"""add_toolkit_tts_segments_table

Revision ID: c7f20e3a5b21
Revises: b6e19d2f4a10
Create Date: 2026-10-25 15:45:00.000000

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7f20e3a5b21'
down_revision: Union[str, Sequence[str], None] = 'b6e19d2f4a10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add toolkit_tts_segments table."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'toolkit_tts_segments' not in tables:
        op.create_table(
            'toolkit_tts_segments',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('task_id', sa.String(length=36), sa.ForeignKey('toolkit_tasks.id', ondelete='CASCADE'), nullable=False),
            sa.Column('segment_order', sa.Integer(), nullable=False),
            sa.Column('text', sa.Text(), nullable=False),
            sa.Column('audio_file_path', sa.String(length=1024), nullable=True),
            sa.Column('duration_seconds', sa.Float(), nullable=True),
            sa.Column('file_size_bytes', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), default=datetime.utcnow, nullable=False),
            sa.Column('updated_at', sa.DateTime(), default=datetime.utcnow, nullable=False),
        )
        op.create_index('ix_toolkit_tts_segments_task_id', 'toolkit_tts_segments', ['task_id'])


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'toolkit_tts_segments' in tables:
        op.drop_table('toolkit_tts_segments')
