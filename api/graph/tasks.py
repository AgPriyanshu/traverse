import asyncio
import logging
from uuid import UUID

from ..contracts.enums import StageName
from ..db.engine import db_session
from ..review import workflow as review_workflow
from ..tasks import celery_app
from ..workers.errors import PermanentError
from ..workers.policy import RETRY_POLICY
from ..workers.stages import stage
from . import repository, upsert

logger = logging.getLogger(__name__)


async def _upsert_graph(book_id: UUID) -> dict:
    async with stage(book_id, StageName.UPSERT_GRAPH) as record:
        # Both gates, not just "conflict": if the roster gate deferred
        # relations.extract/aggregate entirely, aggregation never ran and the
        # conflict gate alone would see nothing to block on and let a stale
        # or incomplete graph project (S7.1). A book with neither open
        # clears both calls inside this one stage invocation.
        roster_clear = await review_workflow.pass_gate(
            book_id, review_workflow.ROSTER_GATE
        )
        conflict_clear = await review_workflow.pass_gate(
            book_id, review_workflow.CONFLICT_GATE
        )
        if not (roster_clear and conflict_clear):
            logger.info("book %s: graph.upsert deferred, review pending", book_id)
            record.rows_written = 0

            return {
                "book_id": str(book_id),
                "stage": StageName.UPSERT_GRAPH.value,
                "deferred": True,
            }

        async with db_session() as session:
            project_id = await repository.book_project_id(session, book_id)
            if project_id is None:
                raise PermanentError(f"book {book_id} not found")
            try:
                counts = await upsert.upsert_project(session, project_id)
            except upsert.EvidenceRequiredError as exc:
                raise PermanentError(str(exc)) from exc
        record.rows_written = counts["edges"]

    result = {"book_id": str(book_id), "stage": StageName.UPSERT_GRAPH.value, **counts}

    return result


@celery_app.task(name=StageName.UPSERT_GRAPH.value, **RETRY_POLICY)
def upsert_graph(book_id: str) -> dict:
    """Project the project's relations into Neo4j; refuses unevidenced edges."""
    return asyncio.run(_upsert_graph(UUID(book_id)))
