"""rename_documentchunk_document_fk

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-01 19:46:38.726723

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401 (used by generated column types, e.g. sqlmodel.sql.sqltypes.AutoString)


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('documentchunk', 'document', new_column_name='document_id')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('documentchunk', 'document_id', new_column_name='document')
