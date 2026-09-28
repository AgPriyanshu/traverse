"""routing_policy, cost_snapshot, and upload_session

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-28 22:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Sprint 9 contract freeze: RoutingPolicyOut and MetricsOut already existed
    (frozen since Sprint 1, api/contracts/api.py) as the response shapes for
    the still-501 /ops/routing-policy and /ops/metrics routes. All three
    tables here are genuinely new -- nothing has ever persisted a routing
    policy, a cost rollup, or an upload session before this sprint.
    """
    op.create_table(
        "routingpolicy",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("purposes", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_routing_policy_version", "routingpolicy", ["version"]
    )
    op.create_table(
        "costsnapshot",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_cost_usd", sa.Float(), nullable=False),
        sa.Column("by_stage", postgresql.JSONB(), nullable=False),
        sa.Column("by_purpose", postgresql.JSONB(), nullable=False),
        sa.Column("query_count", sa.Integer(), nullable=False),
        sa.Column("book_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cost_snapshot_window", "costsnapshot", ["window_end"])
    op.create_table(
        "uploadsession",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_token", sa.String(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("ip_hash", sa.String(), nullable=True),
        sa.Column("upload_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_upload_session_token", "uploadsession", ["session_token"], unique=True
    )
    op.create_index(
        "ix_upload_session_expires", "uploadsession", ["expires_at"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_upload_session_expires", table_name="uploadsession")
    op.drop_index("ix_upload_session_token", table_name="uploadsession")
    op.drop_table("uploadsession")
    op.drop_index("ix_cost_snapshot_window", table_name="costsnapshot")
    op.drop_table("costsnapshot")
    op.drop_index("ix_routing_policy_version", table_name="routingpolicy")
    op.drop_table("routingpolicy")
