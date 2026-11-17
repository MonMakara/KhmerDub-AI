"""add_voice_profile_library_and_project_id

Revision ID: d4e5f6070809
Revises: c3d4e5f60708
Create Date: 2026-11-06 18:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6070809'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f60708'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add is_library and project_id columns to voice_profiles."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns('voice_profiles')]

    if 'is_library' not in cols:
        op.add_column(
            'voice_profiles',
            sa.Column('is_library', sa.Boolean(), server_default='1', nullable=False),
        )

    if 'project_id' not in cols:
        op.add_column(
            'voice_profiles',
            sa.Column('project_id', sa.String(length=36), nullable=True),
        )


def downgrade() -> None:
    """Downgrade schema: drop is_library and project_id columns."""
    with op.batch_alter_table('voice_profiles') as batch_op:
        batch_op.drop_column('project_id')
        batch_op.drop_column('is_library')
