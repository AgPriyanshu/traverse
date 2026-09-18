"""chapter human_verified

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-18 13:26:34.472097

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401
import pgvector.sqlalchemy  # noqa: F401 (used by generated column types, e.g. sqlmodel.sql.sqltypes.AutoString)

# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    SCR-1: chapters need the same human_verified guard character and relation
    already carry, so a corrected chapter boundary (S7's confirm_chapter_split
    review task) survives a re-segmentation.

    Autogenerate also proposed dropping checkpoint_writes, checkpoint_migrations,
    checkpoints and checkpoint_blobs — LangGraph's Postgres checkpointer owns
    those tables (api/graph/checkpoint.py::setup_checkpointer()), not Alembic.
    Stripped, per the warning already on record in plans/sprint-1/HANDOFF.md:
    "Never alembic revision --autogenerate without excluding them."
    """
    op.add_column('chapter', sa.Column('human_verified', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column('chapter', 'human_verified', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chapter', 'human_verified')
