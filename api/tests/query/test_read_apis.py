import uuid

from httpx import AsyncClient

from api.contracts.api import CharacterDetailOut, GraphOut, MentionOut, OntologyOut
from api.contracts.enums import ImportanceTier, RelationFamily, ResolutionMethod
from api.db.engine import db_session
from api.db.models.character_model import Character, CharacterMention
from api.db.models.chunk_model import DocumentChunk
from api.db.models.project_model import Book, Chapter, Project
from api.graph import ontology


async def _seeded_character(
    project: Project, book: Book, *, series_order: int | None = None
) -> tuple[Character, list[CharacterMention]]:
    """A character with mentions across two chapters, for the read-path tests.

    Uses its own session, matching this file's ``project``/``book`` fixture
    convention (`api/tests/query/conftest.py`) rather than the root
    conftest's ``session`` fixture — mixing the two against the same rows
    produces exactly the kind of cross-session teardown conflict this avoids.

    Args:
        project: Owning project, from the ``project`` fixture.
        book: Owning book, from the ``book`` fixture.
        series_order: Set on ``book`` first when a test needs a real reading
            position to filter against — the fixture's default is ``None``
            ("no restriction"), which is the wrong fixture for a test that
            means to exercise ``limit_book_order``/``limit_chapter``.
    """
    async with db_session() as session:
        if series_order is not None:
            stored_book = await session.get(Book, book.id)
            stored_book.series_order = series_order
            session.add(stored_book)

        chapter_one = Chapter(book_id=book.id, number=1, page_start=1, page_end=5)
        chapter_two = Chapter(book_id=book.id, number=2, page_start=6, page_end=10)
        session.add(chapter_one)
        session.add(chapter_two)
        await session.flush()

        chunk_one = DocumentChunk(
            book_id=book.id,
            chapter_id=chapter_one.id,
            text="p1",
            pages=[1],
            page_start=1,
            page_end=1,
        )
        chunk_two = DocumentChunk(
            book_id=book.id,
            chapter_id=chapter_two.id,
            text="p7",
            pages=[7],
            page_start=7,
            page_end=7,
        )
        session.add(chunk_one)
        session.add(chunk_two)
        await session.flush()

        character = Character(
            project_id=project.id,
            canonical_name="Elizabeth Bennet",
            importance_tier=ImportanceTier.PROTAGONIST,
            first_book_id=book.id,
            first_chapter=1,
            first_page=1,
            attributes={
                "occupation": [{"value": "none", "book_id": str(book.id), "page": 1}]
            },
        )
        session.add(character)
        await session.flush()

        mentions = [
            CharacterMention(
                character_id=character.id,
                book_id=book.id,
                chunk_id=chunk_one.id,
                surface_form="Elizabeth",
                page=1,
                resolution_method=ResolutionMethod.EXACT,
            ),
            CharacterMention(
                character_id=character.id,
                book_id=book.id,
                chunk_id=chunk_one.id,
                surface_form="Lizzy",
                page=1,
                resolution_method=ResolutionMethod.NICKNAME,
            ),
            CharacterMention(
                character_id=character.id,
                book_id=book.id,
                chunk_id=chunk_two.id,
                surface_form="Elizabeth",
                page=7,
                resolution_method=ResolutionMethod.EXACT,
            ),
        ]
        for mention in mentions:
            session.add(mention)
        await session.commit()
        await session.refresh(character)
        for mention in mentions:
            await session.refresh(mention)

        return character, mentions


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


async def test_get_character_returns_aliases_attributes_and_histogram(
    client: AsyncClient, project: Project, book: Book
):
    """S3.6: alias detail, attributes and a per-chapter histogram, one query each."""
    character, _mentions = await _seeded_character(project, book)

    response = await client.get(f"/api/characters/{character.id}")

    assert response.status_code == 200
    payload = CharacterDetailOut.model_validate(response.json())
    assert payload.mentions_per_chapter == {"1": 2, "2": 1}
    surface_forms = {alias.surface_form for alias in payload.alias_detail}
    assert surface_forms == {"Elizabeth", "Lizzy"}
    by_form = {alias.surface_form: alias for alias in payload.alias_detail}
    assert by_form["Elizabeth"].count == 2
    assert by_form["Lizzy"].count == 1
    assert len(payload.attributes) == 1
    assert payload.attributes[0].label == "occupation"


async def test_get_character_hidden_before_its_first_appearance_is_404(
    client: AsyncClient, project: Project, book: Book
):
    """A deep link cannot bypass the same spoiler gate ``list_characters`` applies."""
    character, _mentions = await _seeded_character(project, book, series_order=1)

    response = await client.get(
        f"/api/characters/{character.id}",
        params={"limit_book_order": 1, "limit_chapter": 0},
    )

    assert response.status_code == 404


async def test_list_mentions_paginates_and_orders_by_page(
    client: AsyncClient, project: Project, book: Book
):
    character, _mentions = await _seeded_character(project, book)

    first_page = await client.get(
        f"/api/characters/{character.id}/mentions", params={"limit": 2, "offset": 0}
    )
    second_page = await client.get(
        f"/api/characters/{character.id}/mentions", params={"limit": 2, "offset": 2}
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    first = [MentionOut.model_validate(item) for item in first_page.json()]
    second = [MentionOut.model_validate(item) for item in second_page.json()]
    assert [m.page for m in first] == [1, 1]
    assert [m.page for m in second] == [7]


async def test_list_mentions_respects_chapter_limit(
    client: AsyncClient, project: Project, book: Book
):
    character, _mentions = await _seeded_character(project, book, series_order=1)

    response = await client.get(
        f"/api/characters/{character.id}/mentions",
        params={"limit_book_order": 1, "limit_chapter": 1},
    )

    assert response.status_code == 200
    mentions = [MentionOut.model_validate(item) for item in response.json()]
    assert all(m.page == 1 for m in mentions)


async def test_list_mentions_unknown_character_is_404(client: AsyncClient):
    response = await client.get(f"/api/characters/{uuid.uuid4()}/mentions")

    assert response.status_code == 404


async def test_merge_endpoint_combines_characters(
    client: AsyncClient, project: Project, book: Book
):
    target, _target_mentions = await _seeded_character(project, book)
    async with db_session() as session:
        source = Character(
            project_id=project.id, canonical_name="Miss Elizabeth Bennet"
        )
        session.add(source)
        await session.commit()
        await session.refresh(source)

    response = await client.post(
        "/api/characters/merge",
        json={"source_ids": [str(source.id)], "target_id": str(target.id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(target.id)
    assert "Miss Elizabeth Bennet" in body["aliases"]

    missing = await client.get(f"/api/characters/{source.id}")
    assert missing.status_code == 404


async def test_merge_endpoint_rejects_target_in_sources(
    client: AsyncClient, project: Project
):
    character_id = str(uuid.uuid4())
    response = await client.post(
        "/api/characters/merge",
        json={"source_ids": [character_id], "target_id": character_id},
    )

    assert response.status_code == 400


async def test_merge_endpoint_unknown_character_is_404(client: AsyncClient):
    response = await client.post(
        "/api/characters/merge",
        json={"source_ids": [str(uuid.uuid4())], "target_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404


async def test_split_endpoint_rejects_splitting_away_every_mention(
    client: AsyncClient, project: Project, book: Book
):
    character, mentions = await _seeded_character(project, book)

    response = await client.post(
        f"/api/characters/{character.id}/split",
        json={
            "mention_ids": [str(m.id) for m in mentions],
            "new_canonical_name": "Someone Else",
        },
    )

    assert response.status_code == 400


async def test_split_endpoint_moves_the_named_mentions(
    client: AsyncClient, project: Project, book: Book
):
    character, mentions = await _seeded_character(project, book)
    chapter_two_mention = next(m for m in mentions if m.page == 7)

    response = await client.post(
        f"/api/characters/{character.id}/split",
        json={
            "mention_ids": [str(chapter_two_mention.id)],
            "new_canonical_name": "Elizabeth (later chapters)",
        },
    )

    assert response.status_code == 200
    source_out, new_out = response.json()
    assert source_out["mention_count"] == 2
    assert new_out["mention_count"] == 1
    assert new_out["canonical_name"] == "Elizabeth (later chapters)"
