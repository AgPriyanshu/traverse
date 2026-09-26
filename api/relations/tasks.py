import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from api.llm import PermanentLLMError, TransientLLMError

from ..contracts.enums import AssertionType, StageName
from ..db.engine import db_session
from ..pipeline import repository as pipeline_repository
from ..pipeline.storage import StorageError, store
from ..tasks import celery_app
from ..workers.errors import PermanentError, TransientError
from ..workers.policy import RETRY_POLICY
from ..workers.stages import StageRecord, stage
from . import aggregate as aggregation
from . import inputs, repository, speakers
from .extract import ExtractedFact, extract_book
from .roster import choose_roster

logger = logging.getLogger(__name__)

_ARTIFACT = "books/{book_id}/relations_extracted.json"

StageBody = Callable[[UUID, StageRecord], Awaitable[None]]


async def _run_stage(book_id: UUID, name: StageName, body: StageBody) -> dict:
    async with stage(book_id, name) as record:
        try:
            await body(book_id, record)
        except TransientLLMError as exc:
            raise TransientError(str(exc)) from exc
        except PermanentLLMError as exc:
            raise PermanentError(str(exc)) from exc
        except StorageError as exc:
            raise TransientError(str(exc)) from exc

    return {
        "book_id": str(book_id),
        "stage": name.value,
        "attempt": record.attempt,
        "rows_written": record.rows_written,
    }


def _execute(book_id: str, name: StageName, body: StageBody) -> dict:
    return asyncio.run(_run_stage(UUID(book_id), name, body))


async def _extract_relations(book_id: UUID, record: StageRecord) -> None:
    """Pass 2: roster-informed extraction, validated and staged as an artifact.

    Facts are staged in object storage, not Postgres: nothing is an edge until
    ``relations.aggregate`` has grouped, oriented and evidenced it.
    """
    async with db_session() as session:
        entries = await repository.load_book_roster(session, book_id)
        raw_chunks = await pipeline_repository.list_chunks_with_chapter_number(
            session, book_id
        )
        (
            reading_chunks,
            candidate_ids,
            prefilter,
            members,
        ) = await inputs.candidate_reading_chunks(session, book_id, raw_chunks)

    if not entries:
        raise PermanentError(f"book {book_id} has no roster; run pass 1 first")

    roster = choose_roster(entries)
    result = await extract_book(
        reading_chunks, roster, book_id=book_id, only_chunk_ids=candidate_ids
    )
    raw_read = sum(len(members.get(unit_id, (unit_id,))) for unit_id in candidate_ids)
    summary = {
        **result.summary(),
        "prefilter_source": prefilter,
        "raw_chunks_total": len(raw_chunks),
        "raw_chunks_read": raw_read,
    }
    logger.info("book %s pass 2: %s", book_id, summary)

    payload = {
        "summary": summary,
        "facts": [fact.model_dump(mode="json") for fact in result.facts],
    }
    await store.put_bytes(
        _ARTIFACT.format(book_id=book_id),
        json.dumps(payload).encode(),
        content_type="application/json",
    )
    record.rows_written = len(result.facts)


async def _aggregate_relations(book_id: UUID, record: StageRecord) -> None:
    """Group staged facts into edges, recomputing the whole project from evidence."""
    key = _ARTIFACT.format(book_id=book_id)
    if not await store.exists(key):
        raise PermanentError(f"{key} does not exist; relations.extract must run first")

    payload = json.loads(await store.get_bytes(key))
    staged = [ExtractedFact.model_validate(item) for item in payload["facts"]]

    async with db_session() as session:
        project_id, book_order = await repository.book_project_and_order(
            session, book_id
        )
        staged, _source = await speakers.attribute_speakers(session, book_id, staged)
        earlier = await repository.load_facts_from_other_books(
            session, project_id, book_id
        )

        facts = [
            aggregation.Fact(
                subject_id=f.subject_id,
                predicate=f.predicate,
                object_id=f.object_id,
                chunk_id=f.chunk_id,
                book_id=book_id,
                book_order=book_order,
                chapter=f.chapter,
                page_start=f.page_start,
                page_end=f.page_end,
                quote=f.quote,
                assertion_type=AssertionType(f.assertion_type),
                asserted_by_id=f.asserted_by_id,
                confidence=f.confidence,
            )
            for f in staged
        ]
        result = aggregation.aggregate([*earlier, *facts])
        written = await repository.replace_project_relations(
            session, project_id, result.relations
        )
        await repository.replace_conflict_tasks(
            session, project_id, book_id, result.conflicts
        )

    record.rows_written = written


@celery_app.task(name=StageName.EXTRACT_RELATIONS.value, **RETRY_POLICY)
def extract_relations(book_id: str) -> dict:
    """Pass 2 — extract validated relation assertions from every candidate chunk."""
    return _execute(book_id, StageName.EXTRACT_RELATIONS, _extract_relations)


@celery_app.task(name=StageName.AGGREGATE_RELATIONS.value, **RETRY_POLICY)
def aggregate_relations(book_id: str) -> dict:
    """Collapse assertions into edges with evidence, history and provenance."""
    return _execute(book_id, StageName.AGGREGATE_RELATIONS, _aggregate_relations)
