import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlmodel import select

from api.contracts.enums import AssertionType, RelationFamily
from api.db.engine import db_session
from api.db.models import Character, CharacterAppearance, Relation, RelationEvidence
from api.db.models.chunk_model import DocumentChunk
from api.db.models.project_model import Book, Project
from api.graph import client as graph_client
from api.graph import upsert
from api.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Drive the real app in-process, against the real traverse_be2 Postgres."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
async def project() -> AsyncIterator[Project]:
    """Create an empty project and delete it afterwards."""
    row = Project(
        name="Fixture project",
        slug=f"fixture-{uuid.uuid4()}",
    )
    async with db_session() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)

    yield row

    # A raw DELETE, not ``session.get`` + ``session.delete``: the latter
    # loads the ORM relationship graph (``Project.books``, ``Book.chapters``,
    # ...) and, without ``passive_deletes=True`` on those relationships
    # (``api/db/models/**`` is orchestrator-owned, not ours to add it to),
    # SQLAlchemy tries to null out each child's NOT NULL foreign key itself
    # instead of leaving it to the DB. A raw statement never touches the ORM
    # cascade machinery, so Postgres's own ``ON DELETE CASCADE`` (already
    # declared on every one of these FKs) does the actual cleanup — which is
    # also just correct: a test that seeded chapters, chunks, characters or
    # mentions off this project must not need to know that to clean up.
    async with db_session() as session:
        await session.execute(delete(Project).where(Project.id == row.id))
        await session.commit()


@pytest.fixture
async def book(project: Project) -> AsyncIterator[Book]:
    """Create one book in the fixture project."""
    row = Book(
        project_id=project.id,
        series_order=1,
        title="Fixture book",
        content_hash=str(uuid.uuid4()),
    )
    async with db_session() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)

    yield row

    # See ``project``'s teardown above for why this is a raw statement.
    async with db_session() as session:
        await session.execute(delete(Book).where(Book.id == row.id))
        await session.commit()


# ── S6 fixtures/helpers: router/retrieval/grounding/conversation tests ──────
#
# These use the ``session`` fixture from the root conftest (real Postgres,
# truncated after each test) directly, rather than the ``client``/``project``/
# ``book`` fixtures above (real app, explicit-delete cleanup) — both patterns
# coexist in this directory because they serve different test shapes:
# API-surface tests above, repository/pipeline-level tests below (same split
# as ``api/tests/graph/test_upsert.py``).


@pytest.fixture(scope="session", autouse=True)
async def neo4j_driver():
    """Open the process-wide driver once and apply the schema, as startup does."""
    await graph_client.connect()
    yield
    await graph_client.close()


async def make_character(
    session, project, *, name: str, aliases: list[str] | None = None
):
    character = Character(
        project_id=project.id, canonical_name=name, aliases=aliases or []
    )
    session.add(character)
    await session.commit()
    await session.refresh(character)

    return character


async def make_chunk(session, book, *, text: str, page: int = 1):
    chunk = DocumentChunk(
        book_id=book.id, text=text, pages=[page], page_start=page, page_end=page
    )
    session.add(chunk)
    await session.commit()
    await session.refresh(chunk)

    return chunk


async def make_relation(
    session,
    project,
    book,
    *,
    subject: Character,
    predicate: str,
    obj: Character,
    family: RelationFamily,
    quote: str,
    chunk: DocumentChunk | None = None,
):
    if chunk is None:
        chunk = await make_chunk(session, book, text=quote)

    for character in (subject, obj):
        exists = (
            await session.exec(
                select(CharacterAppearance.id).where(
                    CharacterAppearance.character_id == character.id,
                    CharacterAppearance.book_id == book.id,
                )
            )
        ).first()
        if exists is None:
            session.add(CharacterAppearance(character_id=character.id, book_id=book.id))

    relation = Relation(
        project_id=project.id,
        subject_character_id=subject.id,
        object_character_id=obj.id,
        predicate=predicate,
        family=family,
        confidence=0.9,
        evidence_count=1,
    )
    session.add(relation)
    await session.flush()
    session.add(
        RelationEvidence(
            relation_id=relation.id,
            book_id=book.id,
            chunk_id=chunk.id,
            chapter_no=1,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            quote=quote,
            assertion_type=AssertionType.NARRATED,
        )
    )
    await session.commit()
    await session.refresh(relation)

    return relation


async def project_now(session, project_id):
    """Project ``project_id``'s current Postgres state into Neo4j.

    Call after seeding characters/relations in Postgres. Callers are
    responsible for ``await projection.reset_project(project_id)`` in a
    ``finally`` block, same as ``api/tests/graph/test_upsert.py``.
    """
    counts = await upsert.upsert_project(session, project_id)

    return counts
