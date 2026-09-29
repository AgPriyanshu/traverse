import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.db.models import Book, Project, UploadSession
from api.ops import storage
from api.ops.upload_guard import (
    GuardResult,
    UploadQuotaExceeded,
    UploadTooLarge,
    check_ip_rate_limit,
    check_page_limit,
    check_public_domain,
    check_session_quota,
    count_pdf_pages,
    hash_ip,
    record_upload,
    start_upload_session,
    sweep_expired_sessions,
    upload_max_per_session,
)


def _fake_pdf(page_count: int) -> bytes:
    body = b"\n".join(b"<< /Type /Page /Parent 1 0 R >>" for _ in range(page_count))
    header = f"%PDF-1.4\n<< /Type /Pages /Kids [] /Count {page_count} >>\n".encode()
    return header + body


def test_count_pdf_pages_ignores_the_pages_catalog() -> None:
    assert count_pdf_pages(_fake_pdf(5)) == 5


def test_count_pdf_pages_none_for_non_pdf_bytes() -> None:
    assert count_pdf_pages(b"not a pdf at all") is None


def test_check_page_limit_raises_over_the_cap(monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_MAX_PAGES", "10")
    try:
        check_page_limit(11)
        raise AssertionError("expected UploadTooLarge")
    except UploadTooLarge:
        pass


def test_check_page_limit_allows_at_and_under_the_cap(monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_MAX_PAGES", "10")
    check_page_limit(10)
    check_page_limit(1)
    check_page_limit(None)


def test_hash_ip_is_deterministic_and_not_reversible_looking() -> None:
    digest = hash_ip("203.0.113.7")
    assert digest == hash_ip("203.0.113.7")
    assert "203.0.113.7" not in digest
    assert len(digest) == 64


def test_public_domain_guard_flags_modern_copyright_notice() -> None:
    text = (
        "Copyright © 2023 Some Publisher. All rights reserved. "
        "No part of this publication may be reproduced without permission. "
        "ISBN-13: 978-3-16-148410-0"
    )
    result = check_public_domain(text)
    assert isinstance(result, GuardResult)
    assert result.flagged is True
    assert len(result.reasons) >= 2


def test_public_domain_guard_does_not_flag_gutenberg_boilerplate() -> None:
    text = (
        "This eBook is for the use of anyone anywhere in the United States "
        "and most other parts of the world at no cost and with almost no "
        "restrictions whatsoever. Copyright laws are changing all over the "
        "world. Be sure to check the copyright laws for your country before "
        "downloading or redistributing this or any other Project Gutenberg "
        "eBook."
    )
    result = check_public_domain(text)
    assert result.flagged is False


def test_public_domain_guard_ignores_old_copyright_years() -> None:
    text = "First published 1813. Copyright 1898 by an early publisher."
    result = check_public_domain(text)
    assert result.flagged is False


async def test_session_quota_blocks_a_second_upload(
    session: SQLModelAsyncSession,
) -> None:
    row = UploadSession(
        session_token="tok-1",
        upload_count=upload_max_per_session(),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    try:
        check_session_quota(row)
        raise AssertionError("expected UploadQuotaExceeded")
    except UploadQuotaExceeded:
        pass


async def test_ip_rate_limit_blocks_after_the_daily_cap(
    session: SQLModelAsyncSession, monkeypatch
) -> None:
    monkeypatch.setenv("UPLOAD_MAX_PER_IP_PER_DAY", "2")
    ip_hash = hash_ip("198.51.100.9")
    for i in range(2):
        session.add(
            UploadSession(
                session_token=f"tok-{i}",
                ip_hash=ip_hash,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
    await session.commit()

    try:
        await check_ip_rate_limit(session, ip_hash)
        raise AssertionError("expected UploadQuotaExceeded")
    except UploadQuotaExceeded:
        pass


async def test_start_upload_session_is_idempotent_per_token(
    session: SQLModelAsyncSession,
) -> None:
    first = await start_upload_session(session, session_token="tok-x", ip_hash=None)
    second = await start_upload_session(session, session_token="tok-x", ip_hash=None)
    assert first.id == second.id


async def test_record_upload_bumps_count_and_links_project(
    session: SQLModelAsyncSession, project: Project
) -> None:
    upload_session = await start_upload_session(
        session, session_token="tok-y", ip_hash=None
    )
    updated = await record_upload(session, upload_session, project_id=project.id)
    assert updated.upload_count == 1
    assert updated.project_id == project.id


async def test_sweep_deletes_expired_session_with_no_project(
    session: SQLModelAsyncSession,
) -> None:
    session.add(
        UploadSession(
            session_token="tok-expired-no-project",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    await session.commit()

    cleaned = await sweep_expired_sessions(session)
    assert cleaned == 1


async def test_sweep_leaves_unexpired_sessions_alone(
    session: SQLModelAsyncSession,
) -> None:
    session.add(
        UploadSession(
            session_token="tok-not-expired",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await session.commit()

    cleaned = await sweep_expired_sessions(session)
    assert cleaned == 0


async def test_sweep_deletes_project_and_its_storage_objects(
    session: SQLModelAsyncSession, project: Project
) -> None:
    book = Book(
        project_id=project.id,
        title="Demo Upload",
        content_hash=uuid.uuid4().hex,
    )
    session.add(book)
    await session.commit()
    await session.refresh(book)

    key = f"books/{book.id}/source.pdf"
    await storage.put_stream(
        key, BytesIO(b"%PDF-1.4\n"), content_type="application/pdf"
    )
    assert await storage.exists(key) is True

    session.add(
        UploadSession(
            session_token="tok-expired-with-project",
            project_id=project.id,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    await session.commit()

    cleaned = await sweep_expired_sessions(session)
    assert cleaned == 1
    assert await storage.exists(key) is False
    assert await session.get(Project, project.id) is None
