import uuid
from uuid import UUID

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class ReconciliationDecision(SQLModel, table=True):
    """The audit trail for cross-book character linking (S5.1/S5.2).

    Every link, every new character, every block, with its reason — a
    reconcile that cannot be explained afterward cannot be trusted.
    """

    __tablename__ = "reconciliation_decision"
    __table_args__ = (Index("ix_reconciliation_book", "book_id"),)

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    book_id: UUID = Field(foreign_key="book.id", ondelete="CASCADE")
    candidate_cluster_key: str
    character_id: UUID | None = Field(
        default=None, foreign_key="character.id", ondelete="SET NULL"
    )
    method: str
    confidence: float = Field(default=0.0)
    blocked_by: str | None = Field(default=None)
    decided_at: str
    human_verified: bool = Field(default=False)


class CharacterDeath(SQLModel, table=True):
    """A character's established death — the primary cross-book blocking signal.

    A later book naming the same surface form is a namesake, a flashback, or a
    resurrection, never an automatic link, once this row exists.
    """

    __tablename__ = "character_death"
    __table_args__ = (Index("ix_character_death_character", "character_id"),)

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    character_id: UUID = Field(foreign_key="character.id", ondelete="CASCADE")
    book_id: UUID = Field(foreign_key="book.id", ondelete="CASCADE")
    chapter: int | None = Field(default=None)
    evidence_id: UUID | None = Field(
        default=None, foreign_key="relationevidence.id", ondelete="SET NULL"
    )
