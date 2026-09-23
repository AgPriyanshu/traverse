import uuid
from types import SimpleNamespace

import pytest

from api.contracts.enums import CandidateKind
from api.contracts.llm import BatchPlan
from api.extraction import discovery
from api.extraction.schemas import (
    ChunkMentionsOutput,
    MentionOutput,
    MentionSweepOutput,
)


def _chunk(text: str, page: int) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), text=text, page_start=page)


class TestDiscoverMentions:
    async def test_dedupes_within_a_chunk_and_attributes_page_and_chapter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chunk = _chunk("Elizabeth spoke to Elizabeth again.", page=5)
        pairs = [(chunk, 3)]
        plan = BatchPlan(items=pairs, token_count=10)
        monkeypatch.setattr(discovery, "plan_batches", lambda *a, **k: [plan])

        sweep = MentionSweepOutput(
            chunks=[
                ChunkMentionsOutput(
                    chunk_index=1,
                    mentions=[
                        MentionOutput(
                            surface_form="Elizabeth",
                            kind=CandidateKind.PERSON,
                            context="c1",
                        ),
                        MentionOutput(
                            surface_form="Elizabeth",
                            kind=CandidateKind.PERSON,
                            context="c2",
                        ),
                    ],
                )
            ]
        )

        async def fake_structured_call(prompt, schema, **kwargs):
            return sweep

        monkeypatch.setattr(discovery, "structured_call", fake_structured_call)

        results = await discovery.discover_mentions(pairs, book_id=uuid.uuid4())

        assert len(results) == 1
        mention = results[0]
        assert mention.surface_form == "Elizabeth"
        assert mention.count == 2
        assert mention.page == 5
        assert mention.chapter_number == 3
        assert mention.chunk_id == chunk.id

    async def test_skips_a_split_chunk_without_crashing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pairs = [(_chunk("x", 1), None)]
        split_plan = BatchPlan(items=["some text piece"], token_count=5, was_split=True)
        monkeypatch.setattr(discovery, "plan_batches", lambda *a, **k: [split_plan])

        async def fake_structured_call(*a, **k):
            raise AssertionError("should not be called for a split batch")

        monkeypatch.setattr(discovery, "structured_call", fake_structured_call)

        results = await discovery.discover_mentions(pairs, book_id=uuid.uuid4())

        assert results == []

    async def test_empty_chunks_returns_empty(self) -> None:
        assert await discovery.discover_mentions([], book_id=uuid.uuid4()) == []

    async def test_drops_out_of_range_chunk_index(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pairs = [(_chunk("x", 1), None)]
        plan = BatchPlan(items=pairs, token_count=5)
        monkeypatch.setattr(discovery, "plan_batches", lambda *a, **k: [plan])

        sweep = MentionSweepOutput(
            chunks=[
                ChunkMentionsOutput(
                    chunk_index=9,
                    mentions=[MentionOutput(surface_form="Ghost", context="c")],
                )
            ]
        )

        async def fake_structured_call(*a, **k):
            return sweep

        monkeypatch.setattr(discovery, "structured_call", fake_structured_call)

        results = await discovery.discover_mentions(pairs, book_id=uuid.uuid4())

        assert results == []
