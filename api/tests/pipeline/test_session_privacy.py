import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.config.settings import settings
from api.contracts.enums import (
    AssertionType,
    RelationFamily,
    ReviewTaskType,
    StageName,
    StageState,
)
from api.db.engine import get_session
from api.db.models import (
    Book,
    Chapter,
    Character,
    CharacterAppearance,
    CharacterMention,
    DocumentChunk,
    IngestionRun,
    IngestionStage,
    Project,
    Relation,
    RelationEvidence,
    ReviewTask,
    UploadSession,
)
from api.main import app
from api.pipeline import session_privacy
from api.pipeline.storage import store

FIXTURE = Path(__file__).parent.parent / "fixtures" / "three_page_novel.pdf"


@pytest_asyncio.fixture
async def client(
    session: SQLModelAsyncSession, monkeypatch
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(settings, "public_demo", True)

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
    """Create a private project through the real route; return (token, project_id)."""
    response = await client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    token = response.headers[session_privacy.SESSION_TOKEN_HEADER]

    return token, response.json()["id"]


async def _upload(client: AsyncClient, project_id: str, token: str | None) -> dict:
    headers = {session_privacy.SESSION_TOKEN_HEADER: token} if token else {}
    response = await client.post(
        f"/api/projects/{project_id}/books",
        files={
            "file": ("three_page_novel.pdf", FIXTURE.read_bytes(), "application/pdf")
        },
        headers=headers,
    )

    return response


class TestCreateProjectSessionScoping:
    async def test_mints_and_returns_a_session_token(self, client: AsyncClient) -> None:
        response = await client.post("/api/projects", json={"name": "My Book"})

        assert response.status_code == 201
        assert session_privacy.SESSION_TOKEN_HEADER in response.headers
        assert len(response.headers[session_privacy.SESSION_TOKEN_HEADER]) > 10

    async def test_a_second_project_for_the_same_session_is_409(
        self, client: AsyncClient
    ) -> None:
        token, _ = await _create_session_project(client, "First")

        response = await client.post(
            "/api/projects",
            json={"name": "Second"},
            headers={session_privacy.SESSION_TOKEN_HEADER: token},
        )

        assert response.status_code == 409


class TestCrossSessionReadIsolation:
    async def test_wrong_token_gets_404_not_403(self, client: AsyncClient) -> None:
        owner_token, project_id = await _create_session_project(client, "Owner's Book")
        upload_response = await _upload(client, project_id, owner_token)
        assert upload_response.status_code == 202
        book_id = upload_response.json()["id"]

        wrong = await client.get(
            f"/api/books/{book_id}",
            headers={session_privacy.SESSION_TOKEN_HEADER: "not-my-token"},
        )
        missing = await client.get(f"/api/books/{book_id}")
        correct = await client.get(
            f"/api/books/{book_id}",
            headers={session_privacy.SESSION_TOKEN_HEADER: owner_token},
        )

        assert wrong.status_code == 404
        assert missing.status_code == 404
        assert correct.status_code == 200

    async def test_every_book_scoped_route_enforces_ownership(
        self, client: AsyncClient
    ) -> None:
        owner_token, project_id = await _create_session_project(client, "Owner's Book")
        upload_response = await _upload(client, project_id, owner_token)
        book_id = upload_response.json()["id"]
        bad_headers = {session_privacy.SESSION_TOKEN_HEADER: "someone-else"}

        assert (
            await client.get(f"/api/books/{book_id}", headers=bad_headers)
        ).status_code == 404
        assert (
            await client.get(f"/api/books/{book_id}/status", headers=bad_headers)
        ).status_code == 404
        assert (
            await client.get(f"/api/books/{book_id}/chapters", headers=bad_headers)
        ).status_code == 404
        assert (
            await client.get(f"/api/books/{book_id}/chunks", headers=bad_headers)
        ).status_code == 404
        assert (
            await client.get(f"/api/books/{book_id}/pages/1", headers=bad_headers)
        ).status_code == 404
        assert (
            await client.post(f"/api/books/{book_id}/reprocess", headers=bad_headers)
        ).status_code == 404
        assert (
            await client.delete(f"/api/books/{book_id}", headers=bad_headers)
        ).status_code == 404

    async def test_get_project_enforces_ownership(self, client: AsyncClient) -> None:
        owner_token, project_id = await _create_session_project(client, "Private")

        assert (await client.get(f"/api/projects/{project_id}")).status_code == 404
        assert (
            await client.get(
                f"/api/projects/{project_id}",
                headers={session_privacy.SESSION_TOKEN_HEADER: owner_token},
            )
        ).status_code == 200


class TestListingsExcludePrivateProjects:
    async def test_list_projects_hides_others_but_keeps_public(
        self, client: AsyncClient, project: Project, book: Book
    ) -> None:
        """``project``/``book`` (conftest fixtures) are public: no ``UploadSession``
        owns them, matching the seeded public-domain corpus."""
        owner_token, private_project_id = await _create_session_project(
            client, "Private Upload"
        )

        anonymous = await client.get("/api/projects")
        anonymous_ids = {row["id"] for row in anonymous.json()}
        assert str(project.id) in anonymous_ids
        assert private_project_id not in anonymous_ids

        as_owner = await client.get(
            "/api/projects",
            headers={session_privacy.SESSION_TOKEN_HEADER: owner_token},
        )
        owner_ids = {row["id"] for row in as_owner.json()}
        assert str(project.id) in owner_ids
        assert private_project_id in owner_ids

    async def test_list_books_by_project_id_hides_a_private_project(
        self, client: AsyncClient
    ) -> None:
        owner_token, project_id = await _create_session_project(client, "Private")
        await _upload(client, project_id, owner_token)

        response = await client.get(f"/api/books?project_id={project_id}")

        assert response.json() == []


class TestContentHashNeverPoolsAcrossProjects:
    async def test_duplicate_upload_to_a_different_project_is_409_not_reused(
        self, client: AsyncClient
    ) -> None:
        token_a, project_a = await _create_session_project(client, "Session A")
        token_b, project_b = await _create_session_project(client, "Session B")

        first = await _upload(client, project_a, token_a)
        assert first.status_code == 202

        second = await _upload(client, project_b, token_b)

        assert second.status_code == 409
        # The colliding upload must not have created or linked a book under B.
        books_b = await client.get(
            f"/api/projects/{project_b}",
            headers={session_privacy.SESSION_TOKEN_HEADER: token_b},
        )
        assert books_b.json()["books"] == []


class TestDeleteBookCascade:
    """The audit test: a deleted book leaves zero rows anywhere be1 controls."""

    async def _fully_populate_book(
        self, session: SQLModelAsyncSession, client: AsyncClient
    ) -> tuple[str, str]:
        token, project_id = await _create_session_project(client, "Full Book")
        upload = await _upload(client, project_id, token)
        assert upload.status_code == 202
        book_id = uuid.UUID(upload.json()["id"])
        project_uuid = uuid.UUID(project_id)

        chapter = Chapter(
            book_id=book_id, number=1, title="Ch 1", page_start=1, page_end=3
        )
        session.add(chapter)
        await session.commit()
        await session.refresh(chapter)

        chunk = DocumentChunk(
            book_id=book_id,
            chapter_id=chapter.id,
            text="Once upon a time.",
            headings=[],
            pages=[1],
            page_start=1,
            page_end=1,
            token_count=5,
        )
        session.add(chunk)
        await session.commit()
        await session.refresh(chunk)

        run = IngestionRun(book_id=book_id)
        session.add(run)
        await session.commit()
        await session.refresh(run)
        session.add(
            IngestionStage(
                run_id=run.id,
                stage=StageName.PARSE_AND_CHUNK,
                state=StageState.SUCCEEDED,
            )
        )

        subject = Character(project_id=project_uuid, canonical_name="Alice")
        obj = Character(project_id=project_uuid, canonical_name="Bob")
        session.add(subject)
        session.add(obj)
        await session.commit()
        await session.refresh(subject)
        await session.refresh(obj)

        session.add(
            CharacterAppearance(character_id=subject.id, book_id=book_id, first_page=1)
        )
        session.add(
            CharacterMention(
                character_id=subject.id,
                book_id=book_id,
                chunk_id=chunk.id,
                surface_form="Alice",
                page=1,
            )
        )

        relation = Relation(
            project_id=project_uuid,
            subject_character_id=subject.id,
            object_character_id=obj.id,
            predicate="knows",
            family=RelationFamily.SOCIAL,
        )
        session.add(relation)
        await session.commit()
        await session.refresh(relation)

        session.add(
            RelationEvidence(
                relation_id=relation.id,
                book_id=book_id,
                chunk_id=chunk.id,
                page_start=1,
                page_end=1,
                quote="Alice knows Bob.",
                assertion_type=AssertionType.NARRATED,
            )
        )
        session.add(
            ReviewTask(
                project_id=project_uuid,
                book_id=book_id,
                task_type=ReviewTaskType.CONFIRM_RELATION,
                payload={},
            )
        )
        await session.commit()

        return str(book_id), str(project_uuid)

    async def test_deletion_leaves_zero_rows_in_postgres_and_minio(
        self,
        client: AsyncClient,
        session: SQLModelAsyncSession,
        monkeypatch,
    ) -> None:
        monkeypatch.setattr(
            session_privacy.graph_cascade,
            "remove_book",
            AsyncMock(return_value={"relations_written": 0}),
        )
        monkeypatch.setattr(
            session_privacy.graph_projection, "reset_project", AsyncMock(return_value=0)
        )

        book_id_str, project_id_str = await self._fully_populate_book(session, client)
        book_id = uuid.UUID(book_id_str)
        project_id = uuid.UUID(project_id_str)
        storage_key = f"books/{book_id}/source.pdf"

        assert await store.exists(storage_key) is True

        result = await session_privacy.delete_book_cascade(session, book_id)

        assert result["project_deleted"] is True
        session_privacy.graph_cascade.remove_book.assert_awaited_once_with(
            session, project_id, book_id
        )
        session_privacy.graph_projection.reset_project.assert_awaited_once_with(
            project_id
        )

        for model, column in [
            (Book, Book.id),
            (Chapter, Chapter.book_id),
            (DocumentChunk, DocumentChunk.book_id),
            (IngestionRun, IngestionRun.book_id),
            (CharacterAppearance, CharacterAppearance.book_id),
            (CharacterMention, CharacterMention.book_id),
            (RelationEvidence, RelationEvidence.book_id),
            (ReviewTask, ReviewTask.book_id),
        ]:
            rows = (
                (await session.execute(select(model).where(column == book_id)))
                .scalars()
                .all()
            )
            assert rows == [], f"{model.__name__} still has rows for the deleted book"

        # The project had exactly one book, so it — and every project-scoped
        # row, and the session that owned it — must be gone too.
        assert await session.get(Project, project_id) is None
        assert (
            await session.execute(
                select(Character).where(Character.project_id == project_id)
            )
        ).scalars().all() == []
        assert (
            await session.execute(
                select(Relation).where(Relation.project_id == project_id)
            )
        ).scalars().all() == []
        assert (
            await session.execute(
                select(UploadSession).where(UploadSession.project_id == project_id)
            )
        ).scalars().all() == []

        assert await store.exists(storage_key) is False

    async def test_deleting_an_already_deleted_book_is_a_no_op(
        self, client: AsyncClient, session: SQLModelAsyncSession, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            session_privacy.graph_cascade,
            "remove_book",
            AsyncMock(return_value={"relations_written": 0}),
        )
        monkeypatch.setattr(
            session_privacy.graph_projection, "reset_project", AsyncMock(return_value=0)
        )

        token, project_id = await _create_session_project(client, "Once")
        upload = await _upload(client, project_id, token)
        book_id = uuid.UUID(upload.json()["id"])

        first = await session_privacy.delete_book_cascade(session, book_id)
        second = await session_privacy.delete_book_cascade(session, book_id)

        assert first.get("already_deleted") is not True
        assert second == {"book_id": str(book_id), "already_deleted": True}

    async def test_delete_route_survives_a_neo4j_outage(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """A Neo4j failure must not block deleting what Postgres/MinIO hold."""

        async def _boom(*_args, **_kwargs):
            raise RuntimeError("neo4j unreachable")

        monkeypatch.setattr(session_privacy.graph_cascade, "remove_book", _boom)
        monkeypatch.setattr(session_privacy.graph_projection, "reset_project", _boom)

        token, project_id = await _create_session_project(client, "Resilient")
        upload = await _upload(client, project_id, token)
        book_id = upload.json()["id"]

        response = await client.delete(
            f"/api/books/{book_id}",
            headers={session_privacy.SESSION_TOKEN_HEADER: token},
        )

        assert response.status_code == 204


class TestSweepExpiredSessions:
    async def test_sweeps_an_expired_session_and_deletes_its_book(
        self, client: AsyncClient, session: SQLModelAsyncSession, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            session_privacy.graph_cascade,
            "remove_book",
            AsyncMock(return_value={"relations_written": 0}),
        )
        monkeypatch.setattr(
            session_privacy.graph_projection, "reset_project", AsyncMock(return_value=0)
        )

        token, project_id = await _create_session_project(client, "Expiring")
        upload = await _upload(client, project_id, token)
        assert upload.status_code == 202
        book_id = uuid.UUID(upload.json()["id"])

        upload_session = (
            (
                await session.execute(
                    select(UploadSession).where(UploadSession.session_token == token)
                )
            )
            .scalars()
            .first()
        )
        upload_session.expires_at = datetime.now(UTC) - timedelta(hours=1)
        session.add(upload_session)
        await session.commit()

        result = await session_privacy.sweep_expired_upload_sessions(session)

        assert result["sessions_swept"] == 1
        assert result["books_deleted"] == 1
        assert await session.get(Book, book_id) is None
        assert await session.get(Project, uuid.UUID(project_id)) is None

    async def test_a_live_session_is_left_alone(
        self, client: AsyncClient, session: SQLModelAsyncSession
    ) -> None:
        token, project_id = await _create_session_project(client, "Still Live")

        result = await session_privacy.sweep_expired_upload_sessions(session)

        assert result == {"sessions_swept": 0, "books_deleted": 0}
        assert await session.get(Project, uuid.UUID(project_id)) is not None


class TestDeleteProjectRoute:
    @pytest.fixture(autouse=True)
    def _no_neo4j(self, monkeypatch) -> None:
        monkeypatch.setattr(
            session_privacy.graph_cascade,
            "remove_book",
            AsyncMock(return_value={"relations_written": 0}),
        )
        monkeypatch.setattr(
            session_privacy.graph_projection, "reset_project", AsyncMock(return_value=0)
        )

    async def test_owner_deletes_a_project_with_its_books(
        self, client: AsyncClient, session: SQLModelAsyncSession
    ) -> None:
        token, project_id = await _create_session_project(client, "Doomed")
        upload = await _upload(client, project_id, token)
        assert upload.status_code == 202
        book_id = upload.json()["id"]
        storage_key = f"books/{book_id}/source.pdf"
        assert await store.exists(storage_key) is True

        response = await client.delete(
            f"/api/projects/{project_id}",
            headers={session_privacy.SESSION_TOKEN_HEADER: token},
        )

        assert response.status_code == 204
        session.expire_all()
        assert await session.get(Project, uuid.UUID(project_id)) is None
        assert await session.get(Book, uuid.UUID(book_id)) is None
        assert await store.exists(storage_key) is False

    async def test_an_empty_project_can_be_deleted(
        self, client: AsyncClient, session: SQLModelAsyncSession
    ) -> None:
        token, project_id = await _create_session_project(client, "Empty")

        response = await client.delete(
            f"/api/projects/{project_id}",
            headers={session_privacy.SESSION_TOKEN_HEADER: token},
        )

        assert response.status_code == 204
        session.expire_all()
        assert await session.get(Project, uuid.UUID(project_id)) is None

    async def test_another_session_cannot_delete_it_and_cannot_tell_it_exists(
        self, client: AsyncClient, session: SQLModelAsyncSession
    ) -> None:
        _owner_token, project_id = await _create_session_project(client, "Private")
        stranger_token, _other = await _create_session_project(client, "Other")

        with_token = await client.delete(
            f"/api/projects/{project_id}",
            headers={session_privacy.SESSION_TOKEN_HEADER: stranger_token},
        )
        without_token = await client.delete(f"/api/projects/{project_id}")
        missing = await client.delete(f"/api/projects/{uuid.uuid4()}")

        assert with_token.status_code == without_token.status_code == 404
        assert missing.status_code == 404
        session.expire_all()
        assert await session.get(Project, uuid.UUID(project_id)) is not None
