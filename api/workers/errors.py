class PipelineError(Exception):
    """Base class for every failure raised inside an ingestion stage."""


class TransientError(PipelineError):
    """A failure that a later attempt could plausibly survive.

    Broker hiccups, a model server that is still warming, a lock timeout.
    Celery retries these with exponential backoff.
    """


class PermanentError(PipelineError):
    """A failure that will fail identically on every attempt.

    A corrupt PDF, a page with no provenance, a prompt the model can never
    satisfy. Retrying one four times with backoff wastes twenty minutes and
    ends in the same dead letter, so these are never retried.
    """
