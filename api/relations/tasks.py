import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.llm import PermanentLLMError, TransientLLMError

from ..contracts.enums import AssertionType, StageName
from ..contracts.graph import AggregatedRelation
from ..db.engine import db_session
from ..db.models.relation_model import Relation
from ..pipeline import repository as pipeline_repository
from ..pipeline.storage import StorageError, store
from ..review import workflow as review_workflow
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

    Gated on the roster staying stable first (S7.1, F5.1): an open
    ``merge_characters``/``merge_across_books`` task for this book means
    alias resolution or reconciliation left an identity question unsettled,
    and extracting against a roster that might still merge two characters
    keys every edge on the wrong id. A book with no such ambiguity clears the
    gate inside the same call and pays nothing for it.
    """
    if not await review_workflow.pass_gate(book_id, review_workflow.ROSTER_GATE):
        logger.info(
            "book %s: relations.extract deferred, roster ambiguity still open", book_id
        )
        return

    async with db_session() as session:
        entries = await repository.load_project_roster(session, book_id)
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


async def _uncertain_relation_entries(
    session: SQLModelAsyncSession,
    project_id: UUID,
    relations: list[AggregatedRelation],
) -> list[dict]:
    """Flag edges backed by exactly one dialogue-only claim for human confirmation.

    Not a confidence-threshold sweep (S7.2 DoD is explicit about that): a
    hearsay claim repeated by two speakers, or narrated even once, is treated
    as established the way the rest of the pipeline already treats it. A
    single character's unverified word is the one case worth a second look
    before it stands as fact in the graph.
    """
    entries = []
    for relation in relations:
        if not (relation.hearsay and len(relation.evidence) == 1):
            continue

        row_id = (
            await session.exec(
                select(Relation.id)
                .where(Relation.project_id == project_id)
                .where(Relation.subject_character_id == relation.subject_character_id)
                .where(Relation.predicate == relation.predicate)
                .where(Relation.object_character_id == relation.object_character_id)
            )
        ).first()
        if row_id is not None:
            entries.append(
                {"relation_id": str(row_id), "reason": "single dialogue-sourced claim"}
            )

    return entries


async def _aggregate_relations(book_id: UUID, record: StageRecord) -> None:
    """Group staged facts into edges, recomputing the whole project from evidence.

    Gated the same way ``relations.extract`` is (see there): if the roster
    was still ambiguous when extraction ran, it deferred and left no staged
    artifact, and this stage must defer too rather than treat a missing
    artifact as the permanent "pass 1 never ran" error it means in every
    other case.
    """
    if not await review_workflow.pass_gate(book_id, review_workflow.ROSTER_GATE):
        logger.info(
            "book %s: relations.aggregate deferred, roster ambiguity still open",
            book_id,
        )
        return

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
        uncertain = await _uncertain_relation_entries(
            session, project_id, result.relations
        )
        await repository.replace_confirm_relation_tasks(
            session, project_id, book_id, uncertain
        )

    record.rows_written = written

    # Fires the real interrupt() here, at the point aggregation actually
    # found something to ask about, rather than silently deferring it to
    # whenever graph.upsert next happens to run.
    await review_workflow.pass_gate(book_id, review_workflow.CONFLICT_GATE)


@celery_app.task(name=StageName.EXTRACT_RELATIONS.value, **RETRY_POLICY)
def extract_relations(book_id: str) -> dict:
    """Pass 2 — extract validated relation assertions from every candidate chunk."""
    return _execute(book_id, StageName.EXTRACT_RELATIONS, _extract_relations)


@celery_app.task(name=StageName.AGGREGATE_RELATIONS.value, **RETRY_POLICY)
def aggregate_relations(book_id: str) -> dict:
    """Collapse assertions into edges with evidence, history and provenance."""
    return _execute(book_id, StageName.AGGREGATE_RELATIONS, _aggregate_relations)
