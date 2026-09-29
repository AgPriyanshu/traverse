"""Projects, books and ingestion. Owned by backend engineer 1."""

import hashlib
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

import anyio
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
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
from ..contracts.enums import BookStatus, StageName, StageState
from ..contracts.pipeline import StageStatus
from ..db.engine import get_session
from ..pipeline import render, repository, session_privacy
from ..pipeline.metadata import extract_title_author
from ..pipeline.storage import store
from ..tasks import ingestion_chain
from ._stub import not_implemented

router = APIRouter(tags=["books"])
OWNER = "be1"

# Matches the streaming chunk size ``pipeline/storage.py`` already reads with.
_READ_CHUNK = 1 << 20
_PDF_MAGIC = b"%PDF-"


async def _session_token(
    x_session_token: str | None = Header(
        default=None, alias=session_privacy.SESSION_TOKEN_HEADER
    ),
) -> str | None:
    """The caller's demo-upload session token, if any (ETH-2).

    A plain header dependency rather than a new contract type: session scoping
    is a transport-level concern (who is asking), not part of the frozen
    request/response shapes in ``contracts/api.py``.
    """
    return x_session_token


async def _client_ip(
    x_forwarded_for: str | None = Header(default=None),
) -> str | None:
    if not x_forwarded_for:
        return None

    return x_forwarded_for.split(",")[0].strip()


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
    x_session_token: str | None = Depends(_session_token),
    session: SQLModelAsyncSession = Depends(get_session),
) -> list[ProjectOut]:
    """List every project this caller may see, with book/character/relation counts.

    A project owned by a *different* session's upload never appears here
    (ETH-2, S9.8) — only the public, unowned corpus and, if the caller sent a
    matching token, their own.
    """
    projects = await repository.list_projects(session)
    visible = await session_privacy.visible_project_ids(
        session, [project.id for project in projects], x_session_token
    )

    return [project for project in projects if project.id in visible]


@router.post(
    "/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED
)
async def create_project(
    body: ProjectCreate,
    response: Response,
    x_session_token: str | None = Depends(_session_token),
    ip: str | None = Depends(_client_ip),
    session: SQLModelAsyncSession = Depends(get_session),
) -> ProjectOut:
    """Create a project, private to the caller's upload session by construction.

    Every project made through this route is linked 1:1 to an ``UploadSession``
    (ETH-2, migration 0012) — there is no path here that lands a caller's
    upload in a shared or default project. The seeded, public-domain demo
    corpus is the only project anyone can read without a session token, and it
    is inserted directly by ``scripts/seed_series.py``, never through this
    endpoint. A demo session owns at most one project — the frozen
    ``upload_session.project_id`` column is single-valued, matching do1's
    S9.5 "1 book" visitor quota.

    The response carries the caller's session token back in the
    ``X-Session-Token`` header (minted fresh if none was sent) so the client
    can replay it on every later call for this upload.
    """
    upload_session = await session_privacy.get_or_create_upload_session(
        session, x_session_token, ip=ip
    )

    if upload_session.project_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this session already owns a project",
        )

    project = await repository.create_project(session, name=body.name, kind=body.kind)
    await session_privacy.link_session_to_project(session, upload_session, project.id)

    response.headers[session_privacy.SESSION_TOKEN_HEADER] = (
        upload_session.session_token
    )

    return ProjectOut(
        id=project.id,
        name=project.name,
        slug=project.slug,
        kind=project.kind,
        book_count=0,
        character_count=0,
        relation_count=0,
        updated_at=project.updated_at,
    )


@router.get("/projects/{project_id}", response_model=ProjectDetailOut)
async def get_project(
    project_id: UUID,
    x_session_token: str | None = Depends(_session_token),
    session: SQLModelAsyncSession = Depends(get_session),
) -> ProjectDetailOut:
    """Return one project and the books it contains, in series order."""
    await session_privacy.get_visible_project(session, project_id, x_session_token)
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
    x_session_token: str | None = Depends(_session_token),
    session: SQLModelAsyncSession = Depends(get_session),
) -> list[BookOut]:
    """List books across every project this caller may see, or filter to one.

    A flat list rather than fanning `GET /projects` out into N detail calls —
    the library screen is the first thing a user sees, and it grows worse in a
    series project, where a reader may have many books (SCR-6). Books in a
    project owned by a different session are filtered out exactly like
    `GET /projects` (ETH-2, S9.8) — passing another session's private
    ``project_id`` returns an empty list, the same as a nonexistent one.
    """
    books = await repository.list_books(session, project_id, book_status)
    visible = await session_privacy.visible_project_ids(
        session, [book.project_id for book in books], x_session_token
    )

    return [book for book in books if book.project_id in visible]


@router.post(
    "/projects/{project_id}/books",
    response_model=BookOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_book(
    project_id: UUID,
    file: UploadFile,
    series_order: int | None = Query(default=None),
    x_session_token: str | None = Depends(_session_token),
    session: SQLModelAsyncSession = Depends(get_session),
) -> BookOut | JSONResponse:
    """Stream an uploaded PDF to storage and queue its ingestion.

    Hashing happens while the file streams to a temp path so a 200 MB upload
    never sits in memory whole (F1.1). A ``content_hash`` collision within the
    **same** project short circuits everything after it (F1.5): the object is
    never re-uploaded and the caller gets back the book that already exists,
    at ``200`` rather than ``202`` since nothing was queued. A collision
    against a *different* project's book is never reused (ETH-2, S9.8) — that
    would either pool this upload into someone else's project or hand back an
    id the caller cannot otherwise reach — and is reported as ``409`` instead.

    A project owned by a different session's upload 404s here exactly like
    every other book-scoped route, before anything is read off the file.
    """
    await session_privacy.get_visible_project(session, project_id, x_session_token)

    temp_path, content_hash = await _stream_to_temp_file(file)

    try:
        existing = await repository.get_book_by_hash_in_project(
            session, project_id, content_hash
        )

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

        try:
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
        except IntegrityError:
            # The hash matches a book in a *different* project — never reused
            # (see the docstring). Clean up the object this request just wrote
            # under its own book_id before reporting the conflict.
            await store.delete_prefix(f"books/{book_id}/")

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "identical content has already been ingested under a "
                    "different project; duplicate uploads across projects "
                    "are not supported"
                ),
            ) from None
    finally:
        await anyio.to_thread.run_sync(temp_path.unlink, True)

    if book.id != book_id:
        # Lost a concurrent-upload race for this content_hash within the same
        # project: another request's row won, so the object just written at
        # our own book_id is orphaned. Report the winner rather than a book
        # nothing points at.
        await store.delete_prefix(f"books/{book_id}/")

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "already_ingested", "book_id": str(book.id)},
        )

    owner = await session_privacy.owning_session(session, project_id)
    if owner is not None:
        await session_privacy.record_upload(session, owner)

    await anyio.to_thread.run_sync(ingestion_chain(book.id).apply_async)
    out = await repository.get_book_out(session, book.id)

    return out


@router.get("/books/{book_id}", response_model=BookOut)
async def get_book(
    book_id: UUID,
    x_session_token: str | None = Depends(_session_token),
    session: SQLModelAsyncSession = Depends(get_session),
) -> BookOut:
    """Return one book."""
    await session_privacy.get_visible_book(session, book_id, x_session_token)
    book = await repository.get_book_out(session, book_id)

    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="book not found"
        )

    return book


@router.get("/books/{book_id}/status", response_model=BookStatusOut)
async def get_book_status(
    book_id: UUID,
    x_session_token: str | None = Depends(_session_token),
    session: SQLModelAsyncSession = Depends(get_session),
) -> BookStatusOut:
    """Return a book's ingestion progress, stage by stage.

    The stages come from the latest ingestion run, so a re-process reports its
    own attempt rather than a merge of every run the book has ever had.
    ``status`` is derived from those stages rather than read off the stored
    column: nothing currently updates ``book.status`` as stages complete or
    fail, so the column alone would report every book "queued" forever,
    including one already dead-lettered (see HANDOFF.md).
    """
    await session_privacy.get_visible_book(session, book_id, x_session_token)
    stages = await repository.get_stage_statuses(session, book_id)
    run = await repository.get_latest_run(session, book_id)

    return BookStatusOut(
        book_id=book_id,
        status=repository.derive_book_status(stages),
        stages=stages,
        trace_url=run.trace_url if run else None,
    )


def _parse_stage(raw: str) -> StageName:
    try:
        return StageName(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"unknown stage: {raw!r}"
        ) from exc


def _first_incomplete_stage(statuses: list[StageStatus]) -> StageName | None:
    """Return the earliest stage that has not already succeeded or been skipped.

    ``None`` means every stage this pipeline currently reports on has
    finished — a caller wanting to force a full re-run must name a stage
    explicitly rather than relying on the default, since restarting from
    ``parse_and_chunk`` deletes and re-parses every chunk (F1.5).
    """
    by_stage = {entry.stage: entry for entry in statuses}

    for stage_name in StageName:
        entry = by_stage.get(stage_name)
        if entry is None or entry.state not in (
            StageState.SUCCEEDED,
            StageState.SKIPPED,
        ):
            return stage_name

    return None


@router.post("/books/{book_id}/reprocess", response_model=BookStatusOut)
async def reprocess_book(
    book_id: UUID,
    from_stage: str | None = Query(default=None),
    x_session_token: str | None = Depends(_session_token),
    session: SQLModelAsyncSession = Depends(get_session),
) -> BookStatusOut:
    """Re-run ingestion for a book from a named stage onward.

    Everything before ``from_stage`` is left untouched, and any chapter a
    human has since verified survives regardless of where the re-run starts
    — ``upsert_chapters`` never overwrites one (F5.4). Omitting ``from_stage``
    resumes from this book's first stage that has not already succeeded, so
    a "Retry" action does not require the caller to already know which stage
    is dead-lettered.
    """
    await session_privacy.get_visible_book(session, book_id, x_session_token)

    if from_stage is not None:
        stage_name = _parse_stage(from_stage)
    else:
        statuses = await repository.get_stage_statuses(session, book_id)
        stage_name = _first_incomplete_stage(statuses)

        if stage_name is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="every stage has already succeeded; pass from_stage explicitly",
            )

    await repository.set_book_status(session, book_id, BookStatus.PROCESSING)
    await anyio.to_thread.run_sync(
        ingestion_chain(book_id, from_stage=stage_name).apply_async
    )

    stages = await repository.get_stage_statuses(session, book_id)
    run = await repository.get_latest_run(session, book_id)

    return BookStatusOut(
        book_id=book_id,
        status=BookStatus.PROCESSING,
        stages=stages,
        trace_url=run.trace_url if run else None,
    )


@router.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(
    book_id: UUID,
    x_session_token: str | None = Depends(_session_token),
    session: SQLModelAsyncSession = Depends(get_session),
) -> None:
    """Delete a book from every store it touched — Postgres, object storage,
    and the graph and trace stores its ingestion wrote to (ETH-2, S9.8).

    Idempotent (``session_privacy.delete_book_cascade``): a book that does not
    exist, or was never visible to this caller, both 404 rather than silently
    no-opping, since a caller must not be able to distinguish "already
    deleted" from "never existed" for someone else's book.
    """
    await session_privacy.get_visible_book(session, book_id, x_session_token)
    await session_privacy.delete_book_cascade(session, book_id)


@router.get("/books/{book_id}/chapters", response_model=list[ChapterOut])
async def list_chapters(
    book_id: UUID,
    x_session_token: str | None = Depends(_session_token),
    session: SQLModelAsyncSession = Depends(get_session),
) -> list[ChapterOut]:
    """Return a book's chapters, in page order, each with its chunk count."""
    await session_privacy.get_visible_book(session, book_id, x_session_token)
    chapters = await repository.list_chapters_out(session, book_id)

    return chapters


@router.get("/books/{book_id}/chunks", response_model=list[ChunkOut])
async def list_chunks(
    book_id: UUID,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    x_session_token: str | None = Depends(_session_token),
    session: SQLModelAsyncSession = Depends(get_session),
) -> list[ChunkOut]:
    """Return a page of a book's chunks, in document order."""
    await session_privacy.get_visible_book(session, book_id, x_session_token)
    chunks = await repository.list_chunks_out(
        session, book_id, limit=limit, offset=offset
    )

    return chunks


@router.get("/books/{book_id}/pages/{page}", response_model=PageRenderOut)
async def render_page(
    book_id: UUID,
    page: int,
    x_session_token: str | None = Depends(_session_token),
    session: SQLModelAsyncSession = Depends(get_session),
) -> PageRenderOut:
    """Return a page's rendered image, dimensions and text-span boxes.

    Rendered lazily from the source PDF and cached on first request (S2.6);
    a re-request for the same page never re-touches the source. See
    ``pipeline/render.py`` and the coordinate contract in ``HANDOFF.md``.
    """
    book = await session_privacy.get_visible_book(session, book_id, x_session_token)

    if book.storage_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="book has no stored source"
        )

    try:
        rendered = await render.render_page(
            book_id, book.storage_key, page, book.page_count
        )
    except render.PageOutOfRangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    return rendered
