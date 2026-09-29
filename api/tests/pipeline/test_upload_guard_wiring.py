"""Real HTTP proof that do1's ``ops.upload_guard`` is actually wired into
``POST /projects/{id}/books`` (S9.8/S9.5 merge-train reconciliation).

The two modules were built in parallel against the same ``UploadSession``
table without either agent seeing the other's finished code — see
``plans/sprint-9/HANDOFF.md``'s "Sprint 9 merge-train fast-follow" note for
the full reconciliation. This file exists to prove the wiring with real
requests through the ASGI app, not by calling the guard functions in
isolation (``api/tests/ops/test_upload_guard.py`` already covers those units
directly and is do1's).
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.db.engine import get_session
from api.db.models import Project
from api.main import app
from api.pipeline import session_privacy
from api.pipeline.storage import store

FIXTURE = Path(__file__).parent.parent / "fixtures" / "three_page_novel.pdf"


@pytest_asyncio.fixture
async def client(session: SQLModelAsyncSession) -> AsyncIterator[AsyncClient]:
    async def override() -> AsyncIterator[SQLModelAsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http

    app.dependency_overrides.clear()
    await store.delete_prefix("books/")


async def _create_session_project(client: AsyncClient, name: str) -> tuple[str, str]:
    response = await client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    token = response.headers[session_privacy.SESSION_TOKEN_HEADER]

    return token, response.json()["id"]


async def _upload(client: AsyncClient, project_id: str, token: str):
    return await client.post(
        f"/api/projects/{project_id}/books",
        files={
            "file": ("three_page_novel.pdf", FIXTURE.read_bytes(), "application/pdf")
        },
        headers={session_privacy.SESSION_TOKEN_HEADER: token},
    )


class TestPageLimitRejection:
    async def test_over_the_page_cap_is_413_not_202(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """``three_page_novel.pdf`` has 3 page objects — a cap of 1 must reject it."""
        monkeypatch.setenv("UPLOAD_MAX_PAGES", "1")
        token, project_id = await _create_session_project(client, "Too Long")

        response = await _upload(client, project_id, token)

        assert response.status_code == 413
        assert "pages exceeds" in response.json()["detail"]

    async def test_at_or_under_the_cap_still_ingests(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        monkeypatch.setenv("UPLOAD_MAX_PAGES", "3")
        token, project_id = await _create_session_project(client, "Just Fits")

        response = await _upload(client, project_id, token)

        assert response.status_code == 202


class TestSessionQuotaRejection:
    async def test_a_second_upload_on_the_same_session_is_429(
        self, client: AsyncClient
    ) -> None:
        """Default ``UPLOAD_MAX_PER_SESSION=1`` — a session's second book,
        even within the one project it owns, must be rejected, not pooled in
        for free. Nothing prevented this before upload_guard was wired in.

        The second file must differ from the first: identical bytes would
        hit the idempotent-reingest short circuit (F1.5) and return the
        existing book at ``200`` instead of ever reaching the quota check —
        exactly what the *other* test in this class pins down.
        """
        token, project_id = await _create_session_project(client, "One Book Only")

        first = await _upload(client, project_id, token)
        assert first.status_code == 202

        second_pdf = _one_page_pdf("A completely different second book")
        second = await client.post(
            f"/api/projects/{project_id}/books",
            files={"file": ("second.pdf", second_pdf, "application/pdf")},
            headers={session_privacy.SESSION_TOKEN_HEADER: token},
        )

        assert second.status_code == 429
        assert "quota" in second.json()["detail"]

    async def test_a_retry_of_the_same_file_is_not_counted_against_quota(
        self, client: AsyncClient
    ) -> None:
        """The idempotent-reingest short circuit (F1.5) must win over the
        quota check: a retried upload of the exact same bytes returns the
        existing book, not a 429, even once the session's quota is spent."""
        token, project_id = await _create_session_project(client, "Retry Safe")

        first = await _upload(client, project_id, token)
        assert first.status_code == 202
        book_id = first.json()["id"]

        retry = await _upload(client, project_id, token)

        assert retry.status_code == 200
        assert retry.json() == {"status": "already_ingested", "book_id": book_id}


def _one_page_pdf(text: str) -> bytes:
    """A minimal, valid single-page PDF whose content stream is real
    extractable text — unlike a hand-rolled ``/Type /Page`` object with no
    content stream (as ``test_upload_guard.py``'s own ``_fake_pdf`` builds
    for the page-count unit tests), this needs to survive an actual
    ``pypdfium2`` text extraction, since that is what ``books.py`` feeds
    ``check_public_domain`` in the real route.
    """
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 400 200] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream_body = f"BT /F1 12 Tf 10 100 Td ({text}) Tj ET".encode()
    objects.append(
        b"<< /Length "
        + str(len(stream_body)).encode()
        + b" >>\nstream\n"
        + stream_body
        + b"\nendstream"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_offset = len(out)
    count = len(objects) + 1
    out += f"xref\n0 {count}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF"
    ).encode()

    return bytes(out)


class TestPublicDomainRejection:
    async def test_a_flagged_upload_is_422(self, client: AsyncClient) -> None:
        token, project_id = await _create_session_project(client, "Copyrighted")

        flagged_pdf = _one_page_pdf("All rights reserved. ISBN 978-0-00-000000-0")
        response = await client.post(
            f"/api/projects/{project_id}/books",
            files={"file": ("scan.pdf", flagged_pdf, "application/pdf")},
            headers={session_privacy.SESSION_TOKEN_HEADER: token},
        )

        assert response.status_code == 422
        assert "reasons" in response.json()["detail"]

    async def test_the_bare_fixture_is_not_flagged(self, client: AsyncClient) -> None:
        token, project_id = await _create_session_project(client, "Clean")

        response = await _upload(client, project_id, token)

        assert response.status_code == 202


class TestPublicProjectsAreExempt:
    async def test_no_owning_session_skips_every_guard_check(
        self, client: AsyncClient, project: Project, monkeypatch
    ) -> None:
        """A page cap tiny enough to reject any real upload must not apply to
        a project with no owning ``UploadSession`` — the ``project`` fixture
        is inserted directly, exactly like the seeded public corpus and
        ``scripts/ingest_series.py``'s token-free path (session_privacy's own
        module docstring), and neither is a visitor demo upload the guard's
        limits were built for."""
        monkeypatch.setenv("UPLOAD_MAX_PAGES", "1")

        response = await client.post(
            f"/api/projects/{project.id}/books",
            files={
                "file": (
                    "three_page_novel.pdf",
                    FIXTURE.read_bytes(),
                    "application/pdf",
                )
            },
        )

        assert response.status_code == 202

    async def test_a_session_owned_project_still_404s_without_the_token(
        self, client: AsyncClient
    ) -> None:
        """A different check (session_privacy's isolation, not the guard)
        but worth pinning here too: an unowned-looking anonymous request
        against a *session-owned* project must not be mistaken for the
        public-corpus exemption above — it 404s exactly like every other
        book-scoped route (ETH-2, S9.8), before the guard ever runs."""
        create = await client.post("/api/projects", json={"name": "Session Owned"})
        assert create.status_code == 201
        project_id = create.json()["id"]

        response = await client.post(
            f"/api/projects/{project_id}/books",
            files={
                "file": (
                    "three_page_novel.pdf",
                    FIXTURE.read_bytes(),
                    "application/pdf",
                )
            },
        )

        assert response.status_code == 404
