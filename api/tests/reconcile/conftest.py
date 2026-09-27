import uuid
from uuid import UUID

import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import (
    CandidateKind,
    ImportanceTier,
    ProjectKind,
    ResolutionMethod,
)
from api.db.models import Book, DocumentChunk, Project
from api.extraction import repository as extraction_repository


@pytest_asyncio.fixture
async def series_project(session: SQLModelAsyncSession) -> Project:
    row = Project(
        name="Anne of Green Gables",
        slug=f"anne-{uuid.uuid4().hex[:8]}",
        kind=ProjectKind.SERIES,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return row


async def make_book(
    session: SQLModelAsyncSession, project: Project, *, series_order: int
) -> Book:
    row = Book(
        project_id=project.id,
        title=f"Book {series_order}",
        content_hash=uuid.uuid4().hex,
        series_order=series_order,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return row


async def make_chunk(
    session: SQLModelAsyncSession, book: Book, *, page: int = 1
) -> UUID:
    """A placeholder chunk so ``CharacterMention.chunk_id`` has something to cite."""
    row = DocumentChunk(
        book_id=book.id,
        text=f"Placeholder text for {book.title}, page {page}.",
        pages=[page],
        page_start=page,
        page_end=page,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return row.id


def ctx(page: int, text: str, chunk_id: UUID) -> dict:
    return {
        "chunk_id": str(chunk_id),
        "page": page,
        "chapter_number": None,
        "context": text,
        "count": 1,
    }


async def ingest_book_roster(
    session: SQLModelAsyncSession,
    *,
    book: Book,
    project: Project,
    characters: list[dict],
) -> None:
    """Stand in for ``resolve_aliases``: persist a book's already-resolved roster.

    Bypasses the alias cascade and attribute-extraction LLM calls entirely --
    those are Sprint 3's own tested surface. This directly exercises
    ``persist_characters`` and ``set_resolved_character_ids`` the same way
    ``pipeline.tasks._resolve_aliases`` does, so ``reconcile_book`` sees
    exactly the shape it sees in production.

    Args:
        characters: One dict per resolved character:
            ``canonical_name``, ``aliases``, ``tier``, ``mention_count``,
            ``contexts`` (list of :func:`ctx` dicts).
    """
    candidate_rows = []
    for character in characters:
        candidate_rows.append(
            {
                "surface_form": character["canonical_name"],
                "kind": CandidateKind.PERSON,
                "mention_count": character["mention_count"],
                "contexts": character["contexts"],
            }
        )
    await extraction_repository.replace_candidates(session, book.id, candidate_rows)
    candidates = await extraction_repository.list_candidates(session, book.id)
    candidate_by_name = {c.surface_form: c for c in candidates}

    rows = []
    for character in characters:
        contexts = character["contexts"]
        pages = [c["page"] for c in contexts] or [1]
        rows.append(
            {
                "canonical_name": character["canonical_name"],
                "aliases": character["aliases"],
                "importance_tier": character.get("tier", ImportanceTier.MINOR),
                "first_page": min(pages),
                "first_chapter": None,
                "last_page": max(pages),
                "last_chapter": None,
                "mention_count": character["mention_count"],
                "attributes": {},
                "collision_suspected": False,
                "mentions": [
                    {
                        "chunk_id": c["chunk_id"],
                        "surface_form": character["canonical_name"],
                        "page": c["page"],
                        "resolution_method": ResolutionMethod.EXACT,
                    }
                    for c in contexts
                ],
            }
        )

    await extraction_repository.delete_book_characters(session, book.id)
    persisted = await extraction_repository.persist_characters(
        session, book.id, project.id, rows
    )
    await extraction_repository.sweep_orphaned_characters(session, project.id)

    persisted_by_name = {c.canonical_name: c.id for c in persisted}
    candidate_character_ids = {
        candidate_by_name[character["canonical_name"]].id: persisted_by_name[
            character["canonical_name"]
        ]
        for character in characters
    }
    await extraction_repository.set_resolved_character_ids(
        session, candidate_character_ids
    )
