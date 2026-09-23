import uuid
from types import SimpleNamespace

import pytest

from api.contracts.enums import AssertionType, RelationFamily
from api.db.models import (
    Character,
    CharacterAppearance,
    Relation,
    RelationEvidence,
)
from api.db.models.chunk_model import DocumentChunk
from api.graph import client, projection, queries, repository, upsert


def test_edge_without_evidence_raises_before_anything_is_projected():
    relation = SimpleNamespace(id=uuid.uuid4(), predicate="friend_of")

    with pytest.raises(upsert.EvidenceRequiredError):
        upsert.build_edge_rows(uuid.uuid4(), [{"relation": relation, "evidence": []}])


async def _seed(session, project, book):
    chunk = DocumentChunk(
        book_id=book.id,
        text="Darcy married Elizabeth.",
        pages=[7],
        page_start=7,
        page_end=7,
    )
    session.add(chunk)
    people = [
        Character(project_id=project.id, canonical_name=n)
        for n in ("Darcy", "Elizabeth", "Georgiana")
    ]
    session.add_all(people)
    await session.commit()
    for p in people:
        session.add(CharacterAppearance(character_id=p.id, book_id=book.id))
    darcy, eliza, george = people
    rels = []
    for subj, pred, obj in (
        (darcy, "married_to", eliza),
        (darcy, "parent_of", george),
    ):
        rel = Relation(
            project_id=project.id,
            subject_character_id=subj.id,
            object_character_id=obj.id,
            predicate=pred,
            family=RelationFamily.ROMANTIC
            if pred == "married_to"
            else RelationFamily.KINSHIP,
            confidence=0.8,
            evidence_count=1,
        )
        session.add(rel)
        await session.flush()
        session.add(
            RelationEvidence(
                relation_id=rel.id,
                book_id=book.id,
                chunk_id=chunk.id,
                chapter_no=1,
                page_start=7,
                page_end=7,
                quote="Darcy married Elizabeth.",
                assertion_type=AssertionType.NARRATED,
            )
        )
        rels.append(rel)
    await session.commit()

    return people, rels


@pytest.mark.asyncio
async def test_projection_reads_and_rebuild_is_byte_identical(session, project, book):
    people, rels = await _seed(session, project, book)
    darcy, eliza, george = people
    try:
        counts = await upsert.upsert_project(session, project.id)
        first = await upsert.snapshot(project.id)

        assert counts["edges"] == 4
        async with client.session() as neo:
            record = await (
                await neo.run(
                    "MATCH ()-[r:RELATED {project_id: $p}]->() "
                    "WHERE r.evidence_count = 0 RETURN count(r) AS n",
                    p=str(project.id),
                )
            ).single()
        assert record["n"] == 0

        graph = await queries.get_graph(session, project.id)
        assert len(graph.edges) == 2 and len(graph.nodes) == 3
        assert graph.edges[0].page_refs[0].page == 7

        hood = await queries.get_neighbourhood(george.id, 2)
        assert {n.canonical_name for n in hood.nodes} == {
            "Darcy",
            "Elizabeth",
            "Georgiana",
        }

        path = await queries.shortest_path(session, george.id, eliza.id, 4)
        assert path.found and len(path.hops) == 2

        await projection.reset_project(project.id)
        await upsert.upsert_project(session, project.id)
        assert await upsert.snapshot(project.id) == first

        evidence = await repository.list_evidence(
            session, rels[0].id, limit=10, offset=0
        )
        assert evidence and evidence[0].page_start == 7
        arc = await repository.relation_arc(session, eliza.id, darcy.id)
        assert len(arc.states) == 1
    finally:
        await projection.reset_project(project.id)
