import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Column, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship

from ...contracts.enums import QueryRoute, StageName, StageState
from .base import TimestampMixin


class IngestionRun(TimestampMixin, table=True):
    __table_args__ = (Index("ix_run_book", "book_id"),)

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    book_id: UUID = Field(foreign_key="book.id", ondelete="CASCADE")
    trace_url: str | None = Field(default=None)
    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)

    stages: list["IngestionStage"] = Relationship(
        back_populates="run", cascade_delete=True
    )


class IngestionStage(TimestampMixin, table=True):
    """One row per stage per run — what `GET /books/{id}/status` reads."""

    __table_args__ = (
        UniqueConstraint("run_id", "stage", name="uq_stage_run_stage"),
        Index("ix_stage_state", "state"),
    )

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="ingestionrun.id", ondelete="CASCADE")
    stage: StageName
    state: StageState = Field(default=StageState.PENDING)
    attempt: int = Field(default=0)
    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)
    duration_ms: int | None = Field(default=None)
    rows_written: int | None = Field(default=None)
    input_tokens: int | None = Field(default=None)
    output_tokens: int | None = Field(default=None)
    cost_usd: float | None = Field(default=None)
    error_class: str | None = Field(default=None)
    error_message: str | None = Field(default=None)
    traceback: str | None = Field(default=None)

    run: IngestionRun = Relationship(back_populates="stages")


class QueryLog(TimestampMixin, table=True):
    __table_args__ = (Index("ix_querylog_project", "project_id"),)

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", ondelete="CASCADE")
    question: str
    route: QueryRoute | None = Field(default=None)
    cypher_template: str | None = Field(default=None)
    retrieved_ids: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    answer: str | None = Field(default=None)
    citations: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    model_used: str | None = Field(default=None)
    policy_version: int | None = Field(default=None)
    input_tokens: int | None = Field(default=None)
    output_tokens: int | None = Field(default=None)
    cost_usd: float | None = Field(default=None)
    latency_ms: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    # The reading position this question was answered at, so leakage is auditable.
    limit_book_order: int | None = Field(default=None)
    limit_chapter: int | None = Field(default=None)


class EvalRun(TimestampMixin, table=True):
    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    corpus_version: str | None = Field(default=None)
    git_sha: str | None = Field(default=None)
    metrics: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    notes: str | None = Field(default=None)
