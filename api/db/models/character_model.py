import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import ARRAY, Column, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship

from ...contracts.enums import CandidateKind, ImportanceTier, ResolutionMethod
from .base import TimestampMixin


class Character(TimestampMixin, table=True):
    """One person, project-wide. One Harry Potter, not seven.

    Derived fields (first/last appearance, series-wide tier and mention count)
    are RECOMPUTED from every appearance after each reconcile, never
    accumulated — that is what makes out-of-order series ingestion
    self-correct.
    """

    __table_args__ = (
        UniqueConstraint(
            "project_id", "canonical_name", name="uq_character_project_name"
        ),
        Index("ix_character_project", "project_id"),
        Index("ix_character_aliases", "aliases", postgresql_using="gin"),
    )

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", ondelete="CASCADE")
    canonical_name: str
    aliases: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    importance_tier: ImportanceTier = Field(default=ImportanceTier.MENTIONED)

    first_book_id: UUID | None = Field(
        default=None, foreign_key="book.id", ondelete="SET NULL"
    )
    first_chapter: int | None = Field(default=None)
    first_page: int | None = Field(default=None)
    last_book_id: UUID | None = Field(
        default=None, foreign_key="book.id", ondelete="SET NULL"
    )
    last_chapter: int | None = Field(default=None)
    mention_count: int = Field(default=0)

    attributes: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    collision_suspected: bool = Field(default=False)
    human_verified: bool = Field(default=False)
    graph_node_id: str | None = Field(default=None)

    appearances: list["CharacterAppearance"] = Relationship(back_populates="character")


class CharacterAppearance(TimestampMixin, table=True):
    """A character's presence in one book.

    This is the append target when a series grows: ingesting book five adds a
    row here rather than a second character.
    """

    __table_args__ = (
        UniqueConstraint(
            "character_id", "book_id", name="uq_appearance_character_book"
        ),
        Index("ix_appearance_book", "book_id"),
    )

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    character_id: UUID = Field(foreign_key="character.id", ondelete="CASCADE")
    book_id: UUID = Field(foreign_key="book.id", ondelete="CASCADE")

    first_page: int | None = Field(default=None)
    first_chapter: int | None = Field(default=None)
    last_page: int | None = Field(default=None)
    last_chapter: int | None = Field(default=None)
    mention_count: int = Field(default=0)
    importance_tier: ImportanceTier = Field(default=ImportanceTier.MENTIONED)
    surface_forms: list[str] = Field(
        default_factory=list, sa_column=Column(ARRAY(String))
    )
    attributes: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))

    character: Character = Relationship(back_populates="appearances")


class CharacterMention(TimestampMixin, table=True):
    __table_args__ = (
        Index("ix_mention_character", "character_id"),
        Index("ix_mention_book", "book_id"),
        Index("ix_mention_chunk", "chunk_id"),
    )

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    character_id: UUID = Field(foreign_key="character.id", ondelete="CASCADE")
    book_id: UUID = Field(foreign_key="book.id", ondelete="CASCADE")
    chunk_id: UUID = Field(foreign_key="documentchunk.id", ondelete="CASCADE")

    surface_form: str
    page: int
    char_start: int | None = Field(default=None)
    char_end: int | None = Field(default=None)
    confidence: float | None = Field(default=None)
    resolution_method: ResolutionMethod = Field(default=ResolutionMethod.EXACT)


class BookCharacterCandidate(TimestampMixin, table=True):
    """Pass-1 output, staged per book.

    Holds a book-local cluster until reconciliation decides whether it is a
    character the project already knows.
    """

    __table_args__ = (Index("ix_candidate_book", "book_id"),)

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    book_id: UUID = Field(foreign_key="book.id", ondelete="CASCADE")
    surface_form: str
    cluster_key: str | None = Field(default=None)
    kind: CandidateKind = Field(default=CandidateKind.UNKNOWN)
    contexts: list[Any] = Field(default_factory=list, sa_column=Column(JSONB))
    mention_count: int = Field(default=0)
    resolved_character_id: UUID | None = Field(
        default=None, foreign_key="character.id", ondelete="SET NULL"
    )


class RejectedCandidate(TimestampMixin, table=True):
    """A candidate the classifier rejected, kept with its reason.

    Never drop one silently: the eval harness measures rejection precision, and
    review can overturn a wrong call.
    """

    __table_args__ = (Index("ix_rejected_book", "book_id"),)

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    book_id: UUID = Field(foreign_key="book.id", ondelete="CASCADE")
    surface_form: str
    kind: CandidateKind = Field(default=CandidateKind.UNKNOWN)
    reason: str
    contexts: list[Any] = Field(default_factory=list, sa_column=Column(JSONB))
    human_verified: bool = Field(default=False)
