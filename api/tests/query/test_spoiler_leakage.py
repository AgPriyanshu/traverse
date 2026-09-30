import uuid

import pytest

from api.contracts.enums import RelationFamily
from api.db.models.character_model import Character
from api.db.models.project_model import Book, Chapter
from api.db.models.relation_model import RelationEvidence
from api.graph import projection
from api.graph import queries as graph_queries
from api.graph import repository as graph_repository
from api.query.scope import ReadingScope
from api.query.templates import TemplateId, run_template
from api.retrieval import repository as retrieval_repository
from api.tests.query.conftest import (
    make_character,
    make_chunk,
    make_relation,
    project_now,
)


async def _set_first_seen(
    session, character: Character, *, book_id, chapter: int
) -> None:
    stored = await session.get(Character, character.id)
    stored.first_book_id = book_id
    stored.first_chapter = chapter
    session.add(stored)
    await session.commit()


@pytest.mark.asyncio
async def test_spoiler_leakage_rate_is_zero_across_every_read_surface(
    session, project, book
):
    # Reading position under test: book one, chapter two. Anything at or
    # before this is "past"; anything after is "the future" and must never
    # surface through any of the checks below.
    scope = ReadingScope(book_order=1, chapter=2)

    book2 = Book(
        project_id=project.id,
        title="Book Two",
        content_hash=uuid.uuid4().hex,
        series_order=2,
    )
    session.add(book2)
    await session.commit()
    await session.refresh(book2)

    past = await make_character(session, project, name="Early Ann")
    present = await make_character(session, project, name="Mid Ben")
    future_same_book = await make_character(session, project, name="Future Cora")
    future_next_book = await make_character(session, project, name="Future Dara")

    await _set_first_seen(session, past, book_id=book.id, chapter=1)
    await _set_first_seen(session, present, book_id=book.id, chapter=2)
    await _set_first_seen(session, future_same_book, book_id=book.id, chapter=3)
    await _set_first_seen(session, future_next_book, book_id=book2.id, chapter=1)

    chapter_three = Chapter(book_id=book.id, number=3, page_start=25, page_end=40)
    session.add(chapter_three)
    await session.commit()
    await session.refresh(chapter_three)

    # Visible edge, reasserted with a future evidence item — the edge itself
    # must stay visible, but the chapter-3 evidence must not.
    visible_edge = await make_relation(
        session,
        project,
        book,
        subject=past,
        predicate="friend_of",
        obj=present,
        family=RelationFamily.SOCIAL,
        quote="Ann and Ben became friends.",
        first_book_order=1,
        first_chapter=2,
    )
    future_evidence_chunk = await make_chunk(
        session,
        book,
        text="Ann and Ben's friendship deepened.",
        page=30,
        chapter_id=chapter_three.id,
    )
    session.add(
        RelationEvidence(
            relation_id=visible_edge.id,
            book_id=book.id,
            chunk_id=future_evidence_chunk.id,
            book_order=1,
            chapter_no=3,
            page_start=30,
            page_end=30,
            quote="Ann and Ben's friendship deepened.",
        )
    )
    await session.commit()

    # Same pair, predicate changes later — an arc state that must not surface.
    await make_relation(
        session,
        project,
        book,
        subject=past,
        predicate="married_to",
        obj=present,
        family=RelationFamily.ROMANTIC,
        quote="Ann and Ben married.",
        first_book_order=1,
        first_chapter=3,
    )

    # Edges entirely in the future — same book, later chapter; and next book.
    hidden_edge_same_book = await make_relation(
        session,
        project,
        book,
        subject=past,
        predicate="rival_of",
        obj=future_same_book,
        family=RelationFamily.SOCIAL,
        quote="Ann and Cora became rivals.",
        first_book_order=1,
        first_chapter=3,
    )
    hidden_edge_next_book = await make_relation(
        session,
        project,
        book2,
        subject=past,
        predicate="enemy_of",
        obj=future_next_book,
        family=RelationFamily.SOCIAL,
        quote="Ann and Dara became enemies.",
        first_book_order=2,
        first_chapter=1,
    )

    await project_now(session, project.id)

    leaked: list[str] = []
    checks = 0

    def record(label: str, condition: bool) -> None:
        nonlocal checks
        checks += 1
        if condition:
            leaked.append(label)

    try:
        # 1. Roster.
        roster = await graph_repository.list_characters(
            session, project.id, scope=scope
        )
        roster_ids = {c.id for c in roster}
        record("roster: future same-book character", future_same_book.id in roster_ids)
        record("roster: future next-book character", future_next_book.id in roster_ids)

        # 2. Character detail (deep link).
        record(
            "get_character: future same-book character not hidden",
            await graph_repository.get_character(
                session, future_same_book.id, scope=scope
            )
            is not None,
        )
        record(
            "get_character: future next-book character not hidden",
            await graph_repository.get_character(
                session, future_next_book.id, scope=scope
            )
            is not None,
        )

        # 3. Whole-project graph (Neo4j).
        graph = await graph_queries.get_graph(session, project.id, scope=scope)
        node_ids = {n.id for n in graph.nodes}
        edge_predicates = {e.predicate for e in graph.edges}
        record("get_graph: future same-book node", future_same_book.id in node_ids)
        record("get_graph: future next-book node", future_next_book.id in node_ids)
        record("get_graph: hidden same-book edge", "rival_of" in edge_predicates)
        record("get_graph: hidden next-book edge", "enemy_of" in edge_predicates)
        visible_graph_edge = next(
            (e for e in graph.edges if e.predicate == "friend_of"), None
        )
        record(
            "get_graph: visible edge's page_refs include future evidence",
            visible_graph_edge is not None
            and any(p.page == 30 for p in visible_graph_edge.page_refs),
        )

        # 4. Neighbourhood (Neo4j).
        hood = await graph_queries.get_neighbourhood(session, past.id, 2, scope=scope)
        hood_ids = {n.id for n in hood.nodes}
        hood_predicates = {e.predicate for e in hood.edges}
        record(
            "get_neighbourhood: future same-book node",
            future_same_book.id in hood_ids,
        )
        record(
            "get_neighbourhood: future next-book node",
            future_next_book.id in hood_ids,
        )
        record("get_neighbourhood: hidden edge", "rival_of" in hood_predicates)

        # 5. Shortest path to a not-yet-visible character.
        path = await graph_queries.shortest_path(
            session, past.id, future_same_book.id, 4, scope=scope
        )
        record("shortest_path: found a path to a future character", path.found)

        # 6. Relationship-lookup template (Cypher-level filter).
        rows = await run_template(
            TemplateId.RELATIONSHIP_LOOKUP,
            subject_id=str(past.id),
            object_id=str(future_same_book.id),
            project_id=str(project.id),
            lbo=scope.book_order,
            lch=scope.chapter,
        )
        record("relationship_lookup template: found a future edge", bool(rows))

        # 7. relations_out — Postgres-side hydration filter and evidence trim.
        relations = await graph_repository.relations_out(
            session,
            [visible_edge.id, hidden_edge_same_book.id, hidden_edge_next_book.id],
            scope=scope,
        )
        relations_by_id = {r.id: r for r in relations}
        record(
            "relations_out: hidden same-book edge returned",
            hidden_edge_same_book.id in relations_by_id,
        )
        record(
            "relations_out: hidden next-book edge returned",
            hidden_edge_next_book.id in relations_by_id,
        )
        # Not a leak check — a sanity check that filtering isn't overzealous
        # and dropping the edge that *is* visible.
        visible_relation = relations_by_id.get(visible_edge.id)
        assert visible_relation is not None, "visible edge was wrongly hidden"
        record(
            "relations_out: visible edge's page_refs include future evidence",
            any(p.page == 30 for p in visible_relation.page_refs),
        )

        # 8. relation_arc — a later state must be dropped, not redacted.
        arc = await graph_repository.relation_arc(
            session, past.id, present.id, scope=scope
        )
        arc_predicates = {s.predicate for s in arc.states}
        record(
            "relation_arc: future state (married_to) present",
            "married_to" in arc_predicates,
        )
        assert "friend_of" in arc_predicates, "visible arc state was wrongly hidden"

        # 9. Evidence hydration — a relation reasserted later must not cite it.
        evidence = await graph_repository.list_evidence(
            session, visible_edge.id, limit=10, offset=0, scope=scope
        )
        record(
            "list_evidence: future evidence row (page 30) returned",
            evidence is not None and any(e.page_start == 30 for e in evidence),
        )

        # 10. Aggregation template + hydration — anchor's future relations.
        agg_rows = await run_template(
            TemplateId.AGGREGATION,
            anchor_id=str(past.id),
            project_id=str(project.id),
            predicate="rival_of",
            inverse_predicate="rival_of",
            lbo=scope.book_order,
            lch=scope.chapter,
        )
        record("aggregation template: found a future edge", bool(agg_rows))

        # 11. Retrieval — a chunk whose chapter is beyond the reading position.
        future_query_embedding = retrieval_repository.embed_query("friendship deepened")
        dense = await retrieval_repository.dense_search(
            session,
            project_id=project.id,
            query_embedding=future_query_embedding,
            scope=scope,
            limit=50,
        )
        record(
            "dense_search: future-chapter chunk returned",
            any(chunk.id == future_evidence_chunk.id for chunk, _ in dense),
        )
        lexical = await retrieval_repository.lexical_search(
            session,
            project_id=project.id,
            query="friendship deepened",
            scope=scope,
            limit=50,
        )
        record(
            "lexical_search: future-chapter chunk returned",
            any(chunk.id == future_evidence_chunk.id for chunk, _ in lexical),
        )
    finally:
        await projection.reset_project(project.id)

    leakage_rate = len(leaked) / checks
    print(
        f"\nspoiler leakage: {len(leaked)}/{checks} checks leaked "
        f"(rate={leakage_rate:.3f})"
    )
    if leaked:
        print("leaked checks:\n  " + "\n  ".join(leaked))

    assert leakage_rate == 0.0, leaked
