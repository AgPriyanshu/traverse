import uuid
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, CheckConstraint, Column, Computed, Index, Integer, String
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlmodel import Field

from .base import TimestampMixin

# BGE-M3. Changing this is a migration, not a settings change.
EMBEDDING_DIMENSIONS = 1024


class DocumentChunk(TimestampMixin, table=True):
    """A passage of a book, with the pages it came from.

    Page provenance is mandatory (PRD F1.3) and enforced here by a check
    constraint rather than by convention: nothing downstream may exist without
    tracing back to a page.
    """

    __table_args__ = (
        CheckConstraint(
            "page_start >= 1 AND page_end >= page_start", name="ck_chunk_pages"
        ),
        Index("ix_chunk_book", "book_id"),
        Index("ix_chunk_chapter", "chapter_id"),
        Index("ix_chunk_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunk_embedding_hnsw",
            "text_embedding",
            postgresql_using="hnsw",
            postgresql_ops={"text_embedding": "vector_cosine_ops"},
        ),
    )

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    book_id: UUID = Field(foreign_key="book.id", ondelete="CASCADE")
    chapter_id: UUID | None = Field(
        default=None, foreign_key="chapter.id", ondelete="SET NULL"
    )

    text: str
    headings: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    pages: list[int] = Field(
        default_factory=list, sa_column=Column(ARRAY(Integer), nullable=False)
    )
    page_start: int
    page_end: int
    token_count: int | None = Field(default=None)

    text_embedding: list[float] | None = Field(
        default=None, sa_column=Column(Vector(EMBEDDING_DIMENSIONS))
    )
    # Maintained by Postgres, never written by the application.
    tsv: str | None = Field(
        default=None,
        sa_column=Column(
            TSVECTOR,
            Computed("to_tsvector('english', text)", persisted=True),
            nullable=True,
        ),
    )
