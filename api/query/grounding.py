import re
from dataclasses import dataclass

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import ChunkOut, CitationOut

ABSTENTION_TEXT = "Not established in this novel."

# Below this fraction of a sentence's content words found in a chunk, the
# overlap is coincidental (shared common words) rather than real support.
_SUPPORT_THRESHOLD = 0.6
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[a-z0-9']+")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "the",
        "of",
        "to",
        "in",
        "on",
        "at",
        "for",
        "with",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "he",
        "she",
        "it",
        "they",
        "them",
        "his",
        "her",
        "its",
        "their",
        "this",
        "that",
        "which",
        "who",
        "whom",
        "not",
        "no",
        "but",
        "or",
        "if",
        "then",
        "than",
        "so",
    ]
)
_QUOTE_MAX_CHARS = 400


@dataclass
class GroundedAnswer:
    text: str
    citations: list[CitationOut]
    abstained: bool


def _content_words(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def _best_supporting_chunk(
    sentence: str, chunks: list[ChunkOut]
) -> tuple[ChunkOut, float] | None:
    """Return the chunk with the most content-word overlap, if any clears threshold."""
    words = _content_words(sentence)
    if not words:
        return None

    best: tuple[ChunkOut, float] | None = None
    for chunk in chunks:
        chunk_words = _content_words(chunk.text)
        if not chunk_words:
            continue
        overlap = len(words & chunk_words) / len(words)
        if best is None or overlap > best[1]:
            best = (chunk, overlap)

    if best is not None and best[1] >= _SUPPORT_THRESHOLD:
        return best

    return None


def _quote_from_chunk(sentence: str, chunk: ChunkOut) -> str:
    """Pick a citable excerpt: the sentence itself if it is genuinely IN the chunk.

    A generated sentence rarely appears verbatim, so this is a courtesy for
    the (common) case where it does; otherwise the chunk's own opening span
    stands in as the citable quote — still a real excerpt of the source, just
    not necessarily the exact clause the sentence paraphrases.
    """
    quote = sentence if sentence in chunk.text else chunk.text[:_QUOTE_MAX_CHARS]

    return quote[:_QUOTE_MAX_CHARS]


async def _build_citation(
    session: SQLModelAsyncSession, chunk: ChunkOut, quote: str
) -> CitationOut | None:
    """Build a citation, dropping it if the quote cannot be located in its chunk.

    Best-effort: ``locate_quote`` needs the source PDF from object storage.
    Any failure to reach it (missing storage in a test, a transient error) is
    treated the same as "not found" — a citation this sprint cannot verify is
    dropped rather than shown unverified (query-path.md).
    """
    try:
        from ..pipeline.quotes import locate_quote

        located = await locate_quote(session, chunk.id, quote)
    except Exception:
        located = None

    if located is None:
        return None

    citation = CitationOut(
        book_id=chunk.book_id,
        page_start=located.page,
        page_end=located.page,
        chapter_no=chunk.chapter_number,
        quote=quote,
        chunk_id=chunk.id,
    )

    return citation


async def ground_narrative_answer(
    session: SQLModelAsyncSession, draft: str, chunks: list[ChunkOut]
) -> GroundedAnswer:
    """Keep only the sentences a retrieved chunk actually supports.

    Args:
        session: An open database session.
        draft: The model's raw, unverified answer.
        chunks: The chunks the model was given as context — the only
            evidence a claim may be grounded against.

    Returns:
        The grounded answer: kept sentences joined back together, one
        citation per kept sentence that could be located, and whether every
        sentence was dropped (a full abstention).
    """
    kept_sentences: list[str] = []
    citations: list[CitationOut] = []

    for sentence in _split_sentences(draft):
        match = _best_supporting_chunk(sentence, chunks)
        if match is None:
            continue

        chunk, _score = match
        kept_sentences.append(sentence)
        quote = _quote_from_chunk(sentence, chunk)
        citation = await _build_citation(session, chunk, quote)
        if citation is not None:
            citations.append(citation)

    if not kept_sentences:
        return GroundedAnswer(text=ABSTENTION_TEXT, citations=[], abstained=True)

    answer = GroundedAnswer(
        text=" ".join(kept_sentences), citations=citations, abstained=False
    )

    return answer


def abstain(reason: str | None = None) -> GroundedAnswer:
    """Return the standard abstention answer.

    Args:
        reason: An optional, specific reason appended after the standard
            sentence — e.g. "Elizabeth Bennet has no established brother in
            this project." Kept separate from ``ABSTENTION_TEXT`` so a test
            can assert on the constant regardless of the reason text.
    """
    text = ABSTENTION_TEXT if not reason else f"{ABSTENTION_TEXT} {reason}"

    return GroundedAnswer(text=text, citations=[], abstained=True)
