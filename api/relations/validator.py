import logging
import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from ..contracts.graph import QUOTE_MAX_CHARS
from ..graph import ontology
from .cues import has_cue
from .roster import Roster
from .schemas import RawRelation

logger = logging.getLogger(__name__)

_WS_RE = re.compile(r"\s+")
_QUOTE_TRANSLATION = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "—": "-"})


class RejectReason(StrEnum):
    UNKNOWN_PREDICATE = "unknown_predicate"
    NOT_EXTRACTABLE = "not_extractable"
    OFF_ROSTER_SUBJECT = "off_roster_subject"
    OFF_ROSTER_OBJECT = "off_roster_object"
    SELF_RELATION = "self_relation"
    EMPTY_QUOTE = "empty_quote"
    QUOTE_NOT_IN_CHUNK = "quote_not_in_chunk"
    QUOTE_NAMES_OTHERS = "quote_names_other_characters"
    ENDPOINT_NOT_IN_CHUNK = "endpoint_not_in_chunk"
    PREDICATE_CUE_MISSING = "predicate_cue_missing"


@dataclass(frozen=True)
class ValidRelation:
    subject_id: UUID
    predicate: str
    object_id: UUID
    quote: str
    assertion_type: str
    asserted_by_id: UUID | None
    confidence: float


class RejectionStats:
    def __init__(self) -> None:
        self.accepted = 0
        self.by_reason: Counter[str] = Counter()

    @property
    def total(self) -> int:
        return self.accepted + sum(self.by_reason.values())

    @property
    def off_roster_rate(self) -> float:
        off = (
            self.by_reason[RejectReason.OFF_ROSTER_SUBJECT]
            + self.by_reason[RejectReason.OFF_ROSTER_OBJECT]
        )
        rate = off / self.total if self.total else 0.0

        return rate

    def as_dict(self) -> dict:
        payload = {
            "accepted": self.accepted,
            "rejected": dict(sorted(self.by_reason.items())),
            "off_roster_rate": round(self.off_roster_rate, 4),
        }

        return payload


def fold(text: str) -> str:
    """Case-fold and collapse whitespace and typographic quotes for comparison."""
    folded = _WS_RE.sub(" ", text.translate(_QUOTE_TRANSLATION)).strip().casefold()

    return folded


def quote_in_chunk(quote: str, chunk_text: str) -> bool:
    """Return whether ``quote`` is a verbatim substring of the chunk.

    Whitespace, case and typographic quotes are folded, since Docling and the
    model disagree on those, but no word may differ: a paraphrase is fabricated
    evidence.
    """
    needle = fold(quote)
    present = bool(needle) and needle in fold(chunk_text)

    return present


def validate(
    raw: RawRelation, chunk_text: str, roster: Roster, stats: RejectionStats
) -> ValidRelation | None:
    """Validate one model relation, counting the reason when it is rejected.

    Checks: predicate in the ontology and extractable, subject and object both
    resolve to roster characters, not a self-relation, the quote appears in the
    chunk, both endpoints are named somewhere in the chunk (not necessarily the
    quote), a quote naming other roster characters doesn't name only them, and
    a cue word for the specific predicate is present.

    A quote naming *neither* endpoint (pure pronouns -- "she refused him") is
    no longer rejected on its own: Sprint 4's recall audit measured that this
    check absorbed most of the gain from widening the grounding text (chunk to
    scene) into a different rejection reason instead of an accept, with the
    same real relations still missing. `QUOTE_NAMES_OTHERS` above already
    guards the actual risk Sprint 3's spike found (a real quote attached to
    the wrong pair) -- that only fires when the quote names roster characters
    who are *not* this pair. A pronoun-only quote makes no such wrong-pair
    claim, and whether the pronoun genuinely resolves to this endpoint is a
    coreference judgement the second-pass verifier (`verify.py`) already makes
    by reading the quote against the claim; a substring check can't make it at
    all, so it was rejecting some pronoun quotes the verifier would have kept.

    Args:
        raw: The model's relation.
        chunk_text: The full text of the cited chunk.
        roster: The book's roster.
        stats: Accumulates accepted and rejected counts by reason.

    Returns:
        The validated relation with names resolved to character ids, or
        ``None`` when rejected.
    """
    predicate = str(raw.predicate)
    reason = _reject_reason(raw, predicate, chunk_text, roster)
    if reason is not None:
        stats.by_reason[reason] += 1
        logger.debug("rejected relation (%s): %r", reason, raw)

        return None

    subject_id = roster.resolve(raw.subject)
    object_id = roster.resolve(raw.object)
    speaker = roster.resolve(raw.asserted_by) if raw.asserted_by else None
    stats.accepted += 1
    valid = ValidRelation(
        subject_id=subject_id,  # type: ignore[arg-type]
        predicate=predicate,
        object_id=object_id,  # type: ignore[arg-type]
        quote=raw.quote.strip()[:QUOTE_MAX_CHARS],
        assertion_type=raw.assertion_type.value,
        asserted_by_id=speaker,
        confidence=raw.confidence,
    )

    return valid


def _reject_reason(
    raw: RawRelation, predicate: str, chunk_text: str, roster: Roster
) -> RejectReason | None:
    reason: RejectReason | None = None
    subject_id = roster.resolve(raw.subject)
    object_id = roster.resolve(raw.object)

    if not ontology.is_predicate(predicate):
        reason = RejectReason.UNKNOWN_PREDICATE
    elif not ontology.is_extracted(predicate):
        reason = RejectReason.NOT_EXTRACTABLE
    elif subject_id is None:
        reason = RejectReason.OFF_ROSTER_SUBJECT
    elif object_id is None:
        reason = RejectReason.OFF_ROSTER_OBJECT
    elif subject_id == object_id:
        reason = RejectReason.SELF_RELATION
    elif not raw.quote.strip():
        reason = RejectReason.EMPTY_QUOTE
    elif not quote_in_chunk(raw.quote, chunk_text):
        reason = RejectReason.QUOTE_NOT_IN_CHUNK
    elif not (
        roster.mentions(chunk_text, subject_id)
        and roster.mentions(chunk_text, object_id)
    ):
        reason = RejectReason.ENDPOINT_NOT_IN_CHUNK
    else:
        named = roster.mentioned_in(raw.quote)
        if named and subject_id not in named and object_id not in named:
            reason = RejectReason.QUOTE_NAMES_OTHERS
        elif not has_cue(predicate, raw.quote):
            reason = RejectReason.PREDICATE_CUE_MISSING

    return reason
