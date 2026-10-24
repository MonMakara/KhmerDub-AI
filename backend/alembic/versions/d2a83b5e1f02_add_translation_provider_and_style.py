"""add_translation_provider_and_style

Revision ID: d2a83b5e1f02
Revises: c1f72a4d9e01
Create Date: 2026-10-25 00:17:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2a83b5e1f02'
down_revision: Union[str, Sequence[str], None] = 'c1f72a4d9e01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    project_cols = [c['name'] for c in insp.get_columns('projects')]
    trans_cols = [c['name'] for c in insp.get_columns('translation_segments')]

    if 'translation_provider' not in project_cols:
        op.add_column(
            'projects',
            sa.Column('translation_provider', sa.String(length=50), server_default='nllb', nullable=False),
        )
    if 'translation_style' not in project_cols:
        op.add_column(
            'projects',
            sa.Column('translation_style', sa.String(length=50), server_default='natural', nullable=False),
        )

    if 'style' not in trans_cols:
        op.add_column(
            'translation_segments',
            sa.Column('style', sa.String(length=50), server_default='natural', nullable=True),
        )
    if 'explanation' not in trans_cols:
        op.add_column(
            'translation_segments',
            sa.Column('explanation', sa.Text(), nullable=True),
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('translation_segments', 'explanation')
    op.drop_column('translation_segments', 'style')
    op.drop_column('projects', 'translation_style')
    op.drop_column('projects', 'translation_provider')
