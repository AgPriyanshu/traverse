"""scenes, scene participants and dialogue lines

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-23 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Sprint 4 SCR-1 (be1, S4.8/S4.9): the scene stage skipped silently without
    these tables. Shapes mirror the requested SCR.
    """
    op.create_table(
        'scene',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('book_id', sa.Uuid(), nullable=False),
        sa.Column('chapter_id', sa.Uuid(), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('page_start', sa.Integer(), nullable=False),
        sa.Column('page_end', sa.Integer(), nullable=False),
        sa.Column('chunk_ids', postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['book.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_scene_book_position', 'scene', ['book_id', 'position'])
    op.create_table(
        'scene_participant',
        sa.Column('scene_id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.Uuid(), nullable=False),
        sa.Column('mention_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['scene_id'], ['scene.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['character_id'], ['character.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('scene_id', 'character_id'),
    )
    op.create_table(
        'dialogue_line',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('book_id', sa.Uuid(), nullable=False),
        sa.Column('chunk_id', sa.Uuid(), nullable=False),
        sa.Column('char_start', sa.Integer(), nullable=False),
        sa.Column('char_end', sa.Integer(), nullable=False),
        sa.Column('speaker_character_id', sa.Uuid(), nullable=True),
        sa.Column('method', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['book.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chunk_id'], ['documentchunk.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['speaker_character_id'], ['character.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_dialogue_line_book', 'dialogue_line', ['book_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_dialogue_line_book', table_name='dialogue_line')
    op.drop_table('dialogue_line')
    op.drop_table('scene_participant')
    op.drop_index('ix_scene_book_position', table_name='scene')
    op.drop_table('scene')
