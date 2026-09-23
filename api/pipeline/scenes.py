import re
from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

DINKUS_RE = re.compile(
    r"^\s*(?:[*⁂∗·•~\-—_=#]\s*){3,}$"
    r"|^\s*(?:\*\s+){2,}\*\s*$",
    re.MULTILINE,
)
TIME_JUMP_RE = re.compile(
    r"^\s*(?:the\s+(?:next|following|same)\s+(?:day|morning|evening|night|week)"
    r"|(?:next|that)\s+(?:day|morning|evening|night)"
    r"|(?:some|a\s+few|several|many)\s+(?:days|weeks|months|years|hours)\s+(?:later|after)"
    r"|(?:a|one)\s+(?:week|month|year|fortnight)\s+(?:later|after)"
    r"|(?:in\s+the\s+)?(?:morning|evening)\b"
    r"|meanwhile\b|the\s+following)",
    re.IGNORECASE,
)

MIN_CHUNKS_BEFORE_CAST_SHIFT = 2
MAX_CHUNKS_PER_SCENE = 12


@dataclass(frozen=True)
class SceneChunk:
    chunk_id: UUID
    chapter_id: UUID | None
    page_start: int
    page_end: int
    text: str
    characters: Counter[UUID] = field(default_factory=Counter)


@dataclass
class SceneDraft:
    chunk_ids: list[UUID]
    chapter_id: UUID | None
    page_start: int
    page_end: int
    participants: Counter[UUID]


def _starts_with_dinkus(text: str) -> bool:
    first_line = text.lstrip().split("\n", 1)[0]
    is_dinkus = DINKUS_RE.fullmatch(first_line) is not None

    return is_dinkus


def _has_inner_dinkus(text: str) -> bool:
    found = DINKUS_RE.search(text) is not None

    return found


def _starts_with_time_jump(text: str) -> bool:
    jumped = TIME_JUMP_RE.match(text) is not None

    return jumped


def _cast_shifted(scene_cast: set[UUID], chunk_cast: set[UUID]) -> bool:
    """Whether a chunk's cast shares nobody with the scene that precedes it."""
    if not scene_cast or not chunk_cast:
        return False

    shifted = scene_cast.isdisjoint(chunk_cast)

    return shifted


def _boundary_before(
    current: list[SceneChunk], scene_cast: set[UUID], chunk: SceneChunk
) -> bool:
    previous = current[-1]

    if chunk.chapter_id != previous.chapter_id:
        return True

    if _starts_with_dinkus(chunk.text) or _has_inner_dinkus(chunk.text):
        return True

    if len(current) >= MAX_CHUNKS_PER_SCENE:
        return True

    if _starts_with_time_jump(chunk.text) and len(current) >= 2:
        return True

    recent_cast = {
        character
        for member in current[-MIN_CHUNKS_BEFORE_CAST_SHIFT:]
        for character in member.characters
    }
    if len(current) >= MIN_CHUNKS_BEFORE_CAST_SHIFT and _cast_shifted(
        recent_cast or scene_cast, set(chunk.characters)
    ):
        return True

    return False


def _draft(members: list[SceneChunk]) -> SceneDraft:
    participants: Counter[UUID] = Counter()
    for member in members:
        participants.update(member.characters)

    draft = SceneDraft(
        chunk_ids=[member.chunk_id for member in members],
        chapter_id=members[0].chapter_id,
        page_start=min(member.page_start for member in members),
        page_end=max(member.page_end for member in members),
        participants=participants,
    )

    return draft


def segment_scenes(chunks: list[SceneChunk]) -> list[SceneDraft]:
    """Group chunks, in document order, into contiguous scenes.

    A scene boundary falls before a chunk that changes chapter, opens with (or
    contains) a dinkus line, opens with a time-jump phrase, follows a run that
    reached the size cap, or introduces a cast that shares nobody with the
    last two chunks. A wrong boundary costs a little recall downstream; no
    boundaries at all costs pass 2 the ability to batch coherently, so the
    heuristics lean towards cutting.

    Args:
        chunks: Every chunk of a book in document order, each carrying the
            characters resolved as mentioned in it.

    Returns:
        Scenes that cover every chunk exactly once, in order.
    """
    scenes: list[SceneDraft] = []
    current: list[SceneChunk] = []
    scene_cast: set[UUID] = set()

    for chunk in chunks:
        if current and _boundary_before(current, scene_cast, chunk):
            scenes.append(_draft(current))
            current, scene_cast = [], set()

        current.append(chunk)
        scene_cast.update(chunk.characters)

    if current:
        scenes.append(_draft(current))

    return scenes
