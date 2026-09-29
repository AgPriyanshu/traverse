"""Demo-upload quota, TTL and public-domain guard (S9.5, ETH-1/§12.3).

``UploadSession`` (migration 0012) is the persistence layer; be1's S9.8 wires
per-session isolation and deletion into the actual upload flow
(``api/routes/books.py``, be1-owned -- do1 does not edit it). This module is
the layer *on top*: quota (1 book, ≤150 pages, N/day per IP), the 24h TTL
sweep, and a best-effort public-domain-only guard. be1 calls into these
functions from the upload route; nothing here is wired into a route itself
(see ``plans/sprint-9/HANDOFF.md`` for the exact integration points).

Every limit is read from the environment, not ``api/config/settings.py``
(frozen for the sprint) -- same convention as ``api/ops/budget_guard.py``.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..db.models import Book, Project, UploadSession
from .storage import delete_prefix


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def upload_max_pages() -> int:
    return _int_env("UPLOAD_MAX_PAGES", 150)


def upload_max_per_session() -> int:
    return _int_env("UPLOAD_MAX_PER_SESSION", 1)


def upload_ttl_hours() -> int:
    return _int_env("UPLOAD_TTL_HOURS", 24)


def upload_max_per_ip_per_day() -> int:
    return _int_env("UPLOAD_MAX_PER_IP_PER_DAY", 3)


class UploadGuardError(Exception):
    """Base for every guard rejection. be1's route maps these to HTTP codes:

    ``UploadQuotaExceeded`` -> 429, ``UploadTooLarge`` -> 413,
    ``UploadNotPublicDomain`` -> 422 (rejected) or a flag on the response
    (warned) depending on ``GuardResult.flagged`` vs. ``.reasons`` severity --
    see the module docstring's note on "reject or at minimum flag".
    """


class UploadQuotaExceeded(UploadGuardError):
    pass


class UploadTooLarge(UploadGuardError):
    pass


def hash_ip(ip_address: str) -> str:
    """Never store a raw IP -- a salted-by-nothing sha256 is enough to rate
    limit without being able to reverse it back to an address (ETH-2's own
    "no pooling, no retained PII" spirit, even though session isolation
    itself is be1's S9.8)."""
    return hashlib.sha256(ip_address.encode("utf-8")).hexdigest()


# ── PDF page count ───────────────────────────────────────────────────────────
#
# No PDF library is in api/pyproject.toml (frozen) and Docling's own parse
# happens later, inside the pipeline -- too late to reject an oversized file
# before it burns storage and a queue slot. A `/Type /Page` object count is
# the same "hand-roll the minimum PDF parsing this needs" convention already
# used by scripts/seed_corpus.py's writer; it works because every page object
# in a compliant PDF declares this key exactly once, whether or not the file
# also has a `/Pages` catalog with its own `/Count` (some generators omit or
# lie about that field; counting the actual per-page objects does not).
_PAGE_OBJECT_RE = re.compile(rb"/Type\s*/Page(?!s)\b")


def count_pdf_pages(data: bytes) -> int | None:
    """Best-effort page count from raw PDF bytes, ``None`` if it looks nothing
    like a PDF (some other file entirely -- the caller should reject that too,
    just not with a page-count error)."""
    if not data.startswith(b"%PDF-"):
        return None
    return len(_PAGE_OBJECT_RE.findall(data))


def check_page_limit(page_count: int | None) -> None:
    if page_count is not None and page_count > upload_max_pages():
        raise UploadTooLarge(
            f"{page_count} pages exceeds the demo upload limit of "
            f"{upload_max_pages()} pages"
        )


# ── Public-domain-only guard ─────────────────────────────────────────────────
#
# No copyright registry is reachable from here -- this is a text heuristic,
# not a legal determination. ETH-1 asks for "reject a clearly-copyrighted
# upload, or at minimum flag one"; this clears that bar by catching the
# boilerplate every commercially-published book carries (a copyright page,
# an ISBN, a "no part of this publication" notice) while leaving genuine
# public-domain scans (Gutenberg's own license header does NOT match these)
# unflagged.
#
# Deliberately no bare "copyright <year>"/"©<year>" pattern here: a
# public-domain scan's own front matter often reproduces the original
# publisher's 19th-century copyright notice verbatim, and that must not
# flag -- only `_YEAR_RE` below, checked against the threshold, judges a
# year. These three are strong signals *regardless of year*: a
# Gutenberg-style public-domain text essentially never carries an ISBN or
# "all rights reserved", both artefacts of modern commercial printing.
_COPYRIGHT_MARKERS = (
    re.compile(r"all rights reserved", re.IGNORECASE),
    re.compile(
        r"no part of this (?:publication|book) may be reproduced", re.IGNORECASE
    ),
    re.compile(r"\bISBN[- ]?(?:13|10)?[:\s]*[\d-]{10,}", re.IGNORECASE),
)

# A public-domain work first published long enough ago that a copyright
# notice bearing a *recent* year is the strong signal, not the mere presence
# of the word "copyright" (Gutenberg's own boilerplate footer says
# "Copyright laws are changing all over the world" without asserting one).
_RECENT_YEAR_THRESHOLD = 1928  # US public-domain cutoff, PRD ETH-1's own bar.
_YEAR_RE = re.compile(r"(?:©|\(c\)|copyright)\D{0,10}(\d{4})", re.IGNORECASE)


@dataclass(frozen=True)
class GuardResult:
    flagged: bool
    reasons: list[str] = field(default_factory=list)


def check_public_domain(text_sample: str) -> GuardResult:
    """Scan the first few pages' extracted text for a live copyright claim.

    ``flagged=True`` is a signal for the upload route to reject or hold for
    review, per ETH-1 -- this function never raises, so a caller can choose
    to warn rather than hard-reject if that is the product decision (the
    orchestrator's brief allows either).
    """
    reasons: list[str] = []

    for pattern in _COPYRIGHT_MARKERS:
        if pattern.search(text_sample):
            reasons.append(f"matched copyright marker: {pattern.pattern!r}")

    for year_str in _YEAR_RE.findall(text_sample):
        year = int(year_str)
        if year >= _RECENT_YEAR_THRESHOLD:
            reasons.append(f"copyright year {year} is not public domain")

    return GuardResult(flagged=bool(reasons), reasons=reasons)


# ── Quota and TTL ─────────────────────────────────────────────────────────────


async def count_sessions_for_ip_since(
    session: SQLModelAsyncSession, ip_hash: str, *, since: datetime
) -> int:
    result = await session.execute(
        select(func.count()).select_from(UploadSession)  # type: ignore[arg-type]
        .where(UploadSession.ip_hash == ip_hash)  # type: ignore[arg-type]
        .where(UploadSession.created_at >= since)  # type: ignore[operator]
    )
    return result.scalar_one()


async def check_ip_rate_limit(session: SQLModelAsyncSession, ip_hash: str) -> None:
    since = datetime.now(UTC) - timedelta(days=1)
    count = await count_sessions_for_ip_since(session, ip_hash, since=since)
    if count >= upload_max_per_ip_per_day():
        raise UploadQuotaExceeded(
            f"{ip_hash[:8]}... has started {count} demo upload(s) in the last "
            f"24h, at the limit of {upload_max_per_ip_per_day()}"
        )


def check_session_quota(upload_session: UploadSession) -> None:
    """One book per session (PRD §12.3's default) -- a second upload on an
    already-used session is rejected, not silently pooled into a second book."""
    if upload_session.upload_count >= upload_max_per_session():
        raise UploadQuotaExceeded(
            f"this upload session already used its quota of "
            f"{upload_max_per_session()} book(s)"
        )


async def start_upload_session(
    session: SQLModelAsyncSession, *, session_token: str, ip_hash: str | None
) -> UploadSession:
    """Get the existing session row for this token, or create one.

    Never called after ``check_ip_rate_limit``/``check_session_quota`` have
    already passed for an *existing* token -- creating fresh is only for a
    session this visitor has never used before.
    """
    existing = (
        await session.execute(
            select(UploadSession).where(UploadSession.session_token == session_token)  # type: ignore[arg-type]
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    row = UploadSession(
        session_token=session_token,
        ip_hash=ip_hash,
        expires_at=datetime.now(UTC) + timedelta(hours=upload_ttl_hours()),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def record_upload(
    session: SQLModelAsyncSession, upload_session: UploadSession, *, project_id: UUID
) -> UploadSession:
    """Bump the session's usage after a book is actually accepted."""
    upload_session.upload_count += 1
    upload_session.project_id = project_id
    session.add(upload_session)
    await session.commit()
    await session.refresh(upload_session)
    return upload_session


async def sweep_expired_sessions(session: SQLModelAsyncSession) -> int:
    """Delete every project (and its MinIO objects) behind an expired,
    not-yet-deleted upload session. Returns how many were cleaned up.

    ``UploadSession.project_id`` has ``ondelete="CASCADE"`` (ops_model.py) --
    deleting the project also deletes the session row itself, so a session
    with no project ever attached (rejected before a book was accepted) is
    the only case this marks ``deleted_at`` on directly rather than deleting
    a project.

    Uses a Core ``DELETE`` (not ``session.delete(project)``) on purpose: the
    ORM's default cascade behaviour for an unloaded ``Project.books``
    collection is to NULL each child's ``project_id`` rather than delete it,
    which violates that column's ``NOT NULL`` constraint. A Core statement
    lets Postgres's own ``ON DELETE CASCADE`` (the FK's actual definition)
    do the cascading instead of the ORM second-guessing it.
    """
    now = datetime.now(UTC)
    expired = (
        await session.execute(
            select(UploadSession)
            .where(UploadSession.expires_at < now)  # type: ignore[operator]
            .where(UploadSession.deleted_at.is_(None))  # type: ignore[union-attr]
        )
    ).scalars().all()

    cleaned = 0
    for row in expired:
        if row.project_id is not None:
            books = (
                await session.execute(
                    select(Book.id).where(Book.project_id == row.project_id)  # type: ignore[arg-type]
                )
            ).scalars().all()
            for book_id in books:
                await delete_prefix(f"books/{book_id}/")

            await session.execute(delete(Project).where(Project.id == row.project_id))
        else:
            row.deleted_at = now
            session.add(row)
        cleaned += 1

    await session.commit()
    return cleaned
