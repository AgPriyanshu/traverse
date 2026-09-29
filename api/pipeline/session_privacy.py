"""Per-session upload isolation and real deletion (ETH-2, S9.8).

PRD §10's promise is specific: uploads are private, never pooled, never used
for training, and deletable. This module is what makes that literally true
rather than a comment nobody enforces:

- Every project created through ``POST /projects`` is linked 1:1 to the
  ``UploadSession`` that created it (migration 0012). There is no code path in
  this module that lands two different callers' uploads in the same project.
- A project with **no** linked, live ``UploadSession`` is public — the seeded,
  public-domain demo corpus (``scripts/seed_series.py`` inserts it directly,
  never through this API) and anything the orchestrator seeds by hand. That is
  what keeps ``scripts/ingest_series.py``'s existing token-free uploads into
  the seeded corpus working unchanged.
- A missing or wrong session token against a session-owned project is a 404,
  identical to the project not existing at all — never a 403. A 403 would
  confirm to an attacker that *something* is there under a different owner;
  the whole point of isolation is that a private project is indistinguishable
  from a nonexistent one to anyone but its owner.

Deletion (:func:`delete_book_cascade`) is the other half: it is what
``DELETE /books/{id}`` and the TTL sweep both call, and it is written to leave
zero rows in every store the caller can verify without another agent's
Neo4j write access — see the note on the graph cascade below.
"""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import anyio
from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..db.models import Book, Project, UploadSession
from ..extraction import repository as extraction_repository
from ..graph import cascade as graph_cascade
from ..graph import projection as graph_projection
from . import repository as pipeline_repository
from . import tracing_cleanup
from .storage import store

logger = logging.getLogger(__name__)

SESSION_TOKEN_HEADER = "X-Session-Token"
DEFAULT_TTL = timedelta(hours=24)

# be2 holds exclusive write access to the single shared Neo4j instance during
# a sprint (BRANCH.md §4/§9); be1 never touches it directly. This bounds how
# long a delete can spend retrying a Neo4j connection the caller's own
# environment may not have (``api/graph/client.py`` backs off for up to ~2
# minutes across 8 attempts) so a Postgres+MinIO deletion — the two stores
# this module verifies directly — never hangs on a shared resource it does
# not own. See ``plans/sprint-9/HANDOFF.md`` for the integration-time
# real-Neo4j verification this defers to.
_GRAPH_CASCADE_TIMEOUT_SECONDS = 20.0


def _not_found() -> HTTPException:
    """One shared 404 body: existence and ownership must look identical."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="book not found")


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_ip(ip: str | None) -> str | None:
    """One-way hash of the caller's address — enough to rate-limit by, never
    enough to identify (ETH-2: never retain a demo uploader's raw IP)."""
    if not ip:
        return None

    return hashlib.sha256(ip.encode()).hexdigest()


async def _find_live_session_by_token(
    session: SQLModelAsyncSession, token: str | None
) -> UploadSession | None:
    if not token:
        return None

    row = (
        (
            await session.execute(
                select(UploadSession).where(UploadSession.session_token == token)
            )
        )
        .scalars()
        .first()
    )

    if row is None or row.deleted_at is not None:
        return None

    return row


async def owning_session(
    session: SQLModelAsyncSession, project_id: UUID
) -> UploadSession | None:
    """Return the live session that owns ``project_id``, or ``None`` if public.

    ``expires_at`` is deliberately not checked here: an expired-but-not-yet-
    swept session's data stays private to its owner until the TTL sweep
    actually deletes it. Expiry alone must never demote a session's project to
    public — that would let anyone read a stale upload in the window between
    it expiring and the sweeper running.
    """
    row = (
        (
            await session.execute(
                select(UploadSession).where(
                    UploadSession.project_id == project_id,
                    UploadSession.deleted_at.is_(None),  # type: ignore[union-attr]
                )
            )
        )
        .scalars()
        .first()
    )

    return row


async def get_or_create_upload_session(
    session: SQLModelAsyncSession, token: str | None, *, ip: str | None = None
) -> UploadSession:
    """Return the live session for ``token``, or mint a fresh one.

    A token naming an expired or already-swept session is treated as unknown
    rather than revived: reusing an old token must not resurrect or extend a
    session whose TTL has already run out.
    """
    existing = await _find_live_session_by_token(session, token)

    if existing is not None and existing.expires_at > datetime.now(UTC):
        return existing

    new_token = generate_token()
    row = UploadSession(
        session_token=new_token,
        ip_hash=hash_ip(ip),
        expires_at=datetime.now(UTC) + DEFAULT_TTL,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return row


async def link_session_to_project(
    session: SQLModelAsyncSession, upload_session: UploadSession, project_id: UUID
) -> None:
    upload_session.project_id = project_id
    session.add(upload_session)
    await session.commit()


async def record_upload(
    session: SQLModelAsyncSession, upload_session: UploadSession
) -> None:
    upload_session.upload_count += 1
    session.add(upload_session)
    await session.commit()


async def get_visible_project(
    session: SQLModelAsyncSession, project_id: UUID, token: str | None
) -> Project:
    """Return ``project_id``, or raise 404 if it does not exist or is someone
    else's private session's project."""
    project = await session.get(Project, project_id)

    if project is None:
        raise _not_found()

    owner = await owning_session(session, project_id)

    if owner is not None and owner.session_token != token:
        raise _not_found()

    return project


async def get_visible_book(
    session: SQLModelAsyncSession, book_id: UUID, token: str | None
) -> Book:
    """Return a book, or raise 404 if it does not exist or its project is
    owned by a different session (S9.8's cross-session read-path guard)."""
    book = await pipeline_repository.get_book(session, book_id)

    if book is None:
        raise _not_found()

    await get_visible_project(session, book.project_id, token)

    return book


async def visible_project_ids(
    session: SQLModelAsyncSession, project_ids: list[UUID], token: str | None
) -> set[UUID]:
    """Restrict a list of project ids to the ones this caller may see.

    A project stays visible if it has no live owning session (public) or if
    its owning session's token matches the caller's. Used by ``GET /projects``
    and ``GET /books`` so a session-owned project never appears in another
    caller's listing even though nothing in the underlying query filtered on
    ownership.
    """
    if not project_ids:
        return set()

    rows = (
        await session.execute(
            select(UploadSession.project_id, UploadSession.session_token).where(
                UploadSession.project_id.in_(project_ids),  # type: ignore[union-attr]
                UploadSession.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
    ).all()
    owner_by_project = {pid: tok for pid, tok in rows}

    return {pid for pid in project_ids if owner_by_project.get(pid, token) == token}


async def delete_book_cascade(session: SQLModelAsyncSession, book_id: UUID) -> dict:
    """Delete a book from every store it touched.

    Order matters:

    1. The relations/graph cascade (``api.graph.cascade.remove_book``) reads
       this book's ``RelationEvidence`` before anything removes it, reaggregates
       every edge from what is left, and re-projects Neo4j.
    2. This book's own roster contribution (mentions, appearances) is deleted,
       then any character left with zero appearances anywhere is swept.
    3. The ``Book`` row itself is deleted — its ``ON DELETE CASCADE`` foreign
       keys (``api/db/models``) take chapters, chunks, ingestion runs, scenes,
       dialogue lines, review tasks and any remaining evidence with it.
    4. The object-storage prefix (source PDF + cached page renders) and any
       Langfuse traces tagged with this book are purged.
    5. If that was the project's last book, the project itself — and the
       ``UploadSession`` that owned it — are deleted too, and Neo4j's
       ``reset_project`` clears whatever the per-book cascade left standing.

    Idempotent: a book that no longer exists returns immediately rather than
    raising, since both the API route and the TTL sweeper may call this for
    the same book more than once.
    """
    book = await pipeline_repository.get_book(session, book_id)

    if book is None:
        return {"book_id": str(book_id), "already_deleted": True}

    project_id = book.project_id
    storage_prefix = f"books/{book_id}/"

    graph_result: dict = {}
    try:
        with anyio.fail_after(_GRAPH_CASCADE_TIMEOUT_SECONDS):
            graph_result = await graph_cascade.remove_book(session, project_id, book_id)
    except Exception:
        logger.warning(
            "graph cascade failed or timed out for book %s; Neo4j may still hold "
            "this book's edges until the next integration rebuild (make graph-rebuild)",
            book_id,
            exc_info=True,
        )

    await extraction_repository.delete_book_characters(session, book_id)
    await extraction_repository.sweep_orphaned_characters(session, project_id)

    # A raw DELETE, not ``session.delete(book)``: the ORM's own unit-of-work
    # would try to null out every child's foreign key first (Book.chapters
    # etc. carry no ``passive_deletes``), and ``chapter.book_id`` is NOT NULL
    # — this way Postgres's own ``ON DELETE CASCADE`` (api/db/models) does the
    # work directly, the same way ``upsert_chapters`` already deletes here.
    await session.execute(sa_delete(Book).where(Book.id == book_id))  # type: ignore[arg-type]
    await session.commit()

    await store.delete_prefix(storage_prefix)

    traces_purged = await anyio.to_thread.run_sync(
        tracing_cleanup.purge_book_traces, str(book_id)
    )

    remaining = await pipeline_repository.count_books_in_project(session, project_id)
    project_deleted = False

    if remaining == 0:
        owner = await owning_session(session, project_id)

        if owner is not None:
            owner.deleted_at = datetime.now(UTC)
            session.add(owner)
            await session.commit()

        project_row = await session.get(Project, project_id)

        if project_row is not None:
            await session.execute(
                sa_delete(Project).where(Project.id == project_id)  # type: ignore[arg-type]
            )
            await session.commit()

        try:
            with anyio.fail_after(_GRAPH_CASCADE_TIMEOUT_SECONDS):
                await graph_projection.reset_project(project_id)
        except Exception:
            logger.warning(
                "neo4j reset_project failed or timed out for project %s",
                project_id,
                exc_info=True,
            )

        project_deleted = True

    return {
        "book_id": str(book_id),
        "project_id": str(project_id),
        "project_deleted": project_deleted,
        "traces_purged": traces_purged,
        **graph_result,
    }


async def sweep_expired_upload_sessions(session: SQLModelAsyncSession) -> dict:
    """Delete every book of every expired, not-yet-swept upload session.

    The 24h demo-upload TTL (do1's S9.5). Safe to call repeatedly — an
    already-swept session (``deleted_at`` set, or its project already gone)
    is skipped, so a retry or an overlapping schedule never double-deletes.
    """
    now = datetime.now(UTC)
    expired = (
        (
            await session.execute(
                select(UploadSession).where(
                    UploadSession.expires_at <= now,  # type: ignore[operator]
                    UploadSession.deleted_at.is_(None),  # type: ignore[union-attr]
                )
            )
        )
        .scalars()
        .all()
    )

    sessions_swept = 0
    books_deleted = 0

    for upload_session in expired:
        if upload_session.project_id is None:
            # Never uploaded anything before expiring — nothing to cascade,
            # just retire the row so it stops being listed as pending.
            upload_session.deleted_at = now
            session.add(upload_session)
            await session.commit()
            sessions_swept += 1

            continue

        book_ids = (
            (
                await session.execute(
                    select(Book.id).where(Book.project_id == upload_session.project_id)  # type: ignore[union-attr]
                )
            )
            .scalars()
            .all()
        )

        for book_id in book_ids:
            await delete_book_cascade(session, book_id)
            books_deleted += 1

        sessions_swept += 1

    return {"sessions_swept": sessions_swept, "books_deleted": books_deleted}
