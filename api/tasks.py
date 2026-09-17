"""The Celery application and the frozen ingestion chain.

ORCHESTRATOR-OWNED. Agents register their own tasks in their own modules under
the names in :class:`StageName` and never edit this file.

The chain is built from *string* signatures on purpose: it lets backend
engineer 1 and backend engineer 2 own different stages of one pipeline without
either importing the other's code, which is the single decoupling that makes
the parallel sprint work possible.
"""

from uuid import UUID

from celery import Celery, chain
from celery.canvas import Signature

from .config import settings
from .contracts.enums import StageName

celery_app = Celery(
    "traverse",
    broker=settings.rabbitmq_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)

# Order matters: each stage depends on everything before it.
STAGES: tuple[StageName, ...] = (
    StageName.PARSE_AND_CHUNK,
    StageName.SEGMENT_CHAPTERS,
    StageName.EMBED_CHUNKS,
    StageName.EXTRACT_CHARACTERS,
    StageName.RESOLVE_ALIASES,
    StageName.RECONCILE_CHARACTERS,
    StageName.EXTRACT_RELATIONS,
    StageName.AGGREGATE_RELATIONS,
    StageName.UPSERT_GRAPH,
)


def ingestion_chain(book_id: UUID, *, from_stage: StageName | None = None) -> Signature:
    """Build the ingestion chain for one book.

    Args:
        book_id: The book to ingest.
        from_stage: Resume point. Everything before it is assumed already done
            and is not re-run, which is what makes a failed stage cheap to retry.

    Returns:
        A chain of immutable signatures, one per remaining stage.

    Raises:
        ValueError: If ``from_stage`` is not a known stage.
    """
    stages = list(STAGES)
    if from_stage is not None:
        if from_stage not in stages:
            raise ValueError(f"unknown stage: {from_stage}")
        stages = stages[stages.index(from_stage) :]

    signatures = [
        celery_app.signature(stage.value, args=(str(book_id),), immutable=True)
        for stage in stages
    ]

    return chain(*signatures)
