"""reconciliation_decision and character_death

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-26 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Sprint 5 contract freeze: behaviour tables, not restructuring. Character,
    relation and character_appearance have been project-scoped since migration
    0006, and the indexes the freeze asked for on character_appearance(book_id)
    and relation(project_id, first_book_order) already exist (ix_appearance_book,
    ix_relation_position) -- only these two new tables are genuinely new.
    """
    op.create_table(
        "reconciliation_decision",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_cluster_key", sa.String(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=True),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("blocked_by", sa.String(), nullable=True),
        sa.Column("decided_at", sa.String(), nullable=False),
        sa.Column("human_verified", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["book.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["character_id"], ["character.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reconciliation_book", "reconciliation_decision", ["book_id"])
    op.create_table(
        "character_death",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("chapter", sa.Integer(), nullable=True),
        sa.Column("evidence_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["character.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["book_id"], ["book.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evidence_id"], ["relationevidence.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_character_death_character", "character_death", ["character_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_character_death_character", table_name="character_death")
    op.drop_table("character_death")
    op.drop_index("ix_reconciliation_book", table_name="reconciliation_decision")
    op.drop_table("reconciliation_decision")
