"""Non-character rejection (S3.2, F2.4).

Places, houses, estates, organisations, ships, and deities invoked in an oath
are not characters. Every rejection is classified with a structured call over
the candidate's own contexts and stored with its reason — a candidate that
disappears silently cannot be measured by the eval harness or overturned by
Sprint 7's review queue.
"""

import logging
from uuid import UUID

from ..contracts.enums import CandidateKind, LLMPurpose
from ..db.models import BookCharacterCandidate
from ..llm import structured_call
from .prompts import REJECTION_PROMPT
from .schemas import RejectionOutput

logger = logging.getLogger(__name__)

# Enough contexts to see a genuinely ambiguous case (a house whose name is
# also used for its family) without paying for a candidate mentioned 200 times.
_MAX_CONTEXTS = 10


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
        person`` from pass-1's own guess are trusted without a second call.
    """
    rejections: list[dict] = []
    corrected_to_person: list[UUID] = []

    for candidate in candidates:
        if candidate.kind == CandidateKind.PERSON:
            continue

        classification = await _classify(candidate, book_id=book_id)

        if classification.kind == CandidateKind.PERSON:
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
