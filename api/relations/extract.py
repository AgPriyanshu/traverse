import asyncio
import logging
from dataclasses import dataclass, field
from uuid import UUID

from pydantic import BaseModel

from api.llm import LengthLimitError, structured_call

from ..contracts.enums import LLMPurpose
from ..db.models import DocumentChunk
from . import prompts
from .roster import Roster
from .schemas import RelationSweepOutput
from .validator import RejectionStats, ValidRelation, validate

logger = logging.getLogger(__name__)

_MIN_SPLIT_CHARS = 400
_PARALLEL_CHUNKS = 16


class ExtractedFact(BaseModel):
    chunk_id: UUID
    chapter: int | None
    page_start: int
    page_end: int
    subject_id: UUID
    predicate: str
    object_id: UUID
    quote: str
    assertion_type: str
    asserted_by_id: UUID | None
    confidence: float


@dataclass
class ExtractionResult:
    facts: list[ExtractedFact] = field(default_factory=list)
    stats: RejectionStats = field(default_factory=RejectionStats)
    roster_strategy: str = "full"
    roster_size: int = 0
    chunks_total: int = 0
    chunks_read: int = 0
    calls: int = 0
    length_splits: int = 0
    unsplittable_chunks: int = 0

    def summary(self) -> dict:
        payload = {
            "roster_strategy": self.roster_strategy,
            "roster_size": self.roster_size,
            "chunks_total": self.chunks_total,
            "chunks_read": self.chunks_read,
            "calls": self.calls,
            "length_splits": self.length_splits,
            "unsplittable_chunks": self.unsplittable_chunks,
            "facts": len(self.facts),
            **self.stats.as_dict(),
        }

        return payload


def split_text(text: str) -> tuple[str, str] | None:
    """Split text near its middle at a paragraph, sentence or word boundary.

    Returns:
        Two halves, or ``None`` when the text is too short to split usefully.
    """
    if len(text) < _MIN_SPLIT_CHARS:
        return None

    middle = len(text) // 2
    for separator in ("\n", ". ", " "):
        cut = text.rfind(separator, 0, middle)
        if cut <= 0:
            cut = text.find(separator, middle)
        if cut > 0:
            first, second = text[: cut + len(separator)], text[cut + len(separator) :]
            if first.strip() and second.strip():
                return first, second

    return None


async def _sweep(
    prefix: str,
    chunk: DocumentChunk,
    chapter: int | None,
    text: str,
    *,
    book_id: UUID,
    result: ExtractionResult,
) -> list:
    prompt = prompts.build_prompt(
        prefix,
        chapter=chapter,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        text=text,
    )
    result.calls += 1
    try:
        output = await structured_call(
            prompt,
            RelationSweepOutput,
            purpose=LLMPurpose.RELATION_EXTRACT,
            book_id=str(book_id),
            stage="extract_relations",
        )
    except LengthLimitError:
        halves = split_text(text)
        if halves is None:
            result.unsplittable_chunks += 1
            logger.warning(
                "book %s: chunk %s overflowed the reply limit and cannot be split "
                "further; its relations are skipped",
                book_id,
                chunk.id,
            )

            return []

        result.length_splits += 1
        first = await _sweep(
            prefix, chunk, chapter, halves[0], book_id=book_id, result=result
        )
        second = await _sweep(
            prefix, chunk, chapter, halves[1], book_id=book_id, result=result
        )
        merged = [*first, *second]

        return merged

    relations = output.relations

    return relations


async def extract_chunk(
    prefix: str,
    chunk: DocumentChunk,
    chapter: int | None,
    roster: Roster,
    *,
    book_id: UUID,
    result: ExtractionResult,
) -> None:
    """Run pass 2 on one chunk and append validated facts to ``result``."""
    raw_relations = await _sweep(
        prefix, chunk, chapter, chunk.text, book_id=book_id, result=result
    )
    for raw in raw_relations:
        valid: ValidRelation | None = validate(raw, chunk.text, roster, result.stats)
        if valid is None:
            continue
        result.facts.append(
            ExtractedFact(
                chunk_id=chunk.id,
                chapter=chapter,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                subject_id=valid.subject_id,
                predicate=valid.predicate,
                object_id=valid.object_id,
                quote=valid.quote,
                assertion_type=valid.assertion_type,
                asserted_by_id=valid.asserted_by_id,
                confidence=valid.confidence,
            )
        )


async def extract_book(
    chunks: list[tuple[DocumentChunk, int | None]],
    roster: Roster,
    *,
    book_id: UUID,
    only_chunk_ids: set[UUID] | None = None,
) -> ExtractionResult:
    """Run pass 2 over a book's chunks.

    The first chunk runs alone: it populates vLLM's prefix cache, and sixteen
    concurrent first calls would all miss it and pay for the roster sixteen
    times. Concurrency after that is bounded here and, below it, by the shared
    LLM semaphore.

    Args:
        chunks: The book's chunks in document order with chapter numbers.
        roster: The book's roster.
        book_id: Tags the Langfuse trace.
        only_chunk_ids: The prefilter's verdict; ``None`` reads every chunk.

    Returns:
        Validated facts plus counters for every rejection reason.
    """
    prefix = prompts.build_prefix(roster.prompt_block())
    selected = [
        (chunk, chapter)
        for chunk, chapter in chunks
        if only_chunk_ids is None or chunk.id in only_chunk_ids
    ]
    result = ExtractionResult(
        roster_strategy=roster.strategy,
        roster_size=len(roster.entries),
        chunks_total=len(chunks),
        chunks_read=len(selected),
    )
    if not selected:
        return result

    async def run(pair: tuple[DocumentChunk, int | None]) -> None:
        await extract_chunk(
            prefix, pair[0], pair[1], roster, book_id=book_id, result=result
        )

    await run(selected[0])
    gate = asyncio.Semaphore(_PARALLEL_CHUNKS)

    async def bounded(pair: tuple[DocumentChunk, int | None]) -> None:
        async with gate:
            await run(pair)

    await asyncio.gather(*(bounded(pair) for pair in selected[1:]))
    # Completion order is nondeterministic; sort so aggregation is repeatable.
    result.facts.sort(key=lambda f: (f.page_start, str(f.chunk_id), f.quote))

    return result
