"""Contracts for relation extraction and the graph projection."""

from uuid import UUID

from pydantic import BaseModel, Field

from .enums import AssertionType, RelationFamily, RelationStatus
from .pipeline import SeriesPosition

QUOTE_MAX_CHARS = 400


class ExtractedRelation(BaseModel):
    """Pass-2 output for one chunk.

    ``subject_name``/``object_name`` MUST match a known character's canonical
    name or alias; anything else is invention and is rejected before it reaches
    the database.
    """

    subject_name: str
    predicate: str
    object_name: str
    family: RelationFamily
    assertion_type: AssertionType = AssertionType.NARRATED
    asserted_by: str | None = None
    quote: str = Field(max_length=QUOTE_MAX_CHARS)
    chunk_id: UUID
    confidence: float = Field(ge=0.0, le=1.0)


class EvidenceItem(BaseModel):
    chunk_id: UUID
    book_id: UUID
    book_order: int = 1
    chapter_no: int | None = None
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    quote: str = Field(max_length=QUOTE_MAX_CHARS)
    assertion_type: AssertionType = AssertionType.NARRATED
    confidence: float | None = None


class AggregatedRelation(BaseModel):
    """One edge, with evidence from every book that establishes it."""

    subject_character_id: UUID
    predicate: str
    object_character_id: UUID
    family: RelationFamily
    confidence: float = Field(ge=0.0, le=1.0)
    status: RelationStatus = RelationStatus.ACTIVE
    assertion_type: AssertionType = AssertionType.NARRATED
    asserted_by_character_id: UUID | None = None
    hearsay: bool = False
    first: SeriesPosition = Field(default_factory=SeriesPosition)
    last: SeriesPosition | None = None
    evidence: list[EvidenceItem] = Field(min_length=1)
