import logging

from langfuse import Langfuse

from ..config import settings

logger = logging.getLogger(__name__)

_client: Langfuse | None = None

# The stringObject filter langfuse.api.trace.list expects for a metadata key —
# see the Langfuse public API's trace-list filter grammar.
_BOOK_ID_FILTER = (
    '[{{"type":"stringObject","column":"metadata","key":"book_id",'
    '"operator":"=","value":"{book_id}"}}]'
)
_PAGE_SIZE = 100


def _client_or_none() -> Langfuse | None:
    global _client

    if not settings.langfuse_enabled:
        return None

    if _client is None:
        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_base_url,
        )

    return _client


def purge_book_traces(book_id: str) -> int:
    """Delete every Langfuse trace tagged with ``book_id`` in its metadata.

    Synchronous (the Langfuse SDK is not async) — call sites run this on a
    worker thread. Returns ``0`` without making a request when Langfuse is
    disabled, so a call site does not need its own feature-flag check.
    """
    client = _client_or_none()

    if client is None:
        return 0

    deleted = 0

    try:
        page = 1
        while True:
            result = client.api.trace.list(
                limit=_PAGE_SIZE,
                page=page,
                filter=_BOOK_ID_FILTER.format(book_id=book_id),
            )
            items = result.data

            if not items:
                break

            for trace in items:
                client.api.trace.delete(trace.id)
                deleted += 1

            if len(items) < _PAGE_SIZE:
                break

            page += 1
    except Exception:
        logger.warning(
            "langfuse trace purge failed for book %s; traces may survive deletion",
            book_id,
            exc_info=True,
        )

    return deleted
