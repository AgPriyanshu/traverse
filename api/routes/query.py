"""Question answering and retrieval. Owned by backend engineer 2."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import (
    ClarifyResponse,
    QueryEventEnvelope,
    QueryRequest,
    SearchResultOut,
)
from ..db.engine import get_session
from ..graph import repository as graph_repository
from ..retrieval import hybrid_search
from ._stub import not_implemented

router = APIRouter(tags=["query"])
OWNER = "be2"


@router.post(
    "/query",
    response_model=QueryEventEnvelope,
    responses={200: {"content": {"text/event-stream": {}}}},
    description=(
        "Server-sent events. Each frame is one QueryEvent, discriminated on `type`: "
        "token, citation, route, interrupt, done, error."
    ),
)
async def ask(body: QueryRequest) -> StreamingResponse:
    not_implemented(OWNER, "S6.5")


@router.post("/query/{thread_id}/respond", response_model=QueryEventEnvelope)
async def respond_to_clarification(
    thread_id: UUID, body: ClarifyResponse
) -> StreamingResponse:
    not_implemented(OWNER, "S6.5")


@router.get("/search", response_model=SearchResultOut)
async def search(
    project_id: UUID,
    q: str,
    book_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    limit_book_order: int | None = Query(default=None),
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
        book_id=book_id,
        limit=limit,
        limit_book_order=limit_book_order,
        limit_chapter=limit_chapter,
    )

    return result
