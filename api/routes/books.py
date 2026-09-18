"""Projects, books and ingestion. Owned by backend engineer 1."""

import hashlib
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

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
from ..contracts.enums import BookStatus
from ..db.engine import get_session
from ..db.models import Project
from ..pipeline import repository
from ..pipeline.metadata import extract_title_author
from ..pipeline.storage import store
from ..tasks import ingestion_chain
from ._stub import not_implemented

router = APIRouter(tags=["books"])
OWNER = "be1"

# Matches the streaming chunk size ``pipeline/storage.py`` already reads with.
_READ_CHUNK = 1 << 20
_PDF_MAGIC = b"%PDF-"


async def _stream_to_temp_file(file: UploadFile) -> tuple[Path, str]:
    """Write an upload to a temp file while hashing it, never buffered whole.

    Args:
        file: The incoming multipart file.

    Returns:
        The temp file's path and the blake2b hex digest of its bytes.

    Raises:
        HTTPException: 415, if the first chunk is not a PDF signature. 400, if
            the upload is empty.
    """

    # Not a `with`: the handle must outlive this function while chunks stream
    # in across multiple awaits, and is closed explicitly in the `finally`.
    handle = await anyio.to_thread.run_sync(
        lambda: tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)  # noqa: SIM115
    )
    path = Path(handle.name)
    digest = hashlib.blake2b()
    first = True

    try:
        while chunk := await file.read(_READ_CHUNK):
            if first:
                if not chunk.startswith(_PDF_MAGIC):
                    raise HTTPException(
                        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail=(
                            "expected a PDF, received "
                            f"{file.filename!r} ({file.content_type or 'unknown type'})"
                        ),
                    )
                first = False
            digest.update(chunk)
            await anyio.to_thread.run_sync(handle.write, chunk)
    finally:
        await anyio.to_thread.run_sync(handle.close)

    if first:
        await anyio.to_thread.run_sync(path.unlink, True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="uploaded file is empty"
        )

    return path, digest.hexdigest()


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    session: SQLModelAsyncSession = Depends(get_session),
) -> list[ProjectOut]:
    """List every project with its book, character and relation counts."""
    projects = await repository.list_projects(session)

    return projects


@router.post(
    "/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED
)
async def create_project(body: ProjectCreate) -> ProjectOut:
    not_implemented(OWNER, "S5.9")


@router.get("/projects/{project_id}", response_model=ProjectDetailOut)
async def get_project(
    project_id: UUID, session: SQLModelAsyncSession = Depends(get_session)
) -> ProjectDetailOut:
    """Return one project and the books it contains, in series order."""
    project = await repository.get_project_detail(session, project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
        )

    return project


@router.patch("/projects/{project_id}/order", response_model=ProjectDetailOut)
async def reorder_books(project_id: UUID, body: BookOrderUpdate) -> ProjectDetailOut:
    not_implemented(OWNER, "S5.9")


@router.get("/books", response_model=list[BookOut])
async def list_books(
    project_id: UUID | None = Query(default=None),
    book_status: BookStatus | None = Query(default=None, alias="status"),
    session: SQLModelAsyncSession = Depends(get_session),
) -> list[BookOut]:
    """List books across every project, or filter to one.

    A flat list rather than fanning `GET /projects` out into N detail calls —
    the library screen is the first thing a user sees, and it grows worse in a
    series project, where a reader may have many books (SCR-6).
    """
    books = await repository.list_books(session, project_id, book_status)

    return books


@router.post(
    "/projects/{project_id}/books",
    response_model=BookOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_book(
    project_id: UUID,
    file: UploadFile,
    series_order: int | None = Query(default=None),
    session: SQLModelAsyncSession = Depends(get_session),
) -> BookOut | JSONResponse:
    """Stream an uploaded PDF to storage and queue its ingestion.

    Hashing happens while the file streams to a temp path so a 200 MB upload
    never sits in memory whole (F1.1). A ``content_hash`` collision short
    circuits everything after it (F1.5): the object is never re-uploaded and
    the caller gets back the book that already exists, at ``200`` rather than
    ``202`` since nothing was queued.
    """
    project = await session.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
        )

    temp_path, content_hash = await _stream_to_temp_file(file)

    try:
        existing = await repository.get_book_by_hash(session, content_hash)

        if existing is not None:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "already_ingested",
                    "book_id": str(existing.id),
                },
            )

        book_id = uuid4()
        title, author = extract_title_author(
            temp_path, fallback_filename=file.filename or "untitled.pdf"
        )
        storage_key = f"books/{book_id}/source.pdf"
        await store.put_stream(storage_key, temp_path, content_type="application/pdf")

        book = await repository.create_book(
            session,
            id=book_id,
            project_id=project_id,
            title=title,
            author=author,
            content_hash=content_hash,
            series_order=series_order,
            storage_key=storage_key,
        )
    finally:
        await anyio.to_thread.run_sync(temp_path.unlink, True)

    if book.id != book_id:
        # Lost a concurrent-upload race for this content_hash: another
        # request's row won, so the object just written at our own book_id is
        # orphaned. Report the winner rather than a book nothing points at.
        await store.delete_prefix(f"books/{book_id}/")

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "already_ingested", "book_id": str(book.id)},
        )

    await anyio.to_thread.run_sync(ingestion_chain(book.id).apply_async)
    out = await repository.get_book_out(session, book.id)

    return out


@router.get("/books/{book_id}", response_model=BookOut)
async def get_book(
    book_id: UUID, session: SQLModelAsyncSession = Depends(get_session)
) -> BookOut:
    """Return one book."""
    book = await repository.get_book_out(session, book_id)

    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="book not found"
        )

    return book


@router.get("/books/{book_id}/status", response_model=BookStatusOut)
async def get_book_status(
    book_id: UUID, session: SQLModelAsyncSession = Depends(get_session)
) -> BookStatusOut:
    """Return a book's ingestion progress, stage by stage.

    The stages come from the latest ingestion run, so a re-process reports its
    own attempt rather than a merge of every run the book has ever had.
    """
    book = await repository.get_book(session, book_id)

    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="book not found"
        )

    stages = await repository.get_stage_statuses(session, book_id)
    run = await repository.get_latest_run(session, book_id)

    return BookStatusOut(
        book_id=book_id,
        status=book.status,
        stages=stages,
        trace_url=run.trace_url if run else None,
    )


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
