"""Pydantic schemas for every structured LLM call the extraction package makes.

Sent to ``structured_call`` as the ``schema`` argument; never used to validate
anything that reaches another package's boundary (that is ``contracts/``'s
job).
"""

from pydantic import BaseModel, Field

from ..contracts.enums import CandidateKind


class MentionOutput(BaseModel):
    """One referring expression the model found in a chunk."""

    surface_form: str
    kind: CandidateKind = CandidateKind.UNKNOWN
    context: str


class ChunkMentionsOutput(BaseModel):
    """Every mention found in one chunk of a sweep batch.

    ``chunk_index`` is 1-based and refers to the chunk's position in the
    prompt's numbered list, not a database id — the model never sees real
    ids, so it cannot echo one back wrong.
    """

    chunk_index: int = Field(ge=1)
    mentions: list[MentionOutput] = Field(default_factory=list)


class MentionSweepOutput(BaseModel):
    """The reply shape for one pass-1 discovery batch (S3.1)."""

    chunks: list[ChunkMentionsOutput] = Field(default_factory=list)


class RejectionOutput(BaseModel):
    """Whether a candidate is a person, and why not if it isn't (S3.2)."""

    kind: CandidateKind
    reason: str
    is_ambiguous: bool = False


class AdjudicationOutput(BaseModel):
    """LLM adjudication for one residual alias pair (S3.3 stage 5)."""

    same_person: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class AttributeItem(BaseModel):
    """One attribute with the citation that grounds it.

    Mirrors the relation-evidence rule one level up: an attribute with no
    page is not stored (S3.5).
    """

    key: str
    value: str
    page: int = Field(ge=1)
    quote: str


class AttributesOutput(BaseModel):
    """The reply shape for one character's attribute-extraction call (S3.5)."""

    attributes: list[AttributeItem] = Field(default_factory=list)
