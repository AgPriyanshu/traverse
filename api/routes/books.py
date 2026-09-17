"""Projects, books and ingestion. Owned by backend engineer 1."""

from uuid import UUID

from fastapi import APIRouter, Query, UploadFile, status

from ..contracts.api import (
    BookOrderUpdate,
    BookOut,
    BookStatusOut,
    ChapterOut,
    ChunkOut,
    PageRenderOut,
    ProjectCreate,
    ProjectDetailOut,
    ProjectOut,
)
from ._stub import not_implemented

router = APIRouter(tags=["books"])
OWNER = "be1"


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects() -> list[ProjectOut]:
    not_implemented(OWNER, "S1.4")


@router.post(
    "/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED
)
async def create_project(body: ProjectCreate) -> ProjectOut:
    not_implemented(OWNER, "S5.9")


@router.get("/projects/{project_id}", response_model=ProjectDetailOut)
async def get_project(project_id: UUID) -> ProjectDetailOut:
    not_implemented(OWNER, "S1.4")


@router.patch("/projects/{project_id}/order", response_model=ProjectDetailOut)
async def reorder_books(project_id: UUID, body: BookOrderUpdate) -> ProjectDetailOut:
    not_implemented(OWNER, "S5.9")


@router.post(
    "/projects/{project_id}/books",
    response_model=BookOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_book(
    project_id: UUID, file: UploadFile, series_order: int | None = Query(default=None)
) -> BookOut:
    not_implemented(OWNER, "S2.1")


@router.get("/books/{book_id}", response_model=BookOut)
async def get_book(book_id: UUID) -> BookOut:
    not_implemented(OWNER, "S1.4")


@router.get("/books/{book_id}/status", response_model=BookStatusOut)
async def get_book_status(book_id: UUID) -> BookStatusOut:
    not_implemented(OWNER, "S1.4")


@router.post("/books/{book_id}/reprocess", response_model=BookStatusOut)
async def reprocess_book(
    book_id: UUID, from_stage: str | None = Query(default=None)
) -> BookStatusOut:
    not_implemented(OWNER, "S2.5")


@router.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(book_id: UUID) -> None:
    not_implemented(OWNER, "S8.8")


@router.get("/books/{book_id}/chapters", response_model=list[ChapterOut])
async def list_chapters(book_id: UUID) -> list[ChapterOut]:
    not_implemented(OWNER, "S2.3")


@router.get("/books/{book_id}/chunks", response_model=list[ChunkOut])
async def list_chunks(
    book_id: UUID, limit: int = Query(default=50, le=500), offset: int = 0
) -> list[ChunkOut]:
    not_implemented(OWNER, "S2.2")


@router.get("/books/{book_id}/pages/{page}", response_model=PageRenderOut)
async def render_page(book_id: UUID, page: int) -> PageRenderOut:
    not_implemented(OWNER, "S2.6")
