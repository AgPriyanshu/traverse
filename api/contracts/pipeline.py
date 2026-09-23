"""Contracts for the ingestion pipeline. Frozen at the sprint contract freeze."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from .enums import DetectionMethod, StageName, StageState


class SeriesPosition(BaseModel):
    """A point in a project. A standalone book is ``(1, chapter)``.

    Ordering compares as a tuple, which is also how it is compared in SQL —
    ``(first_book_order, first_chapter) <= (:b, :c)``.
    """

    book_order: int = Field(default=1, ge=1)
    chapter: int | None = Field(default=None, ge=0)

    def as_tuple(self) -> tuple[int, int]:
        return (self.book_order, self.chapter if self.chapter is not None else 0)

    def __le__(self, other: "SeriesPosition") -> bool:
        return self.as_tuple() <= other.as_tuple()


class ChapterInfo(BaseModel):
    is_chapter: bool
    number: int | None = None
    title: str | None = None
    text: str | None = None
    detection_method: DetectionMethod = DetectionMethod.REGEX
    confidence: float | None = None


class ChunkPayload(BaseModel):
    """One passage, ready to persist. Page provenance is not optional."""

    text: str
    text_embedding: list[float] | None = None
    pages: list[int] = Field(min_length=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    chapter_number: int | None = None
    token_count: int | None = None
    headings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _pages_coherent(self) -> "ChunkPayload":
        if self.page_end < self.page_start:
            raise ValueError("page_end precedes page_start")
        if self.page_start != min(self.pages) or self.page_end != max(self.pages):
            raise ValueError("page_start/page_end disagree with pages[]")

        return self


class StageStatus(BaseModel):
    stage: StageName
    state: StageState
    attempt: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error: str | None = None


class IngestionRunOut(BaseModel):
    run_id: UUID
    book_id: UUID
    stages: list[StageStatus]
    trace_url: str | None = None
