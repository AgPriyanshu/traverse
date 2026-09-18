import uuid
from uuid import UUID

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, Relationship

from ...contracts.enums import BookStatus, DetectionMethod, ProjectKind
from .base import TimestampMixin


class Project(TimestampMixin, table=True):
    """A standalone novel or an ordered series.

    Characters and relations hang off the project, not the book: a standalone
    is simply a one-book project, so there is no second code path.
    """

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    slug: str = Field(unique=True, index=True)
    kind: ProjectKind = Field(default=ProjectKind.STANDALONE)
    roster_version: int = Field(default=0)

    books: list["Book"] = Relationship(back_populates="project")


class Book(TimestampMixin, table=True):
    __table_args__ = (
        UniqueConstraint("project_id", "series_order", name="uq_book_project_order"),
        Index("ix_book_project", "project_id"),
    )

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", ondelete="CASCADE")
    series_order: int | None = Field(default=None)
    title: str
    author: str | None = Field(default=None)
    translator: str | None = Field(default=None)
    content_hash: str = Field(unique=True, index=True)
    storage_key: str | None = Field(default=None)
    page_count: int | None = Field(default=None)
    chapter_count: int | None = Field(default=None)
    status: BookStatus = Field(default=BookStatus.QUEUED)

    project: Project = Relationship(back_populates="books")
    chapters: list["Chapter"] = Relationship(back_populates="book")


class Chapter(TimestampMixin, table=True):
    __table_args__ = (
        UniqueConstraint("book_id", "number", name="uq_chapter_book_number"),
        Index("ix_chapter_book", "book_id"),
    )

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    book_id: UUID = Field(foreign_key="book.id", ondelete="CASCADE")
    number: int | None = Field(default=None)
    title: str | None = Field(default=None)
    heading_text: str | None = Field(default=None)
    page_start: int
    page_end: int
    detection_method: DetectionMethod = Field(default=DetectionMethod.REGEX)
    confidence: float | None = Field(default=None)
    human_verified: bool = Field(default=False)

    book: Book = Relationship(back_populates="chapters")
