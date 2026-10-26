"""add_project_pipeline_version

Revision ID: fc8a4b3d2e07
Revises: fa7b3c2d1e06
Create Date: 2026-10-26 22:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fc8a4b3d2e07'
down_revision: Union[str, Sequence[str], None] = 'fa7b3c2d1e06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add pipeline_version to projects table, defaulting existing rows to 'v1'."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    project_columns = [col['name'] for col in insp.get_columns('projects')]
    if 'pipeline_version' not in project_columns:
        op.add_column(
            'projects',
            sa.Column(
                'pipeline_version',
                sa.String(length=20),
                nullable=False,
                server_default='v1',
            ),
        )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    project_columns = [col['name'] for col in insp.get_columns('projects')]
    if 'pipeline_version' in project_columns:
        op.drop_column('projects', 'pipeline_version')
