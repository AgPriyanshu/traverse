import uuid

import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import CandidateKind, ImportanceTier, ResolutionMethod
from api.db.models import Book, Character, DocumentChunk
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

    async def test_persist_then_delete_removes_unverified_orphans(
        self, session: SQLModelAsyncSession, book: Book, chunk: DocumentChunk
    ) -> None:
        row = self._row("Elizabeth Bennet", chunk.id)

        persisted = await extraction_repository.persist_characters(
            session, book.id, book.project_id, [row]
        )
        assert len(persisted) == 1

        await extraction_repository.delete_book_characters(session, book.id)

        character = await session.get(Character, persisted[0].id)
        assert character is None

    async def test_a_human_verified_character_survives_delete(
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

        survivor = await session.get(Character, character.id)
        assert survivor is not None


async def test_set_cluster_keys_ignores_candidates_a_rerun_deleted(session) -> None:
    from api.extraction import repository

    await repository.set_cluster_keys(session, {uuid.uuid4(): "Elizabeth Bennet"})
