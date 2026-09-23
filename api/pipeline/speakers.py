import asyncio
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

from pydantic import BaseModel, Field

from api.contracts.enums import LLMPurpose
from api.llm import LengthLimitError, structured_call

from .scene_repository import DialogueLineRow

logger = logging.getLogger(__name__)

EXPLICIT_TAG = "explicit_tag"
NARRATION = "narration"
ALTERNATION = "alternation"
LLM = "llm"
UNRESOLVED = "unresolved"

SPEECH_VERBS = (
    "said|says|replied|replies|cried|cries|exclaimed|answered|asked|added|"
    "continued|observed|returned|rejoined|whispered|muttered|shouted|called|"
    "declared|remarked|inquired|responded|interrupted|repeated|persisted|"
    "resumed|began|cried out|spoke|urged|protested|insisted|laughed|sighed"
)
_VERB_RE = re.compile(rf"\b(?:{SPEECH_VERBS})\b", re.IGNORECASE)
_QUOTE_RE = re.compile(r"“[^”]*(?:”|$)|\"[^\"\n]*(?:\"|$)")
_HONORIFIC_GAP_RE = re.compile(
    r"^\s*(?:(?:mr|mrs|miss|ms|dr|lady|sir|lord|madam|captain|colonel)\.?\s+)?$",
    re.IGNORECASE,
)

TAG_WINDOW_CHARS = 90
MAX_ALTERNATION_RUN = 6
MIN_LLM_CONFIDENCE = 0.5
LLM_LINES_PER_CALL = 10
LLM_CONCURRENCY = 8
EXCERPT_CHARS = 500
MAX_ROSTER = 14


@dataclass(frozen=True)
class Mention:
    character_id: UUID
    start: int
    end: int


@dataclass(frozen=True)
class SpeakerParagraph:
    chunk_id: UUID
    start: int
    text: str
    mentions: list[Mention]


@dataclass
class Line:
    paragraph: int
    chunk_id: UUID
    char_start: int
    char_end: int
    speaker: UUID | None = None
    method: str = UNRESOLVED
    confidence: float = 0.0
    run: int = 0


@dataclass
class SceneText:
    chunk_ids: list[UUID]
    chunk_texts: dict[UUID, str]
    participants: dict[UUID, int]
    chunk_characters: dict[UUID, set[UUID]] = field(default_factory=dict)


class SpeakerAssignment(BaseModel):
    line: int
    speaker: int | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class SpeakerBatchOutput(BaseModel):
    assignments: list[SpeakerAssignment]


SPEAKER_PROMPT = """You attribute quoted dialogue in a novel to the character who \
speaks it.

Characters that may be speaking:
{roster}

For each numbered line below, the quotation to attribute is between <<< and >>>. \
Answer with the number of the speaking character from the list above, or null \
when the text does not make the speaker clear. Do not guess: null is correct \
when it is unclear. Give a confidence between 0 and 1.

{lines}
"""


def find_quotes(text: str) -> list[tuple[int, int]]:
    """Return ``(start, end)`` offsets of each quoted span in ``text``.

    A quotation left open at the end of a paragraph runs to that paragraph's
    end, which is how novels continue one speech across paragraphs.
    """
    spans = [
        (match.start(), match.end())
        for match in _QUOTE_RE.finditer(text)
        if sum(char.isalnum() for char in match.group()) >= 2
    ]

    return spans


def build_matcher(
    forms_by_character: dict[UUID, list[str]],
) -> tuple[re.Pattern[str], dict[str, UUID]] | None:
    """Compile one regex over the surface forms unambiguous among these characters.

    A form that belongs to two characters ("Catherine" for both Catherines) is
    dropped rather than guessed at.
    """
    owners: dict[str, set[UUID]] = {}
    for character_id, forms in forms_by_character.items():
        for form in forms:
            key = form.strip().lower()
            if len(key) >= 3:
                owners.setdefault(key, set()).add(character_id)

    unique = {key: next(iter(ids)) for key, ids in owners.items() if len(ids) == 1}
    if not unique:
        return None

    ordered = sorted(unique, key=len, reverse=True)
    pattern = re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(key) for key in ordered) + r")(?!\w)",
        re.IGNORECASE,
    )

    return pattern, unique


def find_mentions(
    text: str, matcher: tuple[re.Pattern[str], dict[str, UUID]] | None
) -> list[Mention]:
    """Locate roster mentions in ``text`` with their offsets."""
    if matcher is None:
        return []

    pattern, owners = matcher
    mentions = [
        Mention(owners[match.group().lower()], match.start(), match.end())
        for match in pattern.finditer(text)
    ]

    return mentions


def _split_paragraphs(chunk_id: UUID, text: str) -> list[tuple[int, str]]:
    paragraphs: list[tuple[int, str]] = []
    offset = 0
    for piece in text.split("\n"):
        if piece.strip():
            paragraphs.append((offset, piece))
        offset += len(piece) + 1

    return paragraphs


def _outside(mentions: list[Mention], quotes: list[tuple[int, int]]) -> list[Mention]:
    kept = [
        mention
        for mention in mentions
        if not any(start <= mention.start < end for start, end in quotes)
    ]

    return kept


def _tag_speaker(
    text: str, mentions: list[Mention], window_start: int, window_end: int
) -> UUID | None:
    """Find ``NAME verb`` or ``verb NAME`` in a window beside a quotation."""
    window = text[window_start:window_end]
    verbs = [
        (window_start + m.start(), window_start + m.end())
        for m in _VERB_RE.finditer(window)
    ]

    for verb_start, verb_end in verbs:
        for mention in mentions:
            if mention.start < window_start or mention.end > window_end:
                continue

            if mention.start >= verb_end:
                gap = text[verb_end : mention.start]
            elif mention.end <= verb_start:
                gap = text[mention.end : verb_start]
            else:
                continue

            if _HONORIFIC_GAP_RE.match(gap):
                return mention.character_id

    return None


def _explicit_speaker(
    text: str,
    mentions: list[Mention],
    quotes: list[tuple[int, int]],
    index: int,
) -> UUID | None:
    start, end = quotes[index]
    next_start = quotes[index + 1][0] if index + 1 < len(quotes) else len(text)
    after_end = min(next_start, end + TAG_WINDOW_CHARS)
    speaker = _tag_speaker(text, mentions, end, after_end)

    if speaker is None:
        previous_end = quotes[index - 1][1] if index > 0 else 0
        before_start = max(previous_end, start - TAG_WINDOW_CHARS)
        speaker = _tag_speaker(text, mentions, before_start, start)

    return speaker


def _distinct(mentions: list[Mention]) -> set[UUID]:
    distinct = {mention.character_id for mention in mentions}

    return distinct


def extract_scene_lines(
    scene: SceneText,
    matchers: dict[UUID, tuple[re.Pattern[str], dict[str, UUID]] | None],
) -> tuple[list[SpeakerParagraph], list[Line], list[list[tuple[int, int]]]]:
    """Split a scene into paragraphs and locate every dialogue line in it.

    Returns:
        Paragraphs in order, the dialogue lines, and each paragraph's quote
        spans in paragraph-relative offsets.
    """
    paragraphs: list[SpeakerParagraph] = []
    lines: list[Line] = []
    quotes_by_paragraph: list[list[tuple[int, int]]] = []

    for chunk_id in scene.chunk_ids:
        for offset, piece in _split_paragraphs(chunk_id, scene.chunk_texts[chunk_id]):
            mentions = find_mentions(piece, matchers.get(chunk_id))
            index = len(paragraphs)
            paragraphs.append(SpeakerParagraph(chunk_id, offset, piece, mentions))
            quotes = find_quotes(piece)
            quotes_by_paragraph.append(quotes)
            lines.extend(
                Line(index, chunk_id, offset + start, offset + end)
                for start, end in quotes
            )

    return paragraphs, lines, quotes_by_paragraph


def _resolve(
    line: Line, speaker: UUID, method: str, confidence: float, run: int = 0
) -> None:
    line.speaker, line.method, line.confidence, line.run = (
        speaker,
        method,
        confidence,
        run,
    )


def _apply_explicit(
    paragraphs: list[SpeakerParagraph],
    lines: list[Line],
    quotes_by_paragraph: list[list[tuple[int, int]]],
) -> None:
    counters: Counter[int] = Counter()
    for line in lines:
        position = counters[line.paragraph]
        counters[line.paragraph] += 1
        paragraph = paragraphs[line.paragraph]
        speaker = _explicit_speaker(
            paragraph.text,
            paragraph.mentions,
            quotes_by_paragraph[line.paragraph],
            position,
        )

        if speaker is not None:
            _resolve(line, speaker, EXPLICIT_TAG, 0.95)


def _narration_speaker(
    paragraphs: list[SpeakerParagraph],
    quotes_by_paragraph: list[list[tuple[int, int]]],
    index: int,
) -> UUID | None:
    own = _distinct(_outside(paragraphs[index].mentions, quotes_by_paragraph[index]))
    if len(own) == 1:
        return next(iter(own))

    if own:
        return None

    for neighbour in (index - 1, index + 1):
        if not 0 <= neighbour < len(paragraphs) or quotes_by_paragraph[neighbour]:
            continue

        names = _distinct(paragraphs[neighbour].mentions)
        if len(names) == 1:
            return next(iter(names))

    return None


def _apply_narration(
    paragraphs: list[SpeakerParagraph],
    lines: list[Line],
    quotes_by_paragraph: list[list[tuple[int, int]]],
) -> None:
    for line in lines:
        if line.speaker is not None:
            continue

        speaker = _narration_speaker(paragraphs, quotes_by_paragraph, line.paragraph)
        if speaker is not None:
            _resolve(line, speaker, NARRATION, 0.65)


def _propagate_within_paragraph(lines: list[Line]) -> None:
    """Give a paragraph's unresolved quotes the speaker of its resolved one.

    ``"Yes," said Elizabeth, "and no."`` is one speech in two spans.
    """
    by_paragraph: dict[int, list[Line]] = {}
    for line in lines:
        by_paragraph.setdefault(line.paragraph, []).append(line)

    for group in by_paragraph.values():
        speakers = {line.speaker for line in group if line.speaker is not None}
        if len(speakers) != 1:
            continue

        anchor = next(line for line in group if line.speaker is not None)
        for line in group:
            if line.speaker is None:
                _resolve(line, anchor.speaker, anchor.method, anchor.confidence * 0.9)


def _apply_alternation(
    paragraphs: list[SpeakerParagraph],
    lines: list[Line],
    quotes_by_paragraph: list[list[tuple[int, int]]],
    participants: set[UUID],
) -> None:
    """Fill unresolved lines in a two-party exchange from the line before.

    Applies when the scene has exactly two participants, or when the two lines
    before this one were already spoken by two different characters. Runs
    forward only and stops after ``MAX_ALTERNATION_RUN`` inferred lines: an
    error would otherwise propagate down the whole conversation.
    """
    by_paragraph: dict[int, list[Line]] = {}
    for line in lines:
        by_paragraph.setdefault(line.paragraph, []).append(line)

    for index in sorted(by_paragraph):
        group = by_paragraph[index]
        if all(line.speaker is not None for line in group):
            continue

        previous = by_paragraph.get(index - 1)
        if not previous or previous[-1].speaker is None:
            continue

        last = previous[-1]
        parties: set[UUID] = set()
        if len(participants) == 2:
            parties = set(participants)
        else:
            before = by_paragraph.get(index - 2)
            if before and before[-1].speaker not in (None, last.speaker):
                parties = {last.speaker, before[-1].speaker}

        if len(parties) != 2 or last.speaker not in parties:
            continue

        outside = _distinct(
            _outside(paragraphs[index].mentions, quotes_by_paragraph[index])
        )
        if outside - parties:
            continue

        run = last.run + 1 if last.method == ALTERNATION else 1
        if run > MAX_ALTERNATION_RUN:
            continue

        other = next(iter(parties - {last.speaker}))
        for line in group:
            if line.speaker is None:
                _resolve(line, other, ALTERNATION, max(0.5, 0.65 - 0.03 * run), run)


def attribute_scene(
    scene: SceneText,
    matchers: dict[UUID, tuple[re.Pattern[str], dict[str, UUID]] | None],
) -> tuple[list[SpeakerParagraph], list[Line]]:
    """Run the deterministic cascade over one scene: tags, narration, alternation.

    Returns:
        The scene's paragraphs and its dialogue lines, some possibly still
        unresolved for the LLM fallback.
    """
    paragraphs, lines, quotes = extract_scene_lines(scene, matchers)
    _apply_explicit(paragraphs, lines, quotes)
    _propagate_within_paragraph(lines)
    _apply_narration(paragraphs, lines, quotes)
    _propagate_within_paragraph(lines)
    _apply_alternation(paragraphs, lines, quotes, set(scene.participants))

    return paragraphs, lines


def _excerpt(paragraphs: list[SpeakerParagraph], line: Line) -> str:
    start = max(0, line.paragraph - 1)
    window = paragraphs[start : line.paragraph + 2]
    joined = "\n".join(paragraph.text for paragraph in window)
    if len(joined) > EXCERPT_CHARS * 3:
        joined = joined[: EXCERPT_CHARS * 3]

    return joined


async def _ask(
    roster: list[UUID],
    names: dict[UUID, str],
    items: list[tuple[Line, str, str]],
    *,
    book_id: UUID,
) -> dict[int, tuple[UUID | None, float]]:
    """Ask for speakers of ``items``, halving the batch if the reply is cut off."""
    listing = "\n".join(
        f"{number}. {names[cid]}" for number, cid in enumerate(roster, 1)
    )
    body = "\n\n".join(
        f"Line {number}:\n{excerpt}\n<<<{quote}>>>"
        for number, (_, excerpt, quote) in enumerate(items, 1)
    )
    prompt = SPEAKER_PROMPT.format(roster=listing, lines=body)

    try:
        result = await structured_call(
            prompt,
            SpeakerBatchOutput,
            purpose=LLMPurpose.CHARACTER_EXTRACT,
            book_id=str(book_id),
            stage="speaker_attribution",
        )
    except LengthLimitError:
        if len(items) == 1:
            raise

        midpoint = len(items) // 2
        first = await _ask(roster, names, items[:midpoint], book_id=book_id)
        second = await _ask(roster, names, items[midpoint:], book_id=book_id)
        merged = {**first, **{key + midpoint: value for key, value in second.items()}}

        return merged

    answers: dict[int, tuple[UUID | None, float]] = {}
    for assignment in result.assignments:
        if not 1 <= assignment.line <= len(items):
            continue

        speaker = None
        if assignment.speaker is not None and 1 <= assignment.speaker <= len(roster):
            speaker = roster[assignment.speaker - 1]

        answers[assignment.line - 1] = (speaker, assignment.confidence)

    return answers


async def resolve_with_llm(
    work: list[tuple[SceneText, list[SpeakerParagraph], list[Line]]],
    names: dict[UUID, str],
    *,
    book_id: UUID,
) -> int:
    """Fallback for lines the cascade could not resolve, batched per scene.

    A speaker is accepted only when the model names someone from the scene's
    own roster with confidence of at least ``MIN_LLM_CONFIDENCE``; anything
    else stays unresolved, because a wrong attribution is worse than none.

    Returns:
        The number of lines the model resolved.
    """
    gate = asyncio.Semaphore(LLM_CONCURRENCY)
    resolved = 0

    async def run_batch(roster: list[UUID], batch: list[tuple[Line, str, str]]) -> None:
        nonlocal resolved

        async with gate:
            answers = await _ask(roster, names, batch, book_id=book_id)

        for position, (speaker, confidence) in answers.items():
            if speaker is None or confidence < MIN_LLM_CONFIDENCE:
                continue

            _resolve(batch[position][0], speaker, LLM, min(confidence, 0.8))
            resolved += 1

    tasks = []
    for scene, paragraphs, lines in work:
        pending = [line for line in lines if line.speaker is None]
        roster = [
            character_id
            for character_id, _ in sorted(
                scene.participants.items(), key=lambda item: -item[1]
            )
            if character_id in names
        ][:MAX_ROSTER]

        if not pending or len(roster) < 1:
            continue

        for start in range(0, len(pending), LLM_LINES_PER_CALL):
            batch = [
                (
                    line,
                    _excerpt(paragraphs, line),
                    scene.chunk_texts[line.chunk_id][line.char_start : line.char_end],
                )
                for line in pending[start : start + LLM_LINES_PER_CALL]
            ]
            tasks.append(run_batch(roster, batch))

    await asyncio.gather(*tasks)

    return resolved


def to_rows(lines: list[Line]) -> list[DialogueLineRow]:
    """Convert attributed lines to persistable rows; unresolved keeps ``NULL``."""
    rows = [
        DialogueLineRow(
            chunk_id=line.chunk_id,
            char_start=line.char_start,
            char_end=line.char_end,
            speaker_character_id=line.speaker,
            method=line.method if line.speaker is not None else UNRESOLVED,
            confidence=line.confidence if line.speaker is not None else 0.0,
        )
        for line in lines
    ]

    return rows
