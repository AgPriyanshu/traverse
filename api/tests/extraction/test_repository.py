import uuid

import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import (
    AssertionType,
    CandidateKind,
    ImportanceTier,
    RelationFamily,
    ResolutionMethod,
)
from api.db.models import Book, Character, DocumentChunk
from api.db.models.relation_model import Relation
from api.extraction import repository as extraction_repository
from api.extraction.discovery import MentionCandidate


@pytest_asyncio.fixture
async def chunk(session: SQLModelAsyncSession, book: Book) -> DocumentChunk:
    """A saved chunk to satisfy ``character_mention``'s foreign key."""
    row = DocumentChunk(
        book_id=book.id,
        text="Mrs Reynolds showed them through the house.",
        pages=[1],
        page_start=1,
        page_end=1,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return row


def _mention(surface_form: str, chunk_id: uuid.UUID, page: int = 1) -> MentionCandidate:
    return MentionCandidate(
        surface_form=surface_form,
        chunk_id=chunk_id,
        page=page,
        chapter_number=None,
        context="some context",
        kind=CandidateKind.PERSON,
        count=1,
    )


class TestAggregateAndReplaceCandidates:
    async def test_replace_then_list_round_trips(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        chunk_id = uuid.uuid4()
        mentions = [
            _mention("Elizabeth", chunk_id),
            _mention("Elizabeth", uuid.uuid4()),
        ]

        aggregated = extraction_repository.aggregate_mentions(mentions)
        assert len(aggregated) == 1
        assert aggregated[0]["mention_count"] == 2

        written = await extraction_repository.replace_candidates(
            session, book.id, aggregated
        )
        assert written == 1

        candidates = await extraction_repository.list_candidates(session, book.id)
        assert len(candidates) == 1
        assert candidates[0].surface_form == "Elizabeth"
        assert candidates[0].mention_count == 2

    async def test_a_replace_clears_the_previous_run(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        first = extraction_repository.aggregate_mentions(
            [_mention("Elizabeth", uuid.uuid4())]
        )
        await extraction_repository.replace_candidates(session, book.id, first)

        second = extraction_repository.aggregate_mentions(
            [_mention("Darcy", uuid.uuid4())]
        )
        await extraction_repository.replace_candidates(session, book.id, second)

        candidates = await extraction_repository.list_candidates(session, book.id)
        assert [c.surface_form for c in candidates] == ["Darcy"]


class TestRejectCandidates:
    async def test_moves_a_candidate_to_rejected_with_its_reason(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        aggregated = extraction_repository.aggregate_mentions(
            [_mention("Longbourn", uuid.uuid4())]
        )
        await extraction_repository.replace_candidates(session, book.id, aggregated)
        candidates = await extraction_repository.list_candidates(session, book.id)

        rejected_count = await extraction_repository.reject_candidates(
            session,
            book.id,
            [
                {
                    "candidate_id": candidates[0].id,
                    "kind": CandidateKind.PLACE,
                    "reason": "an estate, not a person",
                }
            ],
        )

        assert rejected_count == 1
        remaining = await extraction_repository.list_candidates(session, book.id)
        assert remaining == []

        rejected = await extraction_repository.list_rejected(session, book.id)
        assert len(rejected) == 1
        assert rejected[0].surface_form == "Longbourn"
        assert rejected[0].reason == "an estate, not a person"


class TestMarkAsPerson:
    async def test_corrects_a_stored_kind(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        aggregated = extraction_repository.aggregate_mentions(
            [
                MentionCandidate(
                    surface_form="Longbourn",
                    chunk_id=uuid.uuid4(),
                    page=1,
                    context="the Bennets of Longbourn",
                    kind=CandidateKind.PLACE,
                )
            ]
        )
        await extraction_repository.replace_candidates(session, book.id, aggregated)
        candidates = await extraction_repository.list_candidates(session, book.id)

        await extraction_repository.mark_as_person(session, [candidates[0].id])

        updated = await extraction_repository.list_candidates(session, book.id)
        assert updated[0].kind == CandidateKind.PERSON


class TestPersistAndDeleteCharacters:
    def _row(self, name: str, chunk_id: uuid.UUID) -> dict:
        return {
            "canonical_name": name,
            "aliases": [name],
            "importance_tier": ImportanceTier.MAJOR,
            "first_page": 1,
            "first_chapter": 1,
            "last_page": 10,
            "last_chapter": 2,
            "mention_count": 5,
            "attributes": {},
            "collision_suspected": False,
            "mentions": [
                {
                    "chunk_id": str(chunk_id),
                    "surface_form": name,
                    "page": 1,
                    "resolution_method": ResolutionMethod.EXACT,
                }
            ],
        }

    async def test_persist_then_sweep_removes_unverified_orphans(
        self, session: SQLModelAsyncSession, book: Book, chunk: DocumentChunk
    ) -> None:
        row = self._row("Elizabeth Bennet", chunk.id)

        persisted = await extraction_repository.persist_characters(
            session, book.id, book.project_id, [row]
        )
        assert len(persisted) == 1

        # A rerun that no longer produces this canonical name at all (rather
        # than a rerun that reproduces it) is the only way this character
        # should disappear -- delete_book_characters alone must not remove
        # it, or a same-roster rerun would delete-then-recreate its id.
        await extraction_repository.delete_book_characters(session, book.id)
        character = await session.get(Character, persisted[0].id)
        assert character is not None

        await extraction_repository.sweep_orphaned_characters(session, book.project_id)
        character = await session.get(Character, persisted[0].id)
        assert character is None

    async def test_a_human_verified_character_survives_the_sweep(
        self, session: SQLModelAsyncSession, book: Book, chunk: DocumentChunk
    ) -> None:
        row = self._row("Mrs Reynolds", chunk.id)
        persisted = await extraction_repository.persist_characters(
            session, book.id, book.project_id, [row]
        )
        character = persisted[0]
        character.human_verified = True
        session.add(character)
        await session.commit()

        await extraction_repository.delete_book_characters(session, book.id)
        await extraction_repository.sweep_orphaned_characters(session, book.project_id)

        survivor = await session.get(Character, character.id)
        assert survivor is not None

    async def test_a_rerun_with_no_roster_change_keeps_the_same_character_id(
        self, session: SQLModelAsyncSession, book: Book, chunk: DocumentChunk
    ) -> None:
        # The regression this pins: SCR.md's fe1 finding that a
        # resolve_aliases rerun regenerated every Character's id, which
        # cascade-deleted every `relation` row naming it while Neo4j still
        # held the old ids -- every evidence lookup 404'd until a full
        # pass-2 re-run replaced the graph. A rerun of the same roster must
        # reuse the same id.
        row = self._row("Elizabeth Bennet", chunk.id)

        first_pass = await extraction_repository.persist_characters(
            session, book.id, book.project_id, [row]
        )
        first_id = first_pass[0].id

        # The exact sequence a real rerun performs: wipe this book's
        # contribution, then rewrite it from a freshly resolved roster.
        await extraction_repository.delete_book_characters(session, book.id)
        second_pass = await extraction_repository.persist_characters(
            session, book.id, book.project_id, [row]
        )
        await extraction_repository.sweep_orphaned_characters(session, book.project_id)

        assert len(second_pass) == 1
        assert second_pass[0].id == first_id

    async def test_a_relation_survives_a_rerun_that_reproduces_both_endpoints(
        self, session: SQLModelAsyncSession, book: Book, chunk: DocumentChunk
    ) -> None:
        # The concrete failure this pins: with the old always-a-fresh-id
        # behaviour, this Relation would vanish the moment either endpoint's
        # Character row is recreated -- `subject_character_id` and
        # `object_character_id` are `ON DELETE CASCADE` (api/db/models --
        # frozen, not owned here, but the FK behaviour is exactly what the
        # bug rode in on).
        jane = self._row("Jane Bennet", chunk.id)
        bingley = self._row("Bingley", chunk.id)

        first_pass = await extraction_repository.persist_characters(
            session, book.id, book.project_id, [jane, bingley]
        )
        jane_id = next(c.id for c in first_pass if c.canonical_name == "Jane Bennet")
        bingley_id = next(c.id for c in first_pass if c.canonical_name == "Bingley")

        relation = Relation(
            project_id=book.project_id,
            subject_character_id=jane_id,
            object_character_id=bingley_id,
            predicate="married_to",
            family=RelationFamily.ROMANTIC,
            assertion_type=AssertionType.NARRATED,
            evidence_count=1,
        )
        session.add(relation)
        await session.commit()
        relation_id = relation.id

        # A rerun of resolve_aliases with no roster change -- both names
        # still resolve, so both ids, and the edge between them, must
        # survive untouched.
        await extraction_repository.delete_book_characters(session, book.id)
        await extraction_repository.persist_characters(
            session, book.id, book.project_id, [jane, bingley]
        )
        await extraction_repository.sweep_orphaned_characters(session, book.project_id)

        survivor = await session.get(Relation, relation_id)
        assert survivor is not None
        assert survivor.subject_character_id == jane_id
        assert survivor.object_character_id == bingley_id

    async def test_a_rerun_that_drops_a_name_frees_it_for_reuse_elsewhere(
        self, session: SQLModelAsyncSession, book: Book, chunk: DocumentChunk
    ) -> None:
        # A canonical name genuinely absent from a rerun's roster (an alias
        # rule change split or renamed it) is not the same person by this
        # function's own identity rule (project_id, canonical_name), so it
        # is swept rather than kept forever as a dangling duplicate.
        first_row = self._row("Eliza", chunk.id)
        first_pass = await extraction_repository.persist_characters(
            session, book.id, book.project_id, [first_row]
        )
        stale_id = first_pass[0].id

        await extraction_repository.delete_book_characters(session, book.id)
        renamed_row = self._row("Elizabeth Bennet", chunk.id)
        await extraction_repository.persist_characters(
            session, book.id, book.project_id, [renamed_row]
        )
        await extraction_repository.sweep_orphaned_characters(session, book.project_id)

        assert await session.get(Character, stale_id) is None


async def test_set_cluster_keys_ignores_candidates_a_rerun_deleted(session) -> None:
    from api.extraction import repository

    await repository.set_cluster_keys(session, {uuid.uuid4(): "Elizabeth Bennet"})
