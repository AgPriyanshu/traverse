from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import (
    ClarifyResponse,
    ErrorEvent,
    QueryEventEnvelope,
    QueryRequest,
    SearchResultOut,
)
from ..db.engine import get_session
from ..graph import repository as graph_repository
from ..query import repository as query_repository
from ..query.pipeline import answer_question
from ..query.scope import ReadingScope
from ..retrieval import hybrid_search

router = APIRouter(tags=["query"])
OWNER = "be2"


def _sse_frame(event) -> str:
    """Serialise one ``QueryEvent`` as an SSE frame.

    One JSON object per ``data:`` line, blank line terminated — the format
    ``EventSource``/the frontend's SSE client expects. ``proxy_buffering off``
    must stay set in nginx (Sprint 1) or these frames queue up server-side and
    the stream appears to hang until it closes (query-path.md).
    """
    return f"data: {event.model_dump_json()}\n\n"


async def _event_stream(session: SQLModelAsyncSession, request: QueryRequest):
    try:
        async for event in answer_question(session, request):
            yield _sse_frame(event)
    except Exception as exc:  # noqa: BLE001 - a stream must end with a frame, not a 500
        error = ErrorEvent(type="error", message=str(exc), recoverable=False)
        yield _sse_frame(error)


@router.post(
    "/query",
    response_model=QueryEventEnvelope,
    responses={200: {"content": {"text/event-stream": {}}}},
    description=(
        "Server-sent events. Each frame is one QueryEvent, discriminated on `type`: "
        "token, citation, route, interrupt, done, error."
    ),
)
async def ask(
    body: QueryRequest, session: SQLModelAsyncSession = Depends(get_session)
) -> StreamingResponse:
    if not await graph_repository.project_exists(session, body.project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    return StreamingResponse(
        _event_stream(session, body), media_type="text/event-stream"
    )


@router.post("/query/{thread_id}/respond", response_model=QueryEventEnvelope)
async def respond_to_clarification(
    thread_id: UUID,
    body: ClarifyResponse,
    session: SQLModelAsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Resume a paused thread with the user's answer to a clarifying question.

    The clarification itself just becomes the next question on the same
    thread — ``answer_question`` already resolves names against the
    conversation's carried context (S6.6), so a one-word reply like "the
    younger one" resolves the same way "and her sister?" would.
    """
    conversation = await query_repository.get_conversation(session, thread_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )

    request = QueryRequest(
        project_id=conversation.project_id, question=body.answer, thread_id=thread_id
    )

    return StreamingResponse(
        _event_stream(session, request), media_type="text/event-stream"
    )


@router.get("/search", response_model=SearchResultOut)
async def search(
    project_id: UUID,
    q: str,
    book_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    limit_book_order: int = Query(
        ...,
        description="Required reading position (api/query/scope.py)",
    ),
    limit_chapter: int | None = Query(default=None),
    session: SQLModelAsyncSession = Depends(get_session),
) -> SearchResultOut:
    """Hybrid search: dense (pgvector) + lexical (``ts_rank_cd``), RRF-fused.

    Raises:
        HTTPException: 404 when the project does not exist.
    """
    if not await graph_repository.project_exists(session, project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    result = await hybrid_search(
        session,
        project_id=project_id,
        query=q,
        scope=ReadingScope(book_order=limit_book_order, chapter=limit_chapter),
        book_id=book_id,
        limit=limit,
    )

    return result
