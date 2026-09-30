from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.config.settings import settings
from api.db.engine import get_session
from api.main import app
from api.pipeline import session_privacy
from api.pipeline.storage import store

FIXTURE = Path(__file__).parent.parent / "fixtures" / "three_page_novel.pdf"


@pytest_asyncio.fixture
async def client(
    session: SQLModelAsyncSession, monkeypatch
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(settings, "public_demo", False)

    async def override() -> AsyncIterator[SQLModelAsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http

    app.dependency_overrides.clear()
    await store.delete_prefix("books/")


async def _upload(client: AsyncClient, project_id: str):
    return await client.post(
        f"/api/projects/{project_id}/books",
        files={
            "file": ("three_page_novel.pdf", FIXTURE.read_bytes(), "application/pdf")
        },
    )


class TestSingleUserInstall:
    async def test_projects_are_plain_with_no_session_and_no_one_project_cap(
        self, client: AsyncClient
    ) -> None:
        first = await client.post("/api/projects", json={"name": "First"})
        second = await client.post("/api/projects", json={"name": "Second"})

        assert first.status_code == second.status_code == 201
        assert session_privacy.SESSION_TOKEN_HEADER not in first.headers
        assert first.json()["id"] != second.json()["id"]

        shown = await client.get(f"/api/projects/{first.json()['id']}")
        assert shown.status_code == 200

    async def test_no_upload_limit_applies(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        monkeypatch.setenv("UPLOAD_MAX_PAGES", "1")
        monkeypatch.setenv("UPLOAD_MAX_PER_SESSION", "0")
        project = await client.post("/api/projects", json={"name": "Big books"})

        upload = await _upload(client, project.json()["id"])

        assert upload.status_code == 202

    async def test_a_project_created_with_the_demo_off_is_deletable_without_a_token(
        self, client: AsyncClient
    ) -> None:
        project = await client.post("/api/projects", json={"name": "Scratch"})
        project_id = project.json()["id"]

        deleted = await client.delete(f"/api/projects/{project_id}")

        assert deleted.status_code == 204
        assert (await client.get(f"/api/projects/{project_id}")).status_code == 404
