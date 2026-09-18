"""The ``pipeline.*`` half of the ingestion chain.

Registered under the frozen names from ``StageName``; the names are the
contract and are already referenced by ``api.tasks.ingestion_chain``. Bodies
land stage by stage across Sprints 2 and 3 — the registration, the retry policy
and the status recording are what Sprint 1 owes.
"""

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

from ..contracts.enums import StageName
from ..tasks import celery_app
from ..workers.policy import RETRY_POLICY
from ..workers.stages import StageRecord, stage

StageBody = Callable[[UUID, StageRecord], Awaitable[None]]


async def _run_stage(book_id: UUID, name: StageName, body: StageBody) -> dict:
    async with stage(book_id, name) as record:
        await body(book_id, record)

    return {
        "book_id": str(book_id),
        "stage": name.value,
        "attempt": record.attempt,
        "rows_written": record.rows_written,
    }


def _execute(book_id: str, name: StageName, body: StageBody) -> dict:
    return asyncio.run(_run_stage(UUID(book_id), name, body))


async def _parse_and_chunk(book_id: UUID, record: StageRecord) -> None:
    raise NotImplementedError("pipeline.parse_and_chunk lands in S2.2")


async def _segment_chapters(book_id: UUID, record: StageRecord) -> None:
    raise NotImplementedError("pipeline.segment_chapters lands in S2.3")


async def _embed_chunks(book_id: UUID, record: StageRecord) -> None:
    raise NotImplementedError("pipeline.embed_chunks lands in S2.4")


async def _extract_characters(book_id: UUID, record: StageRecord) -> None:
    raise NotImplementedError("pipeline.extract_characters lands in S3.1")


async def _resolve_aliases(book_id: UUID, record: StageRecord) -> None:
    raise NotImplementedError("pipeline.resolve_aliases lands in S3.3")


async def _reconcile_characters(book_id: UUID, record: StageRecord) -> None:
    raise NotImplementedError("pipeline.reconcile_characters lands in S5.2")


@celery_app.task(name=StageName.PARSE_AND_CHUNK.value, **RETRY_POLICY)
def parse_and_chunk(book_id: str) -> dict:
    """Convert the uploaded file and write its chunks with page provenance."""
    return _execute(book_id, StageName.PARSE_AND_CHUNK, _parse_and_chunk)


@celery_app.task(name=StageName.SEGMENT_CHAPTERS.value, **RETRY_POLICY)
def segment_chapters(book_id: str) -> dict:
    """Detect chapter boundaries and attach every chunk to its chapter."""
    return _execute(book_id, StageName.SEGMENT_CHAPTERS, _segment_chapters)


@celery_app.task(name=StageName.EMBED_CHUNKS.value, **RETRY_POLICY)
def embed_chunks(book_id: str) -> dict:
    """Embed the chunks that still need it."""
    return _execute(book_id, StageName.EMBED_CHUNKS, _embed_chunks)


@celery_app.task(name=StageName.EXTRACT_CHARACTERS.value, **RETRY_POLICY)
def extract_characters(book_id: str) -> dict:
    """Pass 1 — discover candidate character mentions."""
    return _execute(book_id, StageName.EXTRACT_CHARACTERS, _extract_characters)


@celery_app.task(name=StageName.RESOLVE_ALIASES.value, **RETRY_POLICY)
def resolve_aliases(book_id: str) -> dict:
    """Cluster surface forms into one canonical character per person."""
    return _execute(book_id, StageName.RESOLVE_ALIASES, _resolve_aliases)


@celery_app.task(name=StageName.RECONCILE_CHARACTERS.value, **RETRY_POLICY)
def reconcile_characters(book_id: str) -> dict:
    """Merge this book's roster into the project-wide one."""
    return _execute(book_id, StageName.RECONCILE_CHARACTERS, _reconcile_characters)
