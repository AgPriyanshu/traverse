import uuid

from httpx import AsyncClient

from api.contracts.api import GraphOut, OntologyOut
from api.contracts.enums import RelationFamily
from api.db.models.project_model import Book, Project
from api.graph import ontology


async def test_roster_of_an_empty_project_is_an_empty_list(
    client: AsyncClient, project: Project
):
    """S1.7: a real query against real, empty tables — not a stubbed literal."""
    response = await client.get(f"/api/projects/{project.id}/characters")

    assert response.status_code == 200
    assert response.json() == []


async def test_roster_of_an_unknown_project_is_404(client: AsyncClient):
    """An empty list means "no characters yet"; a typo must not look the same."""
    response = await client.get(f"/api/projects/{uuid.uuid4()}/characters")

    assert response.status_code == 404


async def test_roster_filters_are_accepted_on_empty_tables(
    client: AsyncClient, project: Project, book: Book
):
    response = await client.get(
        f"/api/projects/{project.id}/characters",
        params={
            "tier": "protagonist",
            "q": "Elizabeth",
            "book_id": str(book.id),
            "limit_book_order": 1,
            "limit_chapter": 12,
        },
    )

    assert response.status_code == 200
    assert response.json() == []


async def test_unknown_character_is_404(client: AsyncClient):
    response = await client.get(f"/api/characters/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_empty_graph_has_no_nodes_or_edges(client: AsyncClient, project: Project):
    response = await client.get(f"/api/projects/{project.id}/graph")

    assert response.status_code == 200
    payload = GraphOut.model_validate(response.json())
    assert payload.nodes == []
    assert payload.edges == []
    assert payload.truncated is False


async def test_graph_of_an_unknown_project_is_404(client: AsyncClient):
    response = await client.get(f"/api/projects/{uuid.uuid4()}/graph")

    assert response.status_code == 404


async def test_graph_filters_are_accepted_on_empty_tables(
    client: AsyncClient, project: Project, book: Book
):
    response = await client.get(
        f"/api/projects/{project.id}/graph",
        params={
            "book_id": str(book.id),
            "families": ["kinship", "romantic"],
            "min_confidence": 0.5,
            "limit_book_order": 1,
            "limit_chapter": 3,
        },
    )

    assert response.status_code == 200
    assert GraphOut.model_validate(response.json()).edges == []


async def test_ontology_endpoint_serves_the_whole_registry(client: AsyncClient):
    """FE1 builds edge-family colours and filters from this before any edge exists."""
    response = await client.get("/api/graph/ontology")

    assert response.status_code == 200
    payload = OntologyOut.model_validate(response.json())
    assert len(payload.predicates) == len(ontology.PREDICATES)
    assert set(payload.families) == set(RelationFamily)

    by_name = {item.predicate: item for item in payload.predicates}
    assert by_name["sibling_of"].symmetric is True
    assert by_name["parent_of"].inverse == "child_of"
    assert by_name["unrequited_love_for"].inverse is None


async def test_ontology_endpoint_tracks_the_yaml():
    """The endpoint is the file, not a copy of it."""
    from api.routes.graph import get_ontology

    assert await get_ontology() == ontology.load().to_contract()


async def test_query_and_review_are_still_501(client: AsyncClient, project: Project):
    """Sprint 1 freezes these paths and their models; the handlers land later."""
    ask = await client.post(
        "/api/query",
        json={"project_id": str(project.id), "question": "who is Darcy?"},
    )
    tasks = await client.get("/api/review/tasks")
    resolve = await client.post(
        f"/api/review/tasks/{uuid.uuid4()}/resolve",
        json={"decision": "accept", "payload": {}},
    )

    assert ask.status_code == 501
    assert tasks.status_code == 501
    assert resolve.status_code == 501
