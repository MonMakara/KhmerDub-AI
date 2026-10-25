"""add_subtitle_readability_and_tracking_fields

Revision ID: f4a81b2c3d04
Revises: e3b9486f2a03
Create Date: 2026-10-25 13:24:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a81b2c3d04'
down_revision: Union[str, Sequence[str], None] = 'e3b9486f2a03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add readability, tracking and timing fields to subtitle_segments."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns('subtitle_segments')]

    if 'source_segment_order' not in cols:
        op.add_column('subtitle_segments', sa.Column('source_segment_order', sa.Integer(), nullable=True))
    if 'source_text_hash' not in cols:
        op.add_column('subtitle_segments', sa.Column('source_text_hash', sa.String(length=64), nullable=True))
    if 'timing_confidence' not in cols:
        op.add_column('subtitle_segments', sa.Column('timing_confidence', sa.String(length=20), server_default='verified', nullable=False))
    if 'is_source_outdated' not in cols:
        op.add_column('subtitle_segments', sa.Column('is_source_outdated', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    pass
