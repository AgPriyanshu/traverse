"""Non-character rejection (S3.2, F2.4).

Places, houses, estates, organisations, ships, and deities invoked in an oath
are not characters. Every rejection is classified with a structured call over
the candidate's own contexts and stored with its reason — a candidate that
disappears silently cannot be measured by the eval harness or overturned by
Sprint 7's review queue.
"""

import asyncio
import logging
from uuid import UUID

from ..contracts.enums import CandidateKind, LLMPurpose
from ..db.models import BookCharacterCandidate
from ..llm import structured_call
from .filtering import plausible_character_name
from .prompts import REJECTION_PROMPT
from .schemas import RejectionOutput

logger = logging.getLogger(__name__)

# Enough contexts to see a genuinely ambiguous case (a house whose name is
# also used for its family) without paying for a candidate mentioned 200 times.
_MAX_CONTEXTS = 10

# A candidate pass 1 already believes is a person is only re-checked while it
# is rare. Frequent names are the book's cast; the tail is where a critic, an
# author or another novel's heroine quoted in a preface hides.
_RECHECK_PERSON_BELOW = 10

# Half of vLLM's 16 sequences; classification is the only load at this point.
_CONCURRENCY = 8

_FRONT_MATTER_REASON = (
    "mentioned only outside any chapter (preface, introduction or appendix)"
)
_NON_NAME_REASON = "not a proper name: pronoun, role, group or fragment"


def _only_outside_chapters(candidate: BookCharacterCandidate) -> bool:
    outside = bool(candidate.contexts) and all(
        context.get("chapter_number") is None for context in candidate.contexts
    )

    return outside


async def classify_candidates(
    candidates: list[BookCharacterCandidate], *, book_id: UUID
) -> tuple[list[dict], list[UUID]]:
    """Classify every candidate not already confidently a person.

    Args:
        candidates: This book's pass-1 candidates.
        book_id: Tags the Langfuse trace.

    Returns:
        A ``(rejections, corrected_to_person)`` pair. ``rejections`` is one
        ``{"candidate_id", "kind", "reason"}`` dict per candidate the
        classifier rejected — callers persist these to ``rejected_candidate``
        and drop them from the active set. ``corrected_to_person`` lists
        candidates pass-1 guessed wrong (a house whose name is also its
        family's, "the Bennets of Longbourn") that the classifier confirmed
        as a person after all — callers must write this back to the
        candidate's stored ``kind``, or S3.3's cascade will silently exclude
        it as a non-person on its next read. Candidates already ``kind ==
        person`` from pass-1's own guess are trusted without a second call
        once they have ten or more mentions.
    """
    rejections: list[dict] = []
    corrected_to_person: list[UUID] = []
    to_classify: list[BookCharacterCandidate] = []
    # Only meaningful when chapter detection worked: a book with no detected
    # chapters would otherwise have every candidate rejected as front matter.
    chapters_detected = any(
        context.get("chapter_number") is not None
        for candidate in candidates
        for context in candidate.contexts
    )

    for candidate in candidates:
        if chapters_detected and _only_outside_chapters(candidate):
            rejections.append(
                {
                    "candidate_id": candidate.id,
                    "kind": CandidateKind.UNKNOWN,
                    "reason": _FRONT_MATTER_REASON,
                }
            )
        elif not plausible_character_name(candidate.surface_form):
            rejections.append(
                {
                    "candidate_id": candidate.id,
                    "kind": CandidateKind.UNKNOWN,
                    "reason": _NON_NAME_REASON,
                }
            )
        elif (
            candidate.kind != CandidateKind.PERSON
            or candidate.mention_count < _RECHECK_PERSON_BELOW
        ):
            to_classify.append(candidate)

    gate = asyncio.Semaphore(_CONCURRENCY)

    async def bounded(candidate: BookCharacterCandidate) -> RejectionOutput:
        async with gate:
            return await _classify(candidate, book_id=book_id)

    results = await asyncio.gather(*(bounded(c) for c in to_classify))

    for candidate, classification in zip(to_classify, results, strict=True):
        if classification.kind == CandidateKind.PERSON:
            if candidate.kind != CandidateKind.PERSON:
                corrected_to_person.append(candidate.id)
            continue

        rejections.append(
            {
                "candidate_id": candidate.id,
                "kind": classification.kind,
                "reason": classification.reason,
            }
        )

    return rejections, corrected_to_person


async def _classify(
    candidate: BookCharacterCandidate, *, book_id: UUID
) -> RejectionOutput:
    contexts = candidate.contexts[:_MAX_CONTEXTS]
    formatted = "\n".join(f"(page {c['page']}) {c['context']}" for c in contexts)
    prompt = REJECTION_PROMPT.format(
        surface_form=candidate.surface_form, contexts=formatted
    )

    result = await structured_call(
        prompt,
        RejectionOutput,
        purpose=LLMPurpose.CHARACTER_EXTRACT,
        book_id=str(book_id),
        stage="extract_characters",
    )

    return result
