import uuid

import pytest
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import ImportanceTier, ReviewTaskType
from api.db.models import (
    Character,
    CharacterAppearance,
    CharacterDeath,
    Project,
    ReconciliationDecision,
    ReviewTask,
)
from api.extraction import similarity
from api.reconcile import matching, service

from .conftest import ctx, ingest_book_roster, make_book, make_chunk


@pytest.fixture(autouse=True)
def _no_weak_signal_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every scenario here is decided by the deterministic stages (1-3) or by
    an explicit blocking signal -- embedding and LLM are stubbed off so a test
    failure always points at the cascade or the blocking gate, never at
    non-determinism from a stubbed model.
    """

    async def unavailable(text_a: str, text_b: str) -> None:
        return None

    async def says_different(prompt, schema, **kwargs):
        from api.extraction.schemas import AdjudicationOutput

        return AdjudicationOutput(same_person=False, confidence=0.9, reason="stub")

    monkeypatch.setattr(similarity, "context_similarity", unavailable)
    monkeypatch.setattr(matching, "structured_call", says_different)


async def _character_by_name(
    session: SQLModelAsyncSession, project_id: uuid.UUID, name: str
) -> Character | None:
    statement = select(Character).where(
        Character.project_id == project_id, Character.canonical_name == name
    )

    return (await session.execute(statement)).scalars().first()


class TestReconcileMergesAcrossBooks:
    async def test_alias_overlap_links_a_renamed_returning_character(
        self, session: SQLModelAsyncSession, series_project: Project
    ) -> None:
        book1 = await make_book(session, series_project, series_order=1)
        book3 = await make_book(session, series_project, series_order=3)
        chunk1 = await make_chunk(session, book1)
        chunk3 = await make_chunk(session, book3)

        await ingest_book_roster(
            session,
            book=book1,
            project=series_project,
            characters=[
                {
                    "canonical_name": "Anne Shirley",
                    "aliases": ["Anne Shirley", "Anne"],
                    "tier": ImportanceTier.PROTAGONIST,
                    "mention_count": 100,
                    "contexts": [
                        ctx(10, "Anne Shirley arrived at the station.", chunk1)
                    ],
                }
            ],
        )
        await service.reconcile_book(
            session, book_id=book1.id, project_id=series_project.id
        )

        await ingest_book_roster(
            session,
            book=book3,
            project=series_project,
            characters=[
                {
                    "canonical_name": "Miss Shirley",
                    "aliases": ["Anne Shirley", "Miss Shirley"],
                    "tier": ImportanceTier.MAJOR,
                    "mention_count": 60,
                    "contexts": [
                        ctx(5, "Miss Shirley took her post at the school.", chunk3)
                    ],
                }
            ],
        )
        considered = await service.reconcile_book(
            session, book_id=book3.id, project_id=series_project.id
        )

        assert considered == 1
        characters = (
            (
                await session.execute(
                    select(Character).where(Character.project_id == series_project.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(characters) == 1
        anne = characters[0]
        assert set(anne.aliases) == {"Anne Shirley", "Anne", "Miss Shirley"}

        appearances = (
            (
                await session.execute(
                    select(CharacterAppearance).where(
                        CharacterAppearance.character_id == anne.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert {a.book_id for a in appearances} == {book1.id, book3.id}

        decisions = (
            (
                await session.execute(
                    select(ReconciliationDecision).where(
                        ReconciliationDecision.book_id == book3.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(decisions) == 1
        assert decisions[0].character_id == anne.id
        assert decisions[0].method == "exact"
        assert decisions[0].blocked_by is None

        await session.refresh(series_project)
        assert series_project.roster_version == 2


class TestDeathBlocksAutolink:
    """Named to match the acceptance criterion in
    ``plans/sprint-5/backend-1.md`` S5.2.
    """

    async def test_death_blocks_autolink(
        self, session: SQLModelAsyncSession, series_project: Project
    ) -> None:
        book1 = await make_book(session, series_project, series_order=1)
        book2 = await make_book(session, series_project, series_order=2)
        chunk1 = await make_chunk(session, book1)
        chunk2 = await make_chunk(session, book2)

        await ingest_book_roster(
            session,
            book=book1,
            project=series_project,
            characters=[
                {
                    "canonical_name": "Matthew Cuthbert",
                    "aliases": ["Matthew Cuthbert", "Matthew"],
                    "tier": ImportanceTier.PROTAGONIST,
                    "mention_count": 50,
                    "contexts": [ctx(50, "Matthew Cuthbert walked in.", chunk1)],
                }
            ],
        )
        await service.reconcile_book(
            session, book_id=book1.id, project_id=series_project.id
        )
        matthew = await _character_by_name(
            session, series_project.id, "Matthew Cuthbert"
        )
        assert matthew is not None

        session.add(
            CharacterDeath(character_id=matthew.id, book_id=book1.id, chapter=20)
        )
        await session.commit()

        await ingest_book_roster(
            session,
            book=book2,
            project=series_project,
            characters=[
                {
                    "canonical_name": "Old Matthew",
                    "aliases": ["Old Matthew", "Matthew Cuthbert"],
                    "tier": ImportanceTier.MENTIONED,
                    "mention_count": 5,
                    "contexts": [
                        ctx(
                            10,
                            "Old Matthew stood in the doorway, as if he had "
                            "never left.",
                            chunk2,
                        )
                    ],
                }
            ],
        )
        await service.reconcile_book(
            session, book_id=book2.id, project_id=series_project.id
        )

        characters = (
            (
                await session.execute(
                    select(Character).where(Character.project_id == series_project.id)
                )
            )
            .scalars()
            .all()
        )
        assert {c.canonical_name for c in characters} == {
            "Matthew Cuthbert",
            "Old Matthew",
        }

        decision = (
            (
                await session.execute(
                    select(ReconciliationDecision).where(
                        ReconciliationDecision.book_id == book2.id
                    )
                )
            )
            .scalars()
            .one()
        )
        assert decision.blocked_by is not None
        assert "death" in decision.blocked_by

        review_tasks = (
            (
                await session.execute(
                    select(ReviewTask).where(
                        ReviewTask.project_id == series_project.id,
                        ReviewTask.task_type == ReviewTaskType.MERGE_ACROSS_BOOKS,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(review_tasks) == 1
        candidate_names = {
            c["canonical_name"] for c in review_tasks[0].payload["candidates"]
        }
        assert candidate_names == {"Matthew Cuthbert", "Old Matthew"}


class TestGenerationalNamesake:
    """Named to match the acceptance criterion in
    ``plans/sprint-5/backend-1.md`` S5.2.
    """

    async def test_generational_namesake(
        self, session: SQLModelAsyncSession, series_project: Project
    ) -> None:
        book1 = await make_book(session, series_project, series_order=1)
        book4 = await make_book(session, series_project, series_order=4)
        chunk1 = await make_chunk(session, book1)
        chunk4 = await make_chunk(session, book4)

        await ingest_book_roster(
            session,
            book=book1,
            project=series_project,
            characters=[
                {
                    "canonical_name": "Anne Shirley",
                    "aliases": ["Anne Shirley", "Anne"],
                    "tier": ImportanceTier.PROTAGONIST,
                    "mention_count": 100,
                    "contexts": [ctx(10, "Anne Shirley smiled brightly.", chunk1)],
                }
            ],
        )
        await service.reconcile_book(
            session, book_id=book1.id, project_id=series_project.id
        )

        await ingest_book_roster(
            session,
            book=book4,
            project=series_project,
            characters=[
                {
                    "canonical_name": "Little Anne",
                    "aliases": ["Little Anne", "Anne Shirley"],
                    "tier": ImportanceTier.MENTIONED,
                    "mention_count": 3,
                    "contexts": [
                        ctx(
                            5,
                            "young Anne Shirley toddled after her mother.",
                            chunk4,
                        )
                    ],
                }
            ],
        )
        await service.reconcile_book(
            session, book_id=book4.id, project_id=series_project.id
        )

        characters = (
            (
                await session.execute(
                    select(Character).where(Character.project_id == series_project.id)
                )
            )
            .scalars()
            .all()
        )
        assert {c.canonical_name for c in characters} == {
            "Anne Shirley",
            "Little Anne",
        }

        decision = (
            (
                await session.execute(
                    select(ReconciliationDecision).where(
                        ReconciliationDecision.book_id == book4.id
                    )
                )
            )
            .scalars()
            .one()
        )
        assert decision.blocked_by is not None
