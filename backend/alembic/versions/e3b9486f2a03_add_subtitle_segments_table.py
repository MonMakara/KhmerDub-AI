"""add_subtitle_segments_table

Revision ID: e3b9486f2a03
Revises: d2a83b5e1f02
Create Date: 2026-10-25 12:56:00.000000

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3b9486f2a03'
down_revision: Union[str, Sequence[str], None] = 'd2a83b5e1f02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add subtitle_segments table if not exists."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'subtitle_segments' not in tables:
        op.create_table(
            'subtitle_segments',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('project_id', sa.String(length=36), sa.ForeignKey('projects.id'), nullable=False),
            sa.Column('language', sa.String(length=10), nullable=False),
            sa.Column('segment_order', sa.Integer(), nullable=False),
            sa.Column('start_time', sa.Float(), nullable=False),
            sa.Column('end_time', sa.Float(), nullable=False),
            sa.Column('text', sa.Text(), nullable=False),
            sa.Column('is_customized', sa.Boolean(), server_default='0', nullable=False),
            sa.Column('created_at', sa.DateTime(), default=datetime.utcnow, nullable=False),
            sa.Column('updated_at', sa.DateTime(), default=datetime.utcnow, nullable=False),
            sa.UniqueConstraint('project_id', 'language', 'segment_order', name='uq_project_language_segment'),
        )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'subtitle_segments' in tables:
        op.drop_table('subtitle_segments')
