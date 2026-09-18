import uuid

from api.graph import client, projection

from . import fixtures


async def test_reset_clears_one_book_and_leaves_no_orphans(clean_project: str):
    """S1.4 acceptance: 200 nodes and 900 edges out, zero orphans left behind."""
    book_id = await fixtures.create_book(clean_project, series_order=1)
    character_ids = await fixtures.create_characters(
        clean_project, book_id, count=200, series_order=1, prefix="Solo"
    )
    await fixtures.create_relations(
        character_ids, count=900, book_ids=[book_id], series_order=1
    )

    before = await fixtures.count_nodes(clean_project)
    assert before["characters"] == 200
    assert before["relations"] == 900

    counts = await projection.reset(book_id)

    after = await fixtures.count_nodes(clean_project)
    assert counts.relations_deleted == 900
    assert counts.characters_deleted == 200
    assert counts.books_deleted == 1
    assert after == {"characters": 0, "books": 0, "relations": 0, "appearances": 0}
    assert await fixtures.orphan_count(clean_project) == 0


async def test_reset_does_not_touch_another_project(clean_project: str):
    other_project = str(uuid.uuid4())
    try:
        book_id = await fixtures.create_book(clean_project, series_order=1)
        ids = await fixtures.create_characters(
            clean_project, book_id, count=10, series_order=1, prefix="Target"
        )
        await fixtures.create_relations(
            ids, count=20, book_ids=[book_id], series_order=1
        )

        other_book = await fixtures.create_book(other_project, series_order=1)
        other_ids = await fixtures.create_characters(
            other_project, other_book, count=10, series_order=1, prefix="Bystander"
        )
        await fixtures.create_relations(
            other_ids, count=20, book_ids=[other_book], series_order=1
        )

        await projection.reset(book_id)

        assert await fixtures.count_nodes(other_project) == {
            "characters": 10,
            "books": 1,
            "relations": 20,
            "appearances": 10,
        }
    finally:
        await projection.reset_project(other_project)


async def test_reset_keeps_characters_that_appear_in_another_volume(
    clean_project: str,
):
    """A series character outlives the volume being re-ingested."""
    book_one = await fixtures.create_book(clean_project, series_order=1, title="One")
    book_two = await fixtures.create_book(clean_project, series_order=2, title="Two")

    recurring = await fixtures.create_characters(
        clean_project, book_one, count=5, series_order=1, prefix="Recurring"
    )
    for character_id in recurring:
        await fixtures.add_appearance(character_id, book_two, series_order=2)

    only_in_one = await fixtures.create_characters(
        clean_project, book_one, count=7, series_order=1, prefix="Walk-on"
    )

    await projection.reset(book_one)

    counts = await fixtures.count_nodes(clean_project)
    assert counts["characters"] == 5
    assert counts["books"] == 1
    assert await fixtures.orphan_count(clean_project) == 0

    result = await client.execute(
        "MATCH (c:Character) WHERE c.id IN $ids "
        "RETURN collect(c.appears_in_books) AS orders",
        ids=recurring,
    )
    assert all(orders == [2] for orders in result.records[0]["orders"])

    result = await client.execute(
        "MATCH (c:Character) WHERE c.id IN $ids RETURN count(c) AS remaining",
        ids=only_in_one,
    )
    assert result.records[0]["remaining"] == 0


async def test_reset_detaches_a_shared_edge_instead_of_deleting_it(
    clean_project: str,
):
    """An edge a later volume also establishes is trimmed, not dropped."""
    book_one = await fixtures.create_book(clean_project, series_order=1, title="One")
    book_two = await fixtures.create_book(clean_project, series_order=2, title="Two")

    pair = await fixtures.create_characters(
        clean_project, book_one, count=2, series_order=1, prefix="Pair"
    )
    for character_id in pair:
        await fixtures.add_appearance(character_id, book_two, series_order=2)

    shared = await fixtures.create_relations(
        pair,
        count=1,
        book_ids=[book_one, book_two],
        series_order=1,
    )
    book_one_only = await fixtures.create_relations(
        pair, count=1, book_ids=[book_one], series_order=1, predicate="rival_of"
    )

    counts = await projection.reset(book_one)

    assert counts.relations_deleted == 1
    assert counts.relations_detached == 1

    result = await client.execute(
        "MATCH ()-[r:RELATED]->() WHERE r.id = $id "
        "RETURN r.book_refs AS refs, r.page_refs AS pages, r.stale AS stale",
        id=shared[0],
    )
    record = result.records[0]
    assert record["refs"] == [book_two]
    assert record["pages"] == []
    assert record["stale"] is True

    result = await client.execute(
        "MATCH ()-[r:RELATED]->() WHERE r.id = $id RETURN count(r) AS remaining",
        id=book_one_only[0],
    )
    assert result.records[0]["remaining"] == 0


async def test_reset_on_an_unknown_book_is_a_no_op():
    counts = await projection.reset(uuid.uuid4())

    assert counts.books_deleted == 0
    assert counts.relations_deleted == 0
