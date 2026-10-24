"""add_project_tts_voice_fields

Revision ID: c1f72a4d9e01
Revises: b90d366cd5b0
Create Date: 2026-10-24 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1f72a4d9e01'
down_revision: Union[str, Sequence[str], None] = 'b90d366cd5b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_cols = [c['name'] for c in insp.get_columns('projects')]

    if 'tts_provider' not in existing_cols:
        op.add_column(
            'projects',
            sa.Column('tts_provider', sa.String(length=50), server_default='gtts', nullable=False),
        )
    if 'tts_voice' not in existing_cols:
        op.add_column(
            'projects',
            sa.Column('tts_voice', sa.String(length=100), server_default='default', nullable=False),
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('projects', 'tts_voice')
    op.drop_column('projects', 'tts_provider')
