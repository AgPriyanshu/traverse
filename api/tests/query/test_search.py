import uuid

import pytest
from httpx import AsyncClient

from api.db.engine import db_session
from api.db.models.chunk_model import DocumentChunk
from api.db.models.project_model import Book, Project
from api.retrieval import repository

pytestmark = pytest.mark.models


async def test_search_of_an_unknown_project_is_404(client: AsyncClient):
    response = await client.get(
        "/api/search", params={"project_id": str(uuid.uuid4()), "q": "anything"}
    )

    assert response.status_code == 404


async def test_search_on_empty_project_returns_no_chunks(
    client: AsyncClient, project: Project
):
    response = await client.get(
        "/api/search", params={"project_id": str(project.id), "q": "anything"}
    )

    assert response.status_code == 200
    assert response.json() == {"chunks": [], "tier": None}


async def test_search_finds_a_seeded_chunk_with_both_scores(
    client: AsyncClient, project: Project, book: Book
):
    """S2.9: the endpoint is real hybrid retrieval, not a stubbed literal."""
    text = "Elizabeth Bennet danced with Mr. Darcy at the Netherfield ball."
    embedding = repository.embed_query(text)

    async with db_session() as session:
        chunk = DocumentChunk(
            book_id=book.id,
            text=text,
            pages=[10],
            page_start=10,
            page_end=10,
            text_embedding=embedding,
        )
        session.add(chunk)
        await session.commit()

    response = await client.get(
        "/api/search",
        params={"project_id": str(project.id), "q": "Darcy dancing at the ball"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["chunks"]) == 1
    result = body["chunks"][0]
    assert result["text"] == text
    assert result["page_start"] == 10
    assert result["dense_score"] is not None
