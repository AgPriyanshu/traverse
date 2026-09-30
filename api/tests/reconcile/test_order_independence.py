import hashlib
import json
import uuid

import pytest
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import ImportanceTier, ProjectKind
from api.db.models import Book, Character, CharacterAppearance, Project
from api.extraction import similarity
from api.reconcile import matching, service

from .conftest import ctx, ingest_book_roster, make_book, make_chunk


@pytest.fixture(autouse=True)
def _no_weak_signal_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    """This fixture's series is designed to converge through the
    deterministic stages alone (see ``_ROSTERS`` below) -- embedding and LLM
    are stubbed off so the test's determinism does not depend on a stub
    happening to agree with itself twice.
    """

    async def unavailable(text_a: str, text_b: str) -> None:
        return None

    async def says_different(prompt, schema, **kwargs):
        from api.extraction.schemas import AdjudicationOutput

        return AdjudicationOutput(same_person=False, confidence=0.9, reason="stub")

    monkeypatch.setattr(similarity, "context_similarity", unavailable)
    monkeypatch.setattr(matching, "structured_call", says_different)


async def _project_checksum(
    session: SQLModelAsyncSession, project_id: uuid.UUID
) -> str:
    """A deterministic fingerprint of a project's characters and appearances.

    Keyed on series position rather than book id, so the same underlying
    series checksums identically across two projects with different book
    rows -- book id is per-ingestion, series position is the series' own
    identity.
    """
    characters = (
        (
            await session.execute(
                select(Character).where(Character.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    books = {
        b.id: b
        for b in (
            await session.execute(select(Book).where(Book.project_id == project_id))
        )
        .scalars()
        .all()
    }

    payload = []
    for character in characters:
        appearances = (
            (
                await session.execute(
                    select(CharacterAppearance).where(
                        CharacterAppearance.character_id == character.id
                    )
                )
            )
            .scalars()
            .all()
        )
        appearance_payload = sorted(
            (
                {
                    "book_order": books[a.book_id].series_order,
                    "first_page": a.first_page,
                    "last_page": a.last_page,
                    "mention_count": a.mention_count,
                    "tier": a.importance_tier.value,
                    "surface_forms": sorted(a.surface_forms),
                }
                for a in appearances
            ),
            key=lambda d: d["book_order"],
        )
        payload.append(
            {
                "canonical_name": character.canonical_name,
                "aliases": sorted(character.aliases),
                "tier": character.importance_tier.value,
                "mention_count": character.mention_count,
                "first_book_order": (
                    books[character.first_book_id].series_order
                    if character.first_book_id
                    else None
                ),
                "last_book_order": (
                    books[character.last_book_id].series_order
                    if character.last_book_id
                    else None
                ),
                "appearances": appearance_payload,
            }
        )

    payload.sort(key=lambda p: (p["first_book_order"], p["canonical_name"]))
    encoded = json.dumps(payload, sort_keys=True).encode()

    return hashlib.sha256(encoded).hexdigest()


_ANNE_BOOK_1 = {
    "canonical_name": "Anne Shirley",
    "aliases": ["Anne Shirley", "Anne"],
    "tier": ImportanceTier.PROTAGONIST,
    "mention_count": 100,
    "page": 10,
    "text": "Anne Shirley arrived.",
}
_ANNE_BOOK_2 = {
    "canonical_name": "Anne Shirley",
    "aliases": ["Anne Shirley", "Anne"],
    "tier": ImportanceTier.PROTAGONIST,
    "mention_count": 90,
    "page": 20,
    "text": "Anne Shirley started school.",
}
_ANNE_BOOK_3 = {
    "canonical_name": "Miss Shirley",
    "aliases": ["Anne Shirley", "Miss Shirley"],
    "tier": ImportanceTier.MAJOR,
    "mention_count": 60,
    "page": 5,
    "text": "Miss Shirley took her post.",
}
_GILBERT_BOOK_1 = {
    "canonical_name": "Gilbert Blythe",
    "aliases": ["Gilbert Blythe", "Gilbert"],
    "tier": ImportanceTier.MAJOR,
    "mention_count": 40,
    "page": 15,
    "text": "Gilbert Blythe teased her.",
}
_GILBERT_BOOK_3 = {
    "canonical_name": "Gilbert Blythe",
    "aliases": ["Gilbert Blythe", "Gilbert"],
    "tier": ImportanceTier.MAJOR,
    "mention_count": 45,
    "page": 8,
    "text": "Gilbert Blythe smiled at her.",
}

_ROSTERS = {
    1: [_ANNE_BOOK_1, _GILBERT_BOOK_1],
    2: [_ANNE_BOOK_2],
    3: [_ANNE_BOOK_3, _GILBERT_BOOK_3],
}


async def _ingest_series(
    session: SQLModelAsyncSession, project: Project, *, order: list[int]
) -> None:
    """Ingest a fixed 3-book series into ``project``, in the given book order.

    Book 1: Anne Shirley + Gilbert Blythe. Book 2: Anne Shirley only. Book 3:
    "Miss Shirley" (an alias-overlapping rename) + Gilbert Blythe. Every
    book's own roster is fixed; only the order they are ingested (and
    therefore reconciled) in varies between the two calls this test makes.
    """
    books = {
        series_order: await make_book(session, project, series_order=series_order)
        for series_order in (1, 2, 3)
    }

    for series_order in order:
        book = books[series_order]
        chunk_id = await make_chunk(session, book)
        characters = [
            {
                "canonical_name": entry["canonical_name"],
                "aliases": entry["aliases"],
                "tier": entry["tier"],
                "mention_count": entry["mention_count"],
                "contexts": [ctx(entry["page"], entry["text"], chunk_id)],
            }
            for entry in _ROSTERS[series_order]
        ]
        await ingest_book_roster(
            session, book=book, project=project, characters=characters
        )
        await service.reconcile_book(session, book_id=book.id, project_id=project.id)


class TestOrderIndependence:
    async def test_reverse_order_ingestion_is_checksum_identical(
        self, session: SQLModelAsyncSession
    ) -> None:
        forward_project = Project(
            name="Anne Forward",
            slug=f"anne-fwd-{uuid.uuid4().hex[:8]}",
            kind=ProjectKind.SERIES,
        )
        reverse_project = Project(
            name="Anne Reverse",
            slug=f"anne-rev-{uuid.uuid4().hex[:8]}",
            kind=ProjectKind.SERIES,
        )
        session.add(forward_project)
        session.add(reverse_project)
        await session.commit()
        await session.refresh(forward_project)
        await session.refresh(reverse_project)

        await _ingest_series(session, forward_project, order=[1, 2, 3])
        await _ingest_series(session, reverse_project, order=[3, 2, 1])

        forward_checksum = await _project_checksum(session, forward_project.id)
        reverse_checksum = await _project_checksum(session, reverse_project.id)

        assert forward_checksum == reverse_checksum

        forward_names = {
            c.canonical_name
            for c in (
                await session.execute(
                    select(Character).where(Character.project_id == forward_project.id)
                )
            )
            .scalars()
            .all()
        }
        assert forward_names == {"Anne Shirley", "Gilbert Blythe"}
