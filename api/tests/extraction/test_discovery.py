import re
import uuid
from types import SimpleNamespace

import pytest
from transformers import AutoTokenizer

from api.config.settings import settings
from api.contracts.enums import CandidateKind
from api.contracts.llm import BatchPlan
from api.extraction import discovery
from api.extraction.schemas import (
    ChunkMentionsOutput,
    MentionOutput,
    MentionSweepOutput,
)
from api.llm.errors import LengthLimitError


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


_DENSE_NAMES = [
    "Elizabeth Bennet",
    "Fitzwilliam Darcy",
    "Jane Bennet",
    "Charles Bingley",
    "George Wickham",
    "Lydia Bennet",
    "Mr. Bennet",
    "Mrs. Bennet",
    "Caroline Bingley",
    "Charlotte Lucas",
]


def _dense_reply(n: int) -> MentionSweepOutput:
    """Ten substantial mentions per chunk — the shape a real dialogue-dense,
    multi-party scene actually produces, not a token-count stand-in."""
    return MentionSweepOutput(
        chunks=[
            ChunkMentionsOutput(
                chunk_index=i,
                mentions=[
                    MentionOutput(
                        surface_form=name,
                        kind=CandidateKind.PERSON,
                        context=(
                            f"{name} spoke at length about the ball at Netherfield "
                            "and the officers newly arrived in Meryton, addressing "
                            f"the whole assembled party in turn during passage {i}, "
                            "while everyone else present listened attentively and "
                            "occasionally replied with their own opinion of the "
                            "matter at hand."
                        ),
                    )
                    for name in _DENSE_NAMES
                ],
            )
            for i in range(1, n + 1)
        ]
    )


@pytest.mark.models
class TestSplitRetryOnLengthLimit:
    """A batch capped at 12 chunks (the fix above) can still overflow the
    reply if the scene itself is dense enough — real for Pride and
    Prejudice's constant multi-party conversations, where a 12-chunk batch
    produced a completion 3x over ``_OUTPUT_RESERVE`` and got cut off
    mid-JSON. No fixed chunk count is safe against every possible scene, in
    this book or the next one, so a batch that provably overflows must
    recover by splitting in half, recursively, rather than dying on an
    identical retry.

    "Provably" is checked here against the *real* tokenizer's count of a
    realistically dense reply (``_dense_reply``), not a hardcoded flag — the
    fake below raises exactly when a real ``AutoTokenizer`` says the reply
    would exceed the reserve, so this fails if the split logic's recursion
    or bookkeeping is wrong, not just if the try/except is deleted.
    """

    async def test_recursively_halves_a_batch_whose_real_reply_overflows_the_reserve(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tokenizer = AutoTokenizer.from_pretrained(settings.llm_model)
        pairs = [
            (_chunk(f"Passage {i} of the ball at Netherfield.", page=1), 1)
            for i in range(1, 13)
        ]
        call_sizes: list[int] = []

        async def fake_structured_call(prompt, schema, **kwargs):
            n = len(re.findall(r"^\[\d+\]", prompt, re.MULTILINE))
            call_sizes.append(n)
            reply = _dense_reply(n)
            reply_tokens = len(tokenizer.encode(reply.model_dump_json()))

            if reply_tokens > discovery._OUTPUT_RESERVE:
                raise LengthLimitError(f"simulated cutoff at {reply_tokens} tokens")

            return reply

        monkeypatch.setattr(discovery, "structured_call", fake_structured_call)

        results = await discovery._sweep_batch(pairs, book_id=uuid.uuid4())

        # Confirmed by direct measurement (not asserted blind): 12 and 6
        # dense chunks' worth of mentions both really overflow
        # _OUTPUT_RESERVE by the real tokenizer's count, and 3 chunks' worth
        # really fits — so recovery only succeeds if recursion goes two
        # levels deep (12 -> 6+6 -> 3+3 and 3+3), not just splits once.
        assert call_sizes.count(12) == 1
        assert call_sizes.count(6) == 2
        assert call_sizes.count(3) == 4
        assert len(call_sizes) == 7

        # Every one of the 12 chunks' 10 mentions survives the split; none
        # silently dropped by the recovery path.
        assert len(results) == 120
        assert {result.chunk_id for result in results} == {
            chunk.id for chunk, _ in pairs
        }

    async def test_a_single_chunk_that_still_overflows_fails_loudly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = 0

        async def always_overflows(prompt, schema, **kwargs):
            nonlocal calls
            calls += 1

            raise LengthLimitError("even one chunk overflows")

        monkeypatch.setattr(discovery, "structured_call", always_overflows)
        pairs = [(_chunk("Passage 1 of the ball.", page=1), 1)] * 4

        with pytest.raises(LengthLimitError):
            await discovery._sweep_batch(pairs, book_id=uuid.uuid4())

        # 4 -> 2 -> 1 then the floor raises: no infinite recursion, and no
        # silently skipped chunk.
        assert calls == 3
