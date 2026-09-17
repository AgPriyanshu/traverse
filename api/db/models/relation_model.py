import uuid
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlmodel import Field, Relationship

from ...contracts.enums import AssertionType, RelationFamily, RelationStatus
from .base import TimestampMixin

QUOTE_MAX_CHARS = 400


class Relation(TimestampMixin, table=True):
    """One edge per relationship, project-wide.

    Evidence is drawn from every book that establishes it.

    Validity is SERIES POSITION — ``(book_order, chapter)``. A standalone book
    is ``(1, chapter)``, so there is one code path and no branch on project
    kind. A change of predicate CLOSES this edge and opens a new one; it never
    overwrites, because the history is the interesting part.
    """

    __table_args__ = (
        UniqueConstraint(
            "subject_character_id",
            "predicate",
            "object_character_id",
            "first_book_order",
            "first_chapter",
            name="uq_relation_aggregation_key",
        ),
        CheckConstraint(
            "subject_character_id <> object_character_id", name="ck_relation_no_self"
        ),
        Index("ix_relation_project_predicate", "project_id", "predicate"),
        Index("ix_relation_subject", "subject_character_id"),
        Index("ix_relation_object", "object_character_id"),
        Index(
            "ix_relation_position", "project_id", "first_book_order", "first_chapter"
        ),
    )

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", ondelete="CASCADE")
    subject_character_id: UUID = Field(foreign_key="character.id", ondelete="CASCADE")
    object_character_id: UUID = Field(foreign_key="character.id", ondelete="CASCADE")

    # Validated against api/graph/ontology.yaml, not a database enum: adding a
    # predicate must stay a config change.
    predicate: str
    family: RelationFamily

    confidence: float = Field(default=0.0)
    status: RelationStatus = Field(default=RelationStatus.ACTIVE)
    assertion_type: AssertionType = Field(default=AssertionType.NARRATED)
    asserted_by_character_id: UUID | None = Field(
        default=None, foreign_key="character.id", ondelete="SET NULL"
    )
    hearsay: bool = Field(default=False)

    first_book_order: int = Field(default=1)
    first_chapter: int | None = Field(default=None)
    last_book_order: int | None = Field(default=None)
    last_chapter: int | None = Field(default=None)

    evidence_count: int = Field(default=0)
    human_verified: bool = Field(default=False)
    graph_edge_id: str | None = Field(default=None)

    evidence: list["RelationEvidence"] = Relationship(
        back_populates="relation", cascade_delete=True
    )


class RelationEvidence(TimestampMixin, table=True):
    """The pages that prove an edge. An edge with none of these must not exist."""

    __table_args__ = (
        CheckConstraint(
            f"length(quote) <= {QUOTE_MAX_CHARS}", name="ck_evidence_quote_len"
        ),
        CheckConstraint(
            "page_start >= 1 AND page_end >= page_start", name="ck_evidence_pages"
        ),
        Index("ix_evidence_relation", "relation_id"),
        Index("ix_evidence_book", "book_id"),
    )

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    relation_id: UUID = Field(foreign_key="relation.id", ondelete="CASCADE")
    book_id: UUID = Field(foreign_key="book.id", ondelete="CASCADE")
    chunk_id: UUID = Field(foreign_key="documentchunk.id", ondelete="CASCADE")

    book_order: int = Field(default=1)
    chapter_no: int | None = Field(default=None)
    page_start: int
    page_end: int
    quote: str
    assertion_type: AssertionType = Field(default=AssertionType.NARRATED)
    confidence: float | None = Field(default=None)

    relation: Relation = Relationship(back_populates="evidence")
