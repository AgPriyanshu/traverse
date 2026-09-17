"""Every database access the ingestion pipeline makes.

Tasks, routes and nodes call these functions; they never build a query inline.
Centralising it is what makes the ``human_verified`` rule enforceable in one
place instead of at forty call sites.
"""

import logging
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import BookOut, ProjectDetailOut, ProjectOut
from ..contracts.enums import BookStatus, StageName, StageState
from ..contracts.pipeline import ChapterInfo, ChunkPayload, StageStatus
from ..db.models import (
    Book,
    Chapter,
    Character,
    CharacterAppearance,
    DocumentChunk,
    IngestionRun,
    IngestionStage,
    Project,
    Relation,
)

logger = logging.getLogger(__name__)

# One statement per batch. Row-by-row inserts of an 800-chunk novel are a
# 30-second stall; batching keeps each statement's parameter count sane.
CHUNK_INSERT_BATCH = 500


async def create_book(
    session: SQLModelAsyncSession,
    *,
    project_id: UUID,
    title: str,
    author: str | None = None,
    content_hash: str,
    page_count: int | None = None,
    series_order: int | None = None,
    storage_key: str | None = None,
) -> Book:
    """Create a book, or return the existing one with the same content hash.

    Idempotent re-ingest (PRD F1.5) is handled by catching the unique violation
    rather than checking first: a check-then-insert races two workers uploading
    the same file and produces a duplicate anyway.

    Args:
        session: Open session; this function commits.
        project_id: Owning project.
        title: Book title.
        author: Book author, if known.
        content_hash: Hash of the uploaded bytes. Unique across the install.
        page_count: Page count, if already known.
        series_order: Position in a series; ``None`` for a standalone.
        storage_key: Object-storage key of the uploaded file.

    Returns:
        The new book, or the pre-existing one with that ``content_hash``.
    """
    book = Book(
        project_id=project_id,
        title=title,
        author=author,
        content_hash=content_hash,
        page_count=page_count,
        series_order=series_order,
        storage_key=storage_key,
    )
    session.add(book)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await get_book_by_hash(session, content_hash)

        if existing is None:
            raise

        return existing

    await session.refresh(book)

    return book


async def get_book_by_hash(
    session: SQLModelAsyncSession, content_hash: str
) -> Book | None:
    """Return the book with this content hash, if one has been ingested."""
    statement = select(Book).where(Book.content_hash == content_hash)
    book = (await session.execute(statement)).scalars().first()

    return book


async def get_book(session: SQLModelAsyncSession, book_id: UUID) -> Book | None:
    """Return one book by id."""
    book = await session.get(Book, book_id)

    return book


async def set_book_status(
    session: SQLModelAsyncSession, book_id: UUID, status: BookStatus
) -> None:
    """Move a book to a new lifecycle status.

    Args:
        session: Open session; this function commits.
        book_id: Book to update.
        status: New status.
    """
    book = await session.get(Book, book_id)

    if book is None:
        raise ValueError(f"no such book: {book_id}")

    # Mutated through the ORM rather than as a bulk UPDATE: a bulk statement
    # expires the attribute on any instance the caller is still holding, and
    # the next read of it attempts lazy IO outside the async context.
    book.status = status
    session.add(book)
    await session.commit()
    # ``updated_at`` is server-generated on update, so the instance is left
    # with an expired attribute unless it is refetched here.
    await session.refresh(book)


async def upsert_chapters(
    session: SQLModelAsyncSession,
    book_id: UUID,
    chapters: list[ChapterInfo],
    *,
    page_ranges: dict[int | None, tuple[int, int]] | None = None,
) -> list[Chapter]:
    """Persist detected chapters for a book, replacing any previous detection.

    Page ranges come from the chunks already stored for the book unless the
    caller supplies them: a chapter's extent is whatever its chunks span, and
    deriving it twice in two places is how the two drift apart.

    Args:
        session: Open session; this function commits.
        book_id: Book the chapters belong to.
        chapters: Detected chapters, in document order.
        page_ranges: Optional ``chapter_number -> (page_start, page_end)``
            override, for a caller that has not written its chunks yet.

    Returns:
        The persisted chapters, ordered by ``page_start``.

    Raises:
        ValueError: If a chapter has no page range and none can be derived.
    """
    if not chapters:
        return []

    ranges = page_ranges or await chapter_page_ranges(session, book_id)
    unplaceable = [c.number for c in chapters if c.number not in ranges]

    if unplaceable:
        raise ValueError(
            f"no page range for chapter(s) {unplaceable} of book {book_id}; "
            "insert chunks first or pass page_ranges"
        )

    await session.execute(delete(Chapter).where(Chapter.book_id == book_id))  # type: ignore[arg-type]

    rows = []
    for info in chapters:
        page_start, page_end = ranges[info.number]
        rows.append(
            {
                "book_id": book_id,
                "number": info.number,
                "title": info.title,
                "heading_text": info.text,
                "page_start": page_start,
                "page_end": page_end,
                "detection_method": info.detection_method,
                "confidence": info.confidence,
            }
        )

    await session.execute(insert(Chapter), rows)
    book = await session.get(Book, book_id)

    if book is not None:
        book.chapter_count = len(rows)
        session.add(book)

    await session.commit()

    if book is not None:
        await session.refresh(book)

    persisted = await list_chapters(session, book_id)

    return persisted


async def list_chapters(session: SQLModelAsyncSession, book_id: UUID) -> list[Chapter]:
    """Return a book's chapters ordered by page."""
    statement = (
        select(Chapter)
        .where(Chapter.book_id == book_id)  # type: ignore[arg-type]
        .order_by(Chapter.page_start, Chapter.number)  # type: ignore[arg-type]
    )
    chapters = list((await session.execute(statement)).scalars().all())

    return chapters


def page_ranges_from_payloads(
    payloads: list[ChunkPayload],
) -> dict[int | None, tuple[int, int]]:
    """Derive each chapter's page extent from the chunks that carry its number.

    A chapter's extent is whatever its chunks span. Computing it from the
    payloads is the only option on a first ingest: nothing in the database
    links a chunk to a chapter number, only to a ``chapter_id`` that does not
    exist yet.

    Args:
        payloads: Chunks in document order.

    Returns:
        ``chapter_number -> (first page, last page)``.
    """
    ranges: dict[int | None, tuple[int, int]] = {}

    for payload in payloads:
        current = ranges.get(payload.chapter_number)
        ranges[payload.chapter_number] = (
            min(payload.page_start, current[0]) if current else payload.page_start,
            max(payload.page_end, current[1]) if current else payload.page_end,
        )

    return ranges


async def chapter_page_ranges(
    session: SQLModelAsyncSession, book_id: UUID
) -> dict[int | None, tuple[int, int]]:
    """Return ``chapter_number -> (first page, last page)`` from stored chunks.

    Only meaningful once chunks carry a ``chapter_id`` — that is, on a
    re-segmentation. Before that use ``page_ranges_from_payloads``.
    """
    statement = (
        select(
            Chapter.number,
            func.min(DocumentChunk.page_start),
            func.max(DocumentChunk.page_end),
        )
        .join(Chapter, Chapter.id == DocumentChunk.chapter_id)  # type: ignore[arg-type]
        .where(DocumentChunk.book_id == book_id)  # type: ignore[arg-type]
        .group_by(Chapter.number)  # type: ignore[arg-type]
    )
    ranges = {
        number: (first, last)
        for number, first, last in (await session.execute(statement)).all()
    }

    return ranges


async def bulk_insert_chunks(
    session: SQLModelAsyncSession,
    book_id: UUID,
    payloads: list[ChunkPayload],
) -> int:
    """Insert chunks for a book in as few statements as possible.

    ``chapter_number`` on each payload is resolved to a real ``chapter_id``
    here, so nothing downstream carries a dangling number. A number with no
    matching chapter row leaves ``chapter_id`` null rather than failing — the
    chunks exist before segmentation runs.

    Args:
        session: Open session; this function commits.
        book_id: Book the chunks belong to.
        payloads: Chunks in document order.

    Returns:
        The number of rows inserted.
    """
    if not payloads:
        return 0

    chapter_ids = await chapter_ids_by_number(session, book_id)
    rows = [
        {
            "book_id": book_id,
            "chapter_id": chapter_ids.get(payload.chapter_number),
            "text": payload.text,
            "headings": [],
            "pages": payload.pages,
            "page_start": payload.page_start,
            "page_end": payload.page_end,
            "token_count": payload.token_count,
            "text_embedding": payload.text_embedding,
        }
        for payload in payloads
    ]

    for start in range(0, len(rows), CHUNK_INSERT_BATCH):
        await session.execute(
            insert(DocumentChunk), rows[start : start + CHUNK_INSERT_BATCH]
        )

    await session.commit()

    return len(rows)


async def chapter_ids_by_number(
    session: SQLModelAsyncSession, book_id: UUID
) -> dict[int | None, UUID]:
    """Return ``chapter_number -> chapter_id`` for one book."""
    statement = select(Chapter.number, Chapter.id).where(Chapter.book_id == book_id)  # type: ignore[arg-type]
    mapping = {
        number: chapter_id
        for number, chapter_id in (await session.execute(statement)).all()
    }

    return mapping


async def assign_chunk_chapters(session: SQLModelAsyncSession, book_id: UUID) -> int:
    """Backfill ``documentchunk.chapter_id`` from the book's chapter page ranges.

    Args:
        session: Open session; this function commits.
        book_id: Book to backfill.

    Returns:
        The number of chunks whose chapter changed.
    """
    chapters = await list_chapters(session, book_id)

    if not chapters:
        return 0

    updated = 0
    for chapter in chapters:
        result = await session.execute(
            update(DocumentChunk)
            .where(DocumentChunk.book_id == book_id)  # type: ignore[arg-type]
            .where(DocumentChunk.page_start >= chapter.page_start)  # type: ignore[arg-type]
            .where(DocumentChunk.page_start <= chapter.page_end)  # type: ignore[arg-type]
            .values(chapter_id=chapter.id)
            .execution_options(synchronize_session=False)
        )
        updated += result.rowcount or 0

    await session.commit()

    return updated


async def count_chunks(session: SQLModelAsyncSession, book_id: UUID) -> int:
    """Return how many chunks a book has."""
    statement = (
        select(func.count())
        .select_from(DocumentChunk)
        .where(
            DocumentChunk.book_id == book_id  # type: ignore[arg-type]
        )
    )
    total = (await session.execute(statement)).scalar_one()

    return total


async def list_chunks(
    session: SQLModelAsyncSession,
    book_id: UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[DocumentChunk]:
    """Return a page of a book's chunks in document order."""
    statement = (
        select(DocumentChunk)
        .where(DocumentChunk.book_id == book_id)  # type: ignore[arg-type]
        .order_by(DocumentChunk.page_start, DocumentChunk.created_at)  # type: ignore[arg-type]
        .limit(limit)
        .offset(offset)
    )
    chunks = list((await session.execute(statement)).scalars().all())

    return chunks


async def get_stage_statuses(
    session: SQLModelAsyncSession, book_id: UUID
) -> list[StageStatus]:
    """Return the latest run's stage statuses for a book, in pipeline order.

    Args:
        session: Open session.
        book_id: Book to report on.

    Returns:
        One entry per stage that has been attempted, ordered by the frozen
        stage sequence. A book that has never been ingested returns ``[]``.
    """
    latest = (
        select(IngestionRun.id)
        .where(IngestionRun.book_id == book_id)  # type: ignore[arg-type]
        .order_by(IngestionRun.created_at.desc())  # type: ignore[union-attr]
        .limit(1)
    )
    run_id = (await session.execute(latest)).scalars().first()

    if run_id is None:
        return []

    statement = select(IngestionStage).where(IngestionStage.run_id == run_id)  # type: ignore[arg-type]
    rows = list((await session.execute(statement)).scalars().all())
    order = {name: index for index, name in enumerate(StageName)}
    rows.sort(key=lambda row: order.get(row.stage, len(order)))

    statuses = [
        StageStatus(
            stage=row.stage,
            state=row.state,
            attempt=row.attempt,
            started_at=row.started_at,
            finished_at=row.finished_at,
            duration_ms=row.duration_ms,
            error=row.error_message,
        )
        for row in rows
    ]

    return statuses


async def get_latest_run(
    session: SQLModelAsyncSession, book_id: UUID
) -> IngestionRun | None:
    """Return the most recent ingestion run for a book, if any."""
    statement = (
        select(IngestionRun)
        .where(IngestionRun.book_id == book_id)  # type: ignore[arg-type]
        .order_by(IngestionRun.created_at.desc())  # type: ignore[union-attr]
        .limit(1)
    )
    run = (await session.execute(statement)).scalars().first()

    return run


def derive_book_status(statuses: list[StageStatus]) -> BookStatus:
    """Map a book's stage statuses onto its lifecycle status.

    Args:
        statuses: Stage statuses from ``get_stage_statuses``.

    Returns:
        The status the book should be reported as.
    """
    if not statuses:
        return BookStatus.QUEUED

    if any(status.state is StageState.FAILED for status in statuses):
        return BookStatus.FAILED

    if any(status.state is StageState.RUNNING for status in statuses):
        return BookStatus.PROCESSING

    every_stage_ran = len(statuses) == len(StageName)
    all_settled = all(
        status.state in {StageState.SUCCEEDED, StageState.SKIPPED}
        for status in statuses
    )

    if every_stage_ran and all_settled:
        return BookStatus.READY

    return BookStatus.PROCESSING


# ── Read models for the HTTP layer ──────────────────────────────────────────


def _book_out(book: Book, *, character_count: int = 0) -> BookOut:
    out = BookOut(
        id=book.id,
        project_id=book.project_id,
        series_order=book.series_order,
        title=book.title,
        author=book.author,
        page_count=book.page_count,
        chapter_count=book.chapter_count,
        character_count=character_count,
        status=book.status,
        ingested_at=book.updated_at if book.status is BookStatus.READY else None,
    )

    return out


async def get_book_out(session: SQLModelAsyncSession, book_id: UUID) -> BookOut | None:
    """Return one book as its HTTP contract, or ``None`` if it does not exist."""
    book = await session.get(Book, book_id)

    if book is None:
        return None

    counts = await _character_counts_by_book(session, [book_id])

    return _book_out(book, character_count=counts.get(book_id, 0))


async def list_books(
    session: SQLModelAsyncSession, project_id: UUID | None = None
) -> list[BookOut]:
    """Return books, optionally restricted to one project, in series order.

    Args:
        session: Open session.
        project_id: Restrict to this project when given.

    Returns:
        Books ordered by ``series_order`` then title; a standalone book has a
        null order and sorts last.
    """
    statement = select(Book).order_by(
        Book.series_order.is_(None),  # type: ignore[union-attr]
        Book.series_order,  # type: ignore[arg-type]
        Book.title,  # type: ignore[arg-type]
    )

    if project_id is not None:
        statement = statement.where(Book.project_id == project_id)  # type: ignore[arg-type]

    books = list((await session.execute(statement)).scalars().all())
    counts = await _character_counts_by_book(session, [book.id for book in books])
    out = [_book_out(book, character_count=counts.get(book.id, 0)) for book in books]

    return out


async def list_projects(session: SQLModelAsyncSession) -> list[ProjectOut]:
    """Return every project with its book, character and relation counts."""
    statement = select(Project).order_by(Project.name)  # type: ignore[arg-type]
    projects = list((await session.execute(statement)).scalars().all())
    ids = [project.id for project in projects]
    books = await _counts_by_project(session, Book, ids)
    characters = await _counts_by_project(session, Character, ids)
    relations = await _counts_by_project(session, Relation, ids)

    out = [
        ProjectOut(
            id=project.id,
            name=project.name,
            slug=project.slug,
            kind=project.kind,
            book_count=books.get(project.id, 0),
            character_count=characters.get(project.id, 0),
            relation_count=relations.get(project.id, 0),
            updated_at=project.updated_at,
        )
        for project in projects
    ]

    return out


async def get_project_detail(
    session: SQLModelAsyncSession, project_id: UUID
) -> ProjectDetailOut | None:
    """Return one project with its books, or ``None`` if it does not exist."""
    project = await session.get(Project, project_id)

    if project is None:
        return None

    books = await list_books(session, project_id)
    characters = await _counts_by_project(session, Character, [project_id])
    relations = await _counts_by_project(session, Relation, [project_id])

    return ProjectDetailOut(
        id=project.id,
        name=project.name,
        slug=project.slug,
        kind=project.kind,
        book_count=len(books),
        character_count=characters.get(project_id, 0),
        relation_count=relations.get(project_id, 0),
        updated_at=project.updated_at,
        books=books,
    )


async def _counts_by_project(
    session: SQLModelAsyncSession, model: type, project_ids: list[UUID]
) -> dict[UUID, int]:
    if not project_ids:
        return {}

    statement = (
        select(model.project_id, func.count())
        .where(model.project_id.in_(project_ids))
        .group_by(model.project_id)
    )
    counts = {
        project_id: total
        for project_id, total in (await session.execute(statement)).all()
    }

    return counts


async def _character_counts_by_book(
    session: SQLModelAsyncSession, book_ids: list[UUID]
) -> dict[UUID, int]:
    if not book_ids:
        return {}

    statement = (
        select(CharacterAppearance.book_id, func.count())
        .where(CharacterAppearance.book_id.in_(book_ids))  # type: ignore[union-attr]
        .group_by(CharacterAppearance.book_id)  # type: ignore[arg-type]
    )
    counts = {
        book_id: total for book_id, total in (await session.execute(statement)).all()
    }

    return counts


async def count_books(session: SQLModelAsyncSession) -> int:
    """Return how many books exist. Used by tests and the ops dashboard."""
    total = (await session.execute(select(func.count()).select_from(Book))).scalar_one()

    return total
