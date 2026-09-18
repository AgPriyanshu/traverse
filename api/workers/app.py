"""Worker entry point. Run with ``celery -A api.workers.app worker``.

The Celery application itself is defined in ``api.tasks`` alongside the frozen
stage names and the ingestion chain, and is re-exported here rather than
redefined: one application object, one broker connection, one task registry.
This module adds everything that is only true of a *worker* — which task
modules to import, and per-process model warm-up — so that importing
``api.tasks`` from the API process does not drag Docling and BGE-M3 in with it.
"""

import logging

from celery.signals import worker_process_init

from ..config import settings
from ..contracts.enums import StageName
from ..tasks import celery_app, ingestion_chain
from .errors import PermanentError, TransientError
from .policy import RETRY_POLICY, TASK_MODULES

logger = logging.getLogger(__name__)

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_reject_on_worker_lost=True,
    result_extended=True,
)


def import_task_modules() -> list[str]:
    """Import every task module, tolerating ones that have not been written yet.

    Celery's own ``imports`` setting is a hard import and would stop the worker
    booting because another agent's package does not exist yet. A worker that
    runs six of nine stages is useful; a worker that refuses to start is not.

    Returns:
        The names of the modules that imported successfully.
    """
    imported: list[str] = []

    for module in TASK_MODULES:
        try:
            __import__(module)
        except ImportError:
            logger.warning("task module %s is not present yet", module)
            continue

        imported.append(module)

    return imported


def missing_stage_tasks() -> list[StageName]:
    """Return the frozen stage names that no task module has registered.

    Returns:
        Stage names absent from the task registry, in pipeline order.
    """
    import_task_modules()
    registered = set(celery_app.tasks.keys())
    missing = [stage for stage in StageName if stage.value not in registered]

    return missing


@worker_process_init.connect
def warm_models(**_kwargs: object) -> None:
    """Load Docling and the embedding model once per worker process.

    Without this the first task a process ever runs also pays a multi-second
    model load, which reads as a mysteriously slow first book. A process that
    cannot warm still starts: a cold cache should surface as a slow worker, not
    as a worker that will not boot.
    """
    from ..pipeline.chunking import DocumentChunker

    try:
        DocumentChunker(settings).warm()
    except Exception:
        logger.warning(
            "model warm-up failed; the first task will pay the load cost",
            exc_info=True,
        )


import_task_modules()

__all__ = [
    "RETRY_POLICY",
    "TASK_MODULES",
    "PermanentError",
    "TransientError",
    "celery_app",
    "import_task_modules",
    "ingestion_chain",
    "missing_stage_tasks",
    "warm_models",
]
