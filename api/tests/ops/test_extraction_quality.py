import uuid

import pytest
from eval.loaders import load_gold_roster
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import ImportanceTier, ResolutionMethod
from api.db.models import (
    Book,
    Character,
    CharacterAppearance,
    CharacterMention,
    DocumentChunk,
    RejectedCandidate,
)
from api.db.models.project_model import Project
from api.ops.extraction_quality import compute_extraction_quality


async def _pride_and_prejudice_book(
    session: SQLModelAsyncSession, project: Project
) -> Book:
    # Title must slugify to the gold roster's book_key ("pride-and-prejudice").
    row = Book(
        project_id=project.id,
        title="Pride and Prejudice",
        author="Jane Austen",
        content_hash=uuid.uuid4().hex,
        page_count=245,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return row


async def test_no_gold_roster_reports_unavailable_not_an_error(
    session: SQLModelAsyncSession, book: Book
) -> None:
    # The generic `book` fixture is titled "The Test Novel" -- no gold roster.
    result = await compute_extraction_quality(session, book.id)

    assert result.gold_available is False
    assert result.error is None
    assert result.roster_precision is None


async def test_unknown_book_id_is_not_an_error(session: SQLModelAsyncSession) -> None:
    result = await compute_extraction_quality(session, uuid.uuid4())

    assert result.gold_available is False
    assert result.error == "book not found"


async def test_scores_a_matched_character_and_a_false_positive(
    session: SQLModelAsyncSession, project: Project
) -> None:
    pp_book = await _pride_and_prejudice_book(session, project)
    gold = load_gold_roster("pride-and-prejudice")
    gold_character_count = len(gold["characters"])

    # A correctly-resolved Elizabeth Bennet (matches gold on the "Lizzy" alias).
    elizabeth = Character(
        project_id=project.id,
        canonical_name="Elizabeth",
        aliases=["Lizzy"],
        importance_tier=ImportanceTier.PROTAGONIST,
    )
    # A wrongly-kept place name -- the system never rejected it.
    netherfield = Character(
        project_id=project.id,
        canonical_name="Netherfield",
        aliases=[],
        importance_tier=ImportanceTier.MENTIONED,
    )
    session.add(elizabeth)
    session.add(netherfield)
    await session.commit()
    await session.refresh(elizabeth)
    await session.refresh(netherfield)

    session.add(
        CharacterAppearance(
            character_id=elizabeth.id,
            book_id=pp_book.id,
            importance_tier=ImportanceTier.PROTAGONIST,
            surface_forms=["Elizabeth", "Lizzy"],
            mention_count=2,
        )
    )
    session.add(
        CharacterAppearance(
            character_id=netherfield.id,
            book_id=pp_book.id,
            importance_tier=ImportanceTier.MENTIONED,
            surface_forms=["Netherfield"],
            mention_count=1,
        )
    )
    await session.commit()

    result = await compute_extraction_quality(session, pp_book.id)

    assert result.gold_available is True
    assert result.book_key == "pride-and-prejudice"
    assert result.roster_true_positives == 1
    assert result.roster_false_positives == 1
    assert result.roster_false_negatives == gold_character_count - 1
    assert result.tier_accuracy == pytest.approx(1.0)  # Elizabeth's tier matched


async def test_rejection_and_cascade_metrics_read_their_own_tables(
    session: SQLModelAsyncSession, project: Project
) -> None:
    pp_book = await _pride_and_prejudice_book(session, project)
    elizabeth = Character(
        project_id=project.id,
        canonical_name="Elizabeth Bennet",
        aliases=["Lizzy"],
        importance_tier=ImportanceTier.PROTAGONIST,
    )
    session.add(elizabeth)
    await session.commit()
    await session.refresh(elizabeth)

    session.add(
        CharacterAppearance(
            character_id=elizabeth.id,
            book_id=pp_book.id,
            importance_tier=ImportanceTier.PROTAGONIST,
            surface_forms=["Elizabeth Bennet", "Lizzy"],
        )
    )
    # A correct rejection (Longbourn is gold-listed as a place) and a wrong
    # one (Darcy is a real, major gold character).
    session.add(
        RejectedCandidate(book_id=pp_book.id, surface_form="Longbourn", reason="place")
    )
    session.add(
        RejectedCandidate(book_id=pp_book.id, surface_form="Darcy", reason="mistaken")
    )

    chunk = DocumentChunk(
        book_id=pp_book.id,
        text="Elizabeth walked to Netherfield.",
        pages=[13],
        page_start=13,
        page_end=13,
    )
    session.add(chunk)
    await session.commit()
    await session.refresh(chunk)

    session.add(
        CharacterMention(
            character_id=elizabeth.id,
            book_id=pp_book.id,
            chunk_id=chunk.id,
            surface_form="Lizzy",
            page=13,
            resolution_method=ResolutionMethod.NICKNAME,
        )
    )
    session.add(
        CharacterMention(
            character_id=elizabeth.id,
            book_id=pp_book.id,
            chunk_id=chunk.id,
            surface_form="Elizabeth Bennet",
            page=13,
            resolution_method=ResolutionMethod.EXACT,
        )
    )
    await session.commit()

    result = await compute_extraction_quality(session, pp_book.id)

    assert result.rejection_precision == pytest.approx(0.5)
    assert result.wrongly_rejected == ["Darcy"]
    assert result.cascade_contribution == {"nickname": 1, "exact": 1}
