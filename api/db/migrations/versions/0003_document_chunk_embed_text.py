"""document_chunk_embed_text

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-01 19:35:03.206222

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401 (used by generated column types, e.g. sqlmodel.sql.sqltypes.AutoString)


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'documentchunk',
        sa.Column('embed_text', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    )
    op.alter_column(
        'documentchunk',
        'headings',
        type_=sa.ARRAY(sa.String()),
        existing_type=sa.VARCHAR(),
        postgresql_using='ARRAY[headings]',
        nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'documentchunk',
        'headings',
        type_=sa.VARCHAR(),
        existing_type=sa.ARRAY(sa.String()),
        postgresql_using='array_to_string(headings, \',\')',
        nullable=False,
    )
    op.drop_column('documentchunk', 'embed_text')
