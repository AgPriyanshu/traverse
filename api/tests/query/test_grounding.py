import uuid

import pytest

from api.contracts.api import ChunkOut
from api.query import grounding


def _chunk(text: str) -> ChunkOut:
    return ChunkOut(
        id=uuid.uuid4(),
        book_id=uuid.uuid4(),
        text=text,
        pages=[10],
        page_start=10,
        page_end=10,
    )


def test_abstain_uses_the_standard_sentence():
    result = grounding.abstain()
    assert result.text == grounding.ABSTENTION_TEXT
    assert result.abstained is True
    assert result.citations == []


def test_abstain_appends_a_reason():
    result = grounding.abstain("Elizabeth Bennet has no established brother.")
    assert result.text.startswith(grounding.ABSTENTION_TEXT)
    assert "brother" in result.text


@pytest.mark.asyncio
async def test_ground_narrative_answer_drops_unsupported_sentences(
    session, monkeypatch
):
    chunks = [_chunk("Darcy proposed to Elizabeth at Rosings and she refused him.")]
    draft = (
        "Darcy proposed to Elizabeth at Rosings and she refused him. "
        "Napoleon then invaded Russia the following winter."
    )

    async def _fake_locate(_session, _chunk_id, quote):
        return type("Span", (), {"page": 10, "boxes": []})()

    monkeypatch.setattr("api.pipeline.quotes.locate_quote", _fake_locate)

    result = await grounding.ground_narrative_answer(session, draft, chunks)

    assert "Darcy proposed" in result.text
    assert "Napoleon" not in result.text
    assert result.abstained is False
    assert len(result.citations) == 1


@pytest.mark.asyncio
async def test_ground_narrative_answer_abstains_when_nothing_is_supported(session):
    chunks = [_chunk("The weather in Hertfordshire was fine that autumn.")]
    draft = "Napoleon invaded Russia the following winter."

    result = await grounding.ground_narrative_answer(session, draft, chunks)

    assert result.abstained is True
    assert result.text == grounding.ABSTENTION_TEXT
    assert result.citations == []


@pytest.mark.asyncio
async def test_ground_narrative_answer_drops_citation_when_locate_quote_fails(
    session, monkeypatch
):
    chunks = [_chunk("Darcy proposed to Elizabeth at Rosings and she refused him.")]
    draft = "Darcy proposed to Elizabeth at Rosings and she refused him."

    async def _fake_locate(_session, _chunk_id, _quote):
        return None

    monkeypatch.setattr("api.pipeline.quotes.locate_quote", _fake_locate)

    result = await grounding.ground_narrative_answer(session, draft, chunks)

    # The sentence is still kept — grounding is about lexical support, not
    # about whether the exact span could be re-located in the PDF — but the
    # citation itself is dropped rather than shown unverified.
    assert "Darcy proposed" in result.text
    assert result.citations == []
