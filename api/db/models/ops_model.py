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

    results: list["EvalResult"] = Relationship(
        back_populates="eval_run", cascade_delete=True
    )


class EvalResult(TimestampMixin, table=True):
    """One ablation-matrix cell's outcome, scoped to one book within a run.

    ``EvalRun.metrics`` holds the run's own aggregate; a run sweeps several
    axis values (PRD Appendix A), so each cell's own numbers live here.
    """

    __table_args__ = (Index("ix_evalresult_run", "eval_run_id"),)

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    eval_run_id: UUID = Field(foreign_key="evalrun.id", ondelete="CASCADE")
    axis: str
    label: str
    book_key: str | None = Field(default=None)
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    metrics: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))

    eval_run: EvalRun = Relationship(back_populates="results")


class CalibrationModel(TimestampMixin, table=True):
    """A fitted confidence→accuracy mapping, built from Sprint 7's
    ``CorrectionFeedback`` store."""

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    task_type: str
    version: int = Field(default=1)
    bins: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    ece_before: float | None = Field(default=None)
    ece_after: float | None = Field(default=None)
    fitted_on_n: int = Field(default=0)


class RoutingPolicy(TimestampMixin, table=True):
    """Live per-purpose model routing (F7.3).

    Each write is a new row rather than an update — flipping the policy is
    the ops dashboard's headline action, and losing the ability to say what
    was live five minutes ago would make the demo's own cost/accuracy delta
    unauditable.
    """

    __table_args__ = (Index("ix_routing_policy_version", "version"),)

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    version: int
    purposes: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSONB))


class CostSnapshot(TimestampMixin, table=True):
    """A rolling window's cost rollup — ``/ops/metrics`` reads the latest one
    rather than aggregating raw stage/query rows on every request."""

    __table_args__ = (Index("ix_cost_snapshot_window", "window_end"),)

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    window_start: datetime
    window_end: datetime
    total_cost_usd: float = Field(default=0.0)
    by_stage: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    by_purpose: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    query_count: int = Field(default=0)
    book_count: int = Field(default=0)


class UploadSession(TimestampMixin, table=True):
    """One demo-upload's quota/TTL tracking (ETH-1, ETH-2).

    Isolated per session and never pooled into the shared corpus; a
    background sweep deletes the project once ``expires_at`` passes.
    """

    __table_args__ = (Index("ix_upload_session_expires", "expires_at"),)

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_token: str = Field(unique=True, index=True)
    project_id: UUID | None = Field(
        default=None, foreign_key="project.id", ondelete="CASCADE"
    )
    ip_hash: str | None = Field(default=None)
    upload_count: int = Field(default=0)
    expires_at: datetime
    deleted_at: datetime | None = Field(default=None)
