import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Column, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from ...contracts.enums import ResolutionMethod, ReviewStatus, ReviewTaskType
from .base import TimestampMixin


class ReviewTask(TimestampMixin, table=True):
    """Work the pipeline stopped rather than guessed at.

    ``payload`` carries everything the interface needs to decide without a
    second round trip, and ``priority`` is blast radius — a merge on a
    protagonist cascades through dozens of edges, a minor-pair confirmation
    does not.
    """

    __table_args__ = (
        Index("ix_review_status_priority", "status", "priority"),
        Index("ix_review_project", "project_id"),
        Index("ix_review_thread", "graph_thread_id"),
    )

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", ondelete="CASCADE")
    book_id: UUID | None = Field(
        default=None, foreign_key="book.id", ondelete="CASCADE"
    )

    task_type: ReviewTaskType
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    graph_thread_id: str | None = Field(default=None)
    priority: int = Field(default=0)
    status: ReviewStatus = Field(default=ReviewStatus.OPEN)

    resolution: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    resolved_at: datetime | None = Field(default=None)
    resolved_by: UUID | None = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL"
    )


class CorrectionFeedback(TimestampMixin, table=True):
    """What a human changed, and what the model believed AT THE TIME.

    Decision-time confidence cannot be reconstructed later, and without it the
    calibration work in Sprint 8 has nothing to fit.
    """

    __table_args__ = (Index("ix_feedback_task_type", "task_type"),)

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", ondelete="CASCADE")
    review_task_id: UUID | None = Field(
        default=None, foreign_key="reviewtask.id", ondelete="SET NULL"
    )
    task_type: ReviewTaskType
    model_value: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    human_value: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    model_confidence: float | None = Field(default=None)
    resolution_method: ResolutionMethod = Field(default=ResolutionMethod.HUMAN)
    evidence: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
