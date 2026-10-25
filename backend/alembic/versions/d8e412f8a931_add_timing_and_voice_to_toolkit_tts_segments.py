"""add_timing_and_voice_to_toolkit_tts_segments

Revision ID: d8e412f8a931
Revises: c7f20e3a5b21
Create Date: 2026-10-25 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8e412f8a931'
down_revision: Union[str, Sequence[str], None] = 'c7f20e3a5b21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add start_time, end_time, voice, provider to toolkit_tts_segments."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    columns = [col['name'] for col in insp.get_columns('toolkit_tts_segments')]

    if 'start_time' not in columns:
        op.add_column('toolkit_tts_segments', sa.Column('start_time', sa.Float(), nullable=True))
    if 'end_time' not in columns:
        op.add_column('toolkit_tts_segments', sa.Column('end_time', sa.Float(), nullable=True))
    if 'voice' not in columns:
        op.add_column('toolkit_tts_segments', sa.Column('voice', sa.String(length=100), nullable=True))
    if 'provider' not in columns:
        op.add_column('toolkit_tts_segments', sa.Column('provider', sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('toolkit_tts_segments') as batch_op:
        batch_op.drop_column('provider')
        batch_op.drop_column('voice')
        batch_op.drop_column('end_time')
        batch_op.drop_column('start_time')
