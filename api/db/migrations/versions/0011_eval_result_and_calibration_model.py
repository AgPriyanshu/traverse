"""eval_result and calibration_model

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: Union[str, Sequence[str], None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Sprint 8 contract freeze: evalrun already exists (Sprint 1's broad
    freeze, api/db/models/ops_model.py::EvalRun) and holds one ablation
    run's own aggregate config/metrics. Only eval_result (one row per
    ablation-matrix cell, scoped to a book) and calibration_model (a fitted
    confidence-to-accuracy mapping) are genuinely new.
    """
    op.create_table(
        "evalresult",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("eval_run_id", sa.Uuid(), nullable=False),
        sa.Column("axis", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("book_key", sa.String(), nullable=True),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["eval_run_id"], ["evalrun.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evalresult_run", "evalresult", ["eval_run_id"])
    op.create_table(
        "calibrationmodel",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("bins", postgresql.JSONB(), nullable=False),
        sa.Column("ece_before", sa.Float(), nullable=True),
        sa.Column("ece_after", sa.Float(), nullable=True),
        sa.Column("fitted_on_n", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("calibrationmodel")
    op.drop_index("ix_evalresult_run", table_name="evalresult")
    op.drop_table("evalresult")
