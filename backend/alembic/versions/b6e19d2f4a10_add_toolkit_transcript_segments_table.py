"""add_toolkit_transcript_segments_table

Revision ID: b6e19d2f4a10
Revises: a5c83d1e9f05
Create Date: 2026-10-25 14:30:00.000000

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6e19d2f4a10'
down_revision: Union[str, Sequence[str], None] = 'a5c83d1e9f05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add toolkit_tasks (if missing) and toolkit_transcript_segments table."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'toolkit_tasks' not in tables:
        op.create_table(
            'toolkit_tasks',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('tool_type', sa.String(length=50), nullable=False, server_default='video_to_audio'),
            sa.Column('source_type', sa.String(length=20), nullable=False, server_default='upload'),
            sa.Column('source_project_id', sa.String(length=36), nullable=True),
            sa.Column('source_filename', sa.String(length=255), nullable=False),
            sa.Column('source_file_path', sa.String(length=1024), nullable=False),
            sa.Column('source_media_metadata', sa.Text(), nullable=True),
            sa.Column('target_format', sa.String(length=20), nullable=False, server_default='mp3'),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
            sa.Column('progress_percentage', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('output_file_path', sa.String(length=1024), nullable=True),
            sa.Column('output_filename', sa.String(length=255), nullable=True),
            sa.Column('output_duration_seconds', sa.Float(), nullable=True),
            sa.Column('output_file_size_bytes', sa.Integer(), nullable=True),
            sa.Column('output_media_metadata', sa.Text(), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), default=datetime.utcnow, nullable=False),
            sa.Column('updated_at', sa.DateTime(), default=datetime.utcnow, nullable=False),
        )

    if 'toolkit_transcript_segments' not in tables:
        op.create_table(
            'toolkit_transcript_segments',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('task_id', sa.String(length=36), sa.ForeignKey('toolkit_tasks.id', ondelete='CASCADE'), nullable=False),
            sa.Column('segment_order', sa.Integer(), nullable=False),
            sa.Column('start_time', sa.Float(), nullable=False),
            sa.Column('end_time', sa.Float(), nullable=False),
            sa.Column('raw_text', sa.Text(), nullable=False),
            sa.Column('edited_text', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), default=datetime.utcnow, nullable=False),
            sa.Column('updated_at', sa.DateTime(), default=datetime.utcnow, nullable=False),
        )
        op.create_index('ix_toolkit_transcript_segments_task_id', 'toolkit_transcript_segments', ['task_id'])


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'toolkit_transcript_segments' in tables:
        op.drop_table('toolkit_transcript_segments')
