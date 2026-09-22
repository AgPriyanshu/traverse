"""End-to-end wiring of ``pipeline.extract_characters`` and ``pipeline.resolve_aliases``
(S3.1-S3.5) against a real Postgres — everything except the LLM boundary itself,
which is stubbed at ``api.llm`` per ``api/AGENTS.md``.
"""

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import CandidateKind, StageName
from api.contracts.pipeline import ChunkPayload
from api.db.models import Book, Character, Project
from api.extraction import attributes as attribute_extraction
from api.extraction import discovery as discovery_module
from api.extraction import repository as extraction_repository
from api.extraction.schemas import (
    AttributesOutput,
    ChunkMentionsOutput,
    MentionOutput,
    MentionSweepOutput,
)
from api.pipeline import repository, tasks
from api.workers.stages import StageRecord


def _record(stage: StageName) -> StageRecord:
    return StageRecord(run_id=uuid4(), stage_id=uuid4(), stage=stage, attempt=1)


@pytest.fixture(autouse=True)
def _no_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    """No attribute call needed for this wiring test.

    Attribute extraction is covered on its own in
    ``api/tests/extraction/test_attributes.py``.
    """

    async def fake(*a, **k):
        return AttributesOutput(attributes=[])

    monkeypatch.setattr(attribute_extraction, "structured_call", fake)


@pytest.fixture
def sweep_reply() -> MentionSweepOutput:
    return MentionSweepOutput(
        chunks=[
            ChunkMentionsOutput(
                chunk_index=1,
                mentions=[
                    MentionOutput(
                        surface_form="Elizabeth",
                        kind=CandidateKind.PERSON,
                        context="Elizabeth arrived first.",
                    )
                ],
            ),
            ChunkMentionsOutput(
                chunk_index=2,
                mentions=[
                    MentionOutput(
                        surface_form="Mr. Darcy",
                        kind=CandidateKind.PERSON,
                        context="Mr. Darcy bowed stiffly.",
                    )
                ],
            ),
        ]
    )


@pytest.fixture
async def book_with_chunks(session: SQLModelAsyncSession, project: Project) -> Book:
    row = Book(
        project_id=project.id,
        title="A Test Novel",
        content_hash=uuid4().hex,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    payloads = [
        ChunkPayload(
            text="Elizabeth arrived first.",
            pages=[1],
            page_start=1,
            page_end=1,
            token_count=5,
        ),
        ChunkPayload(
            text="Mr. Darcy bowed stiffly.",
            pages=[2],
            page_start=2,
            page_end=2,
            token_count=5,
        ),
    ]
    await repository.bulk_insert_chunks(session, row.id, payloads)

    return row


class TestExtractCharactersTask:
    async def test_discovers_and_stores_candidates(
        self,
        session: SQLModelAsyncSession,
        book_with_chunks: Book,
        sweep_reply: MentionSweepOutput,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_sweep(*a, **k):
            return sweep_reply

        monkeypatch.setattr(discovery_module, "structured_call", fake_sweep)

        await tasks._extract_characters(
            book_with_chunks.id, _record(StageName.EXTRACT_CHARACTERS)
        )

        candidates = await extraction_repository.list_candidates(
            session, book_with_chunks.id
        )
        surface_forms = {c.surface_form for c in candidates}
        assert surface_forms == {"Elizabeth", "Mr. Darcy"}
        assert all(c.kind == CandidateKind.PERSON for c in candidates)


class TestResolveAliasesTask:
    async def test_persists_a_character_per_cluster(
        self,
        session: SQLModelAsyncSession,
        book_with_chunks: Book,
        sweep_reply: MentionSweepOutput,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_sweep(*a, **k):
            return sweep_reply

        monkeypatch.setattr(discovery_module, "structured_call", fake_sweep)

        await tasks._extract_characters(
            book_with_chunks.id, _record(StageName.EXTRACT_CHARACTERS)
        )
        record = _record(StageName.RESOLVE_ALIASES)
        await tasks._resolve_aliases(book_with_chunks.id, record)

        assert record.rows_written == 2

        statement = select(Character).where(
            Character.project_id == book_with_chunks.project_id  # type: ignore[arg-type]
        )
        rows = (await session.execute(statement)).scalars().all()
        names = {c.canonical_name for c in rows}
        assert names == {"Elizabeth", "Mr. Darcy"}
        assert all(c.importance_tier is not None for c in rows)
        assert all(not c.collision_suspected for c in rows)

    async def test_rerun_is_idempotent(
        self,
        session: SQLModelAsyncSession,
        book_with_chunks: Book,
        sweep_reply: MentionSweepOutput,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_sweep(*a, **k):
            return sweep_reply

        monkeypatch.setattr(discovery_module, "structured_call", fake_sweep)

        await tasks._extract_characters(
            book_with_chunks.id, _record(StageName.EXTRACT_CHARACTERS)
        )
        await tasks._resolve_aliases(
            book_with_chunks.id, _record(StageName.RESOLVE_ALIASES)
        )
        await tasks._extract_characters(
            book_with_chunks.id, _record(StageName.EXTRACT_CHARACTERS)
        )
        await tasks._resolve_aliases(
            book_with_chunks.id, _record(StageName.RESOLVE_ALIASES)
        )

        statement = (
            select(func.count())
            .select_from(Character)
            .where(Character.project_id == book_with_chunks.project_id)  # type: ignore[arg-type]
        )
        total = (await session.execute(statement)).scalar_one()
        assert total == 2
