"""Question answering and retrieval. Owned by backend engineer 2."""

from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ..contracts.api import (
    ClarifyResponse,
    QueryEventEnvelope,
    QueryRequest,
    SearchResultOut,
)
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
) -> SearchResultOut:
    not_implemented(OWNER, "S2.9")
