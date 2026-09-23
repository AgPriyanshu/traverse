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


@pytest.mark.models
class TestBatchSizeInvariant:
    """Real book, real tokenizer: exercise the packing math, not a mock.

    Pride and Prejudice ingestion hit this for real: chunks ran well under
    ``CHUNK_MAX_TOKENS``, so ``plan_batches``'s token-only packing alone
    happily fit 30-40 of them into one batch — 3x what ``_OUTPUT_RESERVE``
    was ever sized for (S3.1's assumed 12 chunks / 60 mentions), and the
    completion got cut off mid-JSON. This drives ``discover_mentions`` with
    the real ``plan_batches`` (only ``_sweep_batch`` is faked, to skip the
    LLM call) and asserts the invariant the fix restores: no batch handed to
    one structured call ever exceeds the chunk count the reserve assumes,
    however much token headroom real chunks leave unused.
    """

    async def test_never_packs_more_chunks_than_the_output_reserve_assumes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pairs = [
            (_chunk(f"Elizabeth said hello there, sentence number {i}.", page=1), 1)
            for i in range(30)
        ]
        seen_batch_sizes: list[int] = []

        async def fake_sweep_batch(batch, *, book_id):
            seen_batch_sizes.append(len(batch))
            return []

        monkeypatch.setattr(discovery, "_sweep_batch", fake_sweep_batch)

        await discovery.discover_mentions(pairs, book_id=uuid.uuid4())

        # All 30 chunks are short enough that plan_batches's token budget
        # alone would fit every one of them in a single batch — proving the
        # slice, not incidental token pressure, is what keeps batches small.
        assert seen_batch_sizes
        assert all(
            size <= discovery._ASSUMED_CHUNKS_PER_BATCH for size in seen_batch_sizes
        )
        assert sum(seen_batch_sizes) == len(pairs)
