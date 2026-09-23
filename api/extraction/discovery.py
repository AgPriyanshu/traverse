"""Pass-1 character discovery (S3.1).

Recall is the objective here; precision is bought back by rejection (S3.2)
and the alias cascade (S3.3). A character missed in this sweep does not exist
for the rest of the pipeline, so over-generation is expected and fine.
"""

import asyncio
import logging
from collections import defaultdict
from uuid import UUID

from pydantic import BaseModel

from api.llm import LengthLimitError, plan_batches, structured_call

from ..config.settings import settings
from ..contracts.enums import LLMPurpose
from ..contracts.extraction import CharacterCandidate
from ..contracts.llm import BatchPlan
from ..db.models import DocumentChunk
from .prompts import MENTION_SWEEP_PROMPT
from .schemas import MentionSweepOutput

logger = logging.getLogger(__name__)

# "A 12-chunk batch can emit 60 mentions" (backend-1.md S3.1) is the sizing
# reference: budget output for that ratio so the reserve shrinks the batch
# instead of the batch overflowing the reply.
_ASSUMED_CHUNKS_PER_BATCH = 12
_ASSUMED_MENTIONS_PER_CHUNK = 5
_OUTPUT_TOKENS_PER_MENTION = 60
_OUTPUT_RESERVE = (
    _ASSUMED_CHUNKS_PER_BATCH * _ASSUMED_MENTIONS_PER_CHUNK * _OUTPUT_TOKENS_PER_MENTION
)


class MentionCandidate(CharacterCandidate):
    """A pass-1 mention, deduplicated within its chunk.

    Extends the frozen ``CharacterCandidate`` contract rather than modifying
    it — ``count`` never leaves this package; it is folded into
    ``BookCharacterCandidate.contexts`` on persistence, not exposed on the
    contract itself.
    """

    count: int = 1


async def discover_mentions(
    chunks: list[tuple[DocumentChunk, int | None]],
    *,
    book_id: UUID,
) -> list[MentionCandidate]:
    """Sweep every chunk of a book for character-like mentions.

    Args:
        chunks: The book's chunks in document order, paired with each one's
            chapter number
            (``api.pipeline.repository.list_chunks_with_chapter_number``).
        book_id: Tags the Langfuse trace and the extraction purpose.

    Returns:
        One ``MentionCandidate`` per distinct surface form per chunk, each
        carrying how many times that form occurred in that chunk.
    """
    if not chunks:
        return []

    # ``plan_batches`` packs items greedily until it runs out of *input*
    # token budget — it has no notion of "12 items," so it happily packs
    # 30-40 real chunks into one batch when they run well under
    # ``CHUNK_MAX_TOKENS`` (semantic chunking, not maximal packing). Since
    # ``_OUTPUT_RESERVE`` above is sized for ``_ASSUMED_CHUNKS_PER_BATCH``
    # mentions worth of output, handing it a batch with 3x that many chunks
    # lets the completion overrun the reserve and get cut off mid-JSON. The
    # slice below enforces the chunk-count assumption the reserve was
    # actually computed for; ``plan_batches`` still governs token safety
    # within each slice.
    plans: list[BatchPlan[tuple[DocumentChunk, int | None]]] = []
    for start in range(0, len(chunks), _ASSUMED_CHUNKS_PER_BATCH):
        group = chunks[start : start + _ASSUMED_CHUNKS_PER_BATCH]
        plans.extend(
            plan_batches(
                group,
                prompt_tokens=len(MENTION_SWEEP_PROMPT) // 4,
                text_of=lambda pair: pair[0].text,
                max_context=settings.llm_max_context,
                output_reserve=_OUTPUT_RESERVE,
                tokenizer_model=settings.llm_model,
            )
        )

    sweepable = []
    for plan in plans:
        if plan.was_split:
            # Chunks are capped at ``CHUNK_MAX_TOKENS`` (1024), well inside
            # any batch's per-item budget for this call — a split here means
            # the budget math is wrong, not that this chunk is unusually
            # long. There is no page to attribute a bare text piece to, so
            # surfacing it loudly beats silently fabricating one.
            logger.warning(
                "book %s: a chunk was split for character-extraction batching; "
                "mentions in it cannot be attributed to a page and are skipped",
                book_id,
            )
            continue

        sweepable.append(plan.items)

    # Sequential calls left vLLM serving one request at a time (~57 tokens/s);
    # ``structured_call`` already bounds concurrency with a shared semaphore, so
    # fanning out lets the server batch them. ``gather`` keeps document order.
    swept = await asyncio.gather(
        *(_sweep_batch(items, book_id=book_id) for items in sweepable)
    )
    candidates: list[MentionCandidate] = [
        candidate for batch in swept for candidate in batch
    ]

    return candidates


async def _sweep_batch(
    batch: list[tuple[DocumentChunk, int | None]], *, book_id: UUID
) -> list[MentionCandidate]:
    """Sweep one batch, splitting in half and retrying if the reply overflows.

    ``_OUTPUT_RESERVE`` is sized from an *assumed average* mentions-per-chunk
    ratio, not a hard cap: a dialogue- and name-dense scene can produce far
    more mentions than that for a batch well within the chunk-count cap, and
    no fixed count is safe against every scene. A batch cut off by the length
    limit is therefore halved and each half retried, recursively. A single
    chunk that still overflows cannot be split further, so the error is
    re-raised rather than skipping it: a silently missing chunk is a recall
    hole nobody would see.
    """
    passages = "\n\n".join(
        f"[{index}] {chunk.text}" for index, (chunk, _) in enumerate(batch, start=1)
    )
    prompt = MENTION_SWEEP_PROMPT.format(passages=passages)

    try:
        result = await structured_call(
            prompt,
            MentionSweepOutput,
            purpose=LLMPurpose.CHARACTER_EXTRACT,
            book_id=str(book_id),
            stage="extract_characters",
        )
    except LengthLimitError:
        if len(batch) == 1:
            raise

        midpoint = len(batch) // 2
        logger.info(
            "book %s: a %d-chunk mention sweep hit the length limit; "
            "splitting into %d and %d chunks",
            book_id,
            len(batch),
            midpoint,
            len(batch) - midpoint,
        )
        first_half = await _sweep_batch(batch[:midpoint], book_id=book_id)
        second_half = await _sweep_batch(batch[midpoint:], book_id=book_id)

        return [*first_half, *second_half]

    candidates: list[MentionCandidate] = []
    for chunk_mentions in result.chunks:
        index = chunk_mentions.chunk_index

        if not 1 <= index <= len(batch):
            logger.warning(
                "book %s: dropping mentions for out-of-range chunk_index %s",
                book_id,
                index,
            )
            continue

        chunk, chapter_number = batch[index - 1]
        candidates.extend(
            _dedupe_within_chunk(chunk_mentions.mentions, chunk, chapter_number)
        )

    return candidates


def _dedupe_within_chunk(
    mentions: list[BaseModel], chunk: DocumentChunk, chapter_number: int | None
) -> list[MentionCandidate]:
    counts: dict[str, int] = defaultdict(int)
    kinds: dict[str, object] = {}
    contexts: dict[str, str] = {}

    for mention in mentions:
        form = mention.surface_form.strip()  # type: ignore[attr-defined]

        if not form:
            continue

        counts[form] += 1
        kinds.setdefault(form, mention.kind)  # type: ignore[attr-defined]
        contexts.setdefault(form, mention.context)  # type: ignore[attr-defined]

    return [
        # ``page_start`` stands in for a per-mention page: nothing upstream
        # tracks where within a chunk's span a mention falls, and citing the
        # chunk's first page is conservative rather than wrong.
        MentionCandidate(
            surface_form=form,
            chunk_id=chunk.id,
            page=chunk.page_start,
            chapter_number=chapter_number,
            context=contexts[form],
            kind=kinds[form],
            count=count,
        )
        for form, count in counts.items()
    ]
