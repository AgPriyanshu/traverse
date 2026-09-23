import asyncio
import logging
from uuid import UUID

from ..contracts.enums import StageName
from ..db.engine import db_session
from ..tasks import celery_app
from ..workers.errors import PermanentError
from ..workers.policy import RETRY_POLICY
from ..workers.stages import stage
from . import repository, upsert

logger = logging.getLogger(__name__)


async def _upsert_graph(book_id: UUID) -> dict:
    async with stage(book_id, StageName.UPSERT_GRAPH) as record:
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
