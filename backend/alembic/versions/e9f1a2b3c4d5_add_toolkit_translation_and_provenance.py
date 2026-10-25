"""add_toolkit_translation_and_provenance

Revision ID: e9f1a2b3c4d5
Revises: d8e412f8a931
Create Date: 2026-10-26 00:05:00.000000

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9f1a2b3c4d5'
down_revision: Union[str, Sequence[str], None] = 'd8e412f8a931'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add source_task_id and is_outdated to toolkit_tasks, create toolkit_translation_segments."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    task_columns = [col['name'] for col in insp.get_columns('toolkit_tasks')]

    if 'source_task_id' not in task_columns:
        op.add_column('toolkit_tasks', sa.Column('source_task_id', sa.String(length=36), nullable=True))
        try:
            op.create_index('ix_toolkit_tasks_source_task_id', 'toolkit_tasks', ['source_task_id'])
        except Exception:
            pass

    if 'is_outdated' not in task_columns:
        op.add_column('toolkit_tasks', sa.Column('is_outdated', sa.Boolean(), nullable=False, server_default=sa.text('0')))

    tables = insp.get_table_names()
    if 'toolkit_translation_segments' not in tables:
        op.create_table(
            'toolkit_translation_segments',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('task_id', sa.String(length=36), sa.ForeignKey('toolkit_tasks.id', ondelete='CASCADE'), nullable=False),
            sa.Column('segment_order', sa.Integer(), nullable=False),
            sa.Column('start_time', sa.Float(), nullable=True),
            sa.Column('end_time', sa.Float(), nullable=True),
            sa.Column('source_text', sa.Text(), nullable=False),
            sa.Column('translated_text', sa.Text(), nullable=False),
            sa.Column('edited_text', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='completed'),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), default=datetime.utcnow, nullable=False),
            sa.Column('updated_at', sa.DateTime(), default=datetime.utcnow, nullable=False),
        )
        op.create_index('ix_toolkit_translation_segments_task_id', 'toolkit_translation_segments', ['task_id'])


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'toolkit_translation_segments' in tables:
        op.drop_table('toolkit_translation_segments')

    with op.batch_alter_table('toolkit_tasks') as batch_op:
        try:
            batch_op.drop_index('ix_toolkit_tasks_source_task_id')
        except Exception:
            pass
        batch_op.drop_column('is_outdated')
        batch_op.drop_column('source_task_id')
