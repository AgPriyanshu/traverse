"""Worker-side policy shared by every stage task."""

from .errors import TransientError

# F1.2: exponential backoff, bounded, and only for failures a later attempt
# could survive. A corrupt PDF retried four times with backoff wastes twenty
# minutes to reach the same dead letter, so PermanentError is deliberately
# absent from ``autoretry_for``.
RETRY_POLICY: dict[str, object] = {
    "autoretry_for": (TransientError,),
    "retry_backoff": True,
    "retry_backoff_max": 300,
    "retry_jitter": True,
    "max_retries": 4,
    "acks_late": True,
}

# Modules that register tasks under the frozen stage names. They are owned by
# different agents, so one that has not landed yet must not stop the worker
# booting — ``celery inspect registered`` is what tells you which are missing.
TASK_MODULES: tuple[str, ...] = (
    "api.pipeline.tasks",
    "api.relations.tasks",
    "api.graph.tasks",
)
