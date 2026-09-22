"""S2.9 acceptance: both retrieval arms return sane results, RRF measured
against each on the 15-question smoke set (``retrieval_smoke.json``).

Real Postgres, real BGE-M3 embeddings (CPU) — no mocks, per ``api/AGENTS.md``.
Whether RRF actually beats either lone arm is not asserted here: the brief
allows for "no" as a valid answer, provided it is recorded rather than
buried (see ``plans/sprint-2/RETRO.md``). What *is* asserted is the other
half of the acceptance criterion — both arms work at all on this corpus.
"""

import json
from pathlib import Path
from uuid import UUID

import pytest

from api.db.models.chunk_model import DocumentChunk
from api.db.models.project_model import Book, Project
from api.retrieval import repository
from api.retrieval.hybrid import _reciprocal_rank_fusion

pytestmark = pytest.mark.models

_FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "retrieval_smoke.json"
FIXTURE = json.loads(_FIXTURE_PATH.read_text())


@pytest.fixture
async def seeded_chunks(session, book: Book) -> dict[str, UUID]:
    """Insert the smoke-set chunks into ``book`` with real BGE-M3 embeddings."""
    key_to_id: dict[str, UUID] = {}

    for index, item in enumerate(FIXTURE["chunks"], start=1):
        embedding = repository.embed_query(item["text"])
        chunk = DocumentChunk(
            book_id=book.id,
            text=item["text"],
            pages=[index],
            page_start=index,
            page_end=index,
            text_embedding=embedding,
        )
        session.add(chunk)
        await session.flush()
        key_to_id[item["key"]] = chunk.id

    await session.commit()

    return key_to_id


def _recall_at_k(
    retrieved: list[list[str]], relevant: list[list[str]], k: int
) -> float:
    hits = sum(
        1
        for got, expected in zip(retrieved, relevant, strict=True)
        if set(got[:k]) & set(expected)
    )

    return hits / len(relevant)


async def test_both_arms_return_sane_results_and_rrf_is_measured(
    session, project: Project, seeded_chunks: dict[str, UUID]
):
    id_to_key = {chunk_id: key for key, chunk_id in seeded_chunks.items()}

    dense_hits: list[list[str]] = []
    lexical_hits: list[list[str]] = []
    rrf_hits: list[list[str]] = []
    relevant: list[list[str]] = []

    for query in FIXTURE["queries"]:
        embedding = repository.embed_query(query["question"])

        dense = await repository.dense_search(
            session, project_id=project.id, query_embedding=embedding, limit=50
        )
        lexical = await repository.lexical_search(
            session, project_id=project.id, query=query["question"], limit=50
        )
        fused = _reciprocal_rank_fusion(dense, lexical)

        dense_hits.append([id_to_key[chunk.id] for chunk, _ in dense])
        lexical_hits.append([id_to_key[chunk.id] for chunk, _ in lexical])
        rrf_hits.append([id_to_key[chunk_id] for chunk_id, *_ in fused])
        relevant.append(query["relevant"])

    dense_recall = _recall_at_k(dense_hits, relevant, 5)
    lexical_recall = _recall_at_k(lexical_hits, relevant, 5)
    rrf_recall = _recall_at_k(rrf_hits, relevant, 5)

    print(
        f"\nrecall@5 over {len(relevant)} queries — "
        f"dense={dense_recall:.3f} lexical={lexical_recall:.3f} rrf={rrf_recall:.3f}"
    )

    # Sanity: both arms work at all on this corpus. Whether RRF beats either
    # one is a measurement, recorded in plans/sprint-2/RETRO.md, not a gate.
    assert dense_recall > 0
    assert lexical_recall > 0


async def test_project_scoping_excludes_another_projects_chunks(
    session, project: Project, book: Book
):
    """A chunk in a different project must never surface in this project's search."""
    other_project = Project(name="Other", slug="other-project-scoping")
    session.add(other_project)
    await session.flush()

    other_book = Book(
        project_id=other_project.id,
        title="Someone else's book",
        content_hash="other-hash-scoping",
    )
    session.add(other_book)
    await session.flush()

    embedding = repository.embed_query("a sentence about a spaceship and lasers")
    foreign_chunk = DocumentChunk(
        book_id=other_book.id,
        text="A sentence about a spaceship and lasers, from another project entirely.",
        pages=[1],
        page_start=1,
        page_end=1,
        text_embedding=embedding,
    )
    session.add(foreign_chunk)
    await session.commit()

    dense = await repository.dense_search(
        session, project_id=project.id, query_embedding=embedding, limit=50
    )
    lexical = await repository.lexical_search(
        session, project_id=project.id, query="spaceship lasers", limit=50
    )

    assert all(chunk.id != foreign_chunk.id for chunk, _ in dense)
    assert all(chunk.id != foreign_chunk.id for chunk, _ in lexical)

    await session.delete(foreign_chunk)
    await session.delete(other_book)
    await session.delete(other_project)
    await session.commit()
