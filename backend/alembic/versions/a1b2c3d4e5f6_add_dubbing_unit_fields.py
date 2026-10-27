"""add_dubbing_unit_fields

Revision ID: a1b2c3d4e5f6
Revises: fc8a4b3d2e07
Create Date: 2026-10-27 08:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'fc8a4b3d2e07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add dubbing unit fields to translation_segments and transcript_segments."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    trans_cols = [col['name'] for col in insp.get_columns('translation_segments')]
    if 'start_time' not in trans_cols:
        op.add_column('translation_segments', sa.Column('start_time', sa.Float(), nullable=True))
    if 'end_time' not in trans_cols:
        op.add_column('translation_segments', sa.Column('end_time', sa.Float(), nullable=True))
    if 'source_segment_ids' not in trans_cols:
        op.add_column('translation_segments', sa.Column('source_segment_ids', sa.Text(), nullable=True))
    if 'source_text' not in trans_cols:
        op.add_column('translation_segments', sa.Column('source_text', sa.Text(), nullable=True))

    tr_cols = [col['name'] for col in insp.get_columns('transcript_segments')]
    if 'dubbing_unit_id' not in tr_cols:
        op.add_column('transcript_segments', sa.Column('dubbing_unit_id', sa.String(length=36), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    trans_cols = [col['name'] for col in insp.get_columns('translation_segments')]
    if 'source_text' in trans_cols:
        op.drop_column('translation_segments', 'source_text')
    if 'source_segment_ids' in trans_cols:
        op.drop_column('translation_segments', 'source_segment_ids')
    if 'end_time' in trans_cols:
        op.drop_column('translation_segments', 'end_time')
    if 'start_time' in trans_cols:
        op.drop_column('translation_segments', 'start_time')

    tr_cols = [col['name'] for col in insp.get_columns('transcript_segments')]
    if 'dubbing_unit_id' in tr_cols:
        op.drop_column('transcript_segments', 'dubbing_unit_id')
