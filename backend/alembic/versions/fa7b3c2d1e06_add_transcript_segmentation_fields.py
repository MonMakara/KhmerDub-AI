"""add_transcript_segmentation_fields

Revision ID: fa7b3c2d1e06
Revises: e9f1a2b3c4d5
Create Date: 2026-10-26 18:05:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa7b3c2d1e06'
down_revision: Union[str, Sequence[str], None] = 'e9f1a2b3c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add segmentation fields to projects and transcript_segments."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # 1. Projects table
    project_columns = [col['name'] for col in insp.get_columns('projects')]
    if 'segmentation_mode' not in project_columns:
        op.add_column('projects', sa.Column('segmentation_mode', sa.String(length=50), nullable=True, server_default='sentence'))
    if 'raw_transcript_json' not in project_columns:
        op.add_column('projects', sa.Column('raw_transcript_json', sa.Text(), nullable=True))

    # 2. Transcript segments table
    segment_columns = [col['name'] for col in insp.get_columns('transcript_segments')]
    if 'words_json' not in segment_columns:
        op.add_column('transcript_segments', sa.Column('words_json', sa.Text(), nullable=True))
    if 'is_approximate' not in segment_columns:
        op.add_column('transcript_segments', sa.Column('is_approximate', sa.Boolean(), nullable=False, server_default='0'))
    if 'is_manually_edited' not in segment_columns:
        op.add_column('transcript_segments', sa.Column('is_manually_edited', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    segment_columns = [col['name'] for col in insp.get_columns('transcript_segments')]
    if 'is_manually_edited' in segment_columns:
        op.drop_column('transcript_segments', 'is_manually_edited')
    if 'is_approximate' in segment_columns:
        op.drop_column('transcript_segments', 'is_approximate')
    if 'words_json' in segment_columns:
        op.drop_column('transcript_segments', 'words_json')

    project_columns = [col['name'] for col in insp.get_columns('projects')]
    if 'raw_transcript_json' in project_columns:
        op.drop_column('projects', 'raw_transcript_json')
    if 'segmentation_mode' in project_columns:
        op.drop_column('projects', 'segmentation_mode')
