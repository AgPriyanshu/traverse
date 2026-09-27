"""conversation and conversation_turn

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-27 06:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Sprint 6 contract freeze: query_log already exists (Sprint 1's broad
    freeze, api/db/models/ops_model.py::QueryLog), and contracts/api.py
    already carries QueryRequest, the discriminated QueryEvent SSE union
    (TokenEvent | CitationEvent | RouteEvent | InterruptEvent | DoneEvent |
    ErrorEvent, Field(discriminator="type")), and CitationOut. Only
    conversation and conversation_turn are genuinely new.
    """
    op.create_table(
        "conversation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("scope_book_id", sa.Uuid(), nullable=True),
        sa.Column("scope_chapter", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scope_book_id"], ["book.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversation_project", "conversation", ["project_id"])
    op.create_table(
        "conversationturn",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("query_log_id", sa.Uuid(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("question", sa.String(), nullable=False),
        sa.Column("answer", sa.String(), nullable=True),
        sa.Column("resolved_character_ids", postgresql.JSONB(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversation.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["query_log_id"], ["querylog.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_turn_conversation", "conversationturn", ["conversation_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_conversation_turn_conversation", table_name="conversationturn")
    op.drop_table("conversationturn")
    op.drop_index("ix_conversation_project", table_name="conversation")
    op.drop_table("conversation")
