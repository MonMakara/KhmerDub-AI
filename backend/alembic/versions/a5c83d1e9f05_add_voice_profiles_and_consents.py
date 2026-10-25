"""add_voice_profiles_and_consents

Revision ID: a5c83d1e9f05
Revises: f4a81b2c3d04
Create Date: 2026-10-25 14:05:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5c83d1e9f05'
down_revision: Union[str, Sequence[str], None] = 'f4a81b2c3d04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add voice_consents and voice_profiles tables."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'voice_consents' not in tables:
        op.create_table(
            'voice_consents',
            sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
            sa.Column('speaker_name', sa.String(length=255), nullable=False),
            sa.Column('authorized_by', sa.String(length=255), nullable=False),
            sa.Column('consent_statement', sa.Text(), nullable=False),
            sa.Column('is_authorized', sa.Boolean(), server_default='1', nullable=False),
            sa.Column('signature_hash', sa.String(length=64), nullable=False),
            sa.Column('granted_at', sa.DateTime(), nullable=False),
        )

    if 'voice_profiles' not in tables:
        op.create_table(
            'voice_profiles',
            sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('gender', sa.String(length=20), server_default='neutral', nullable=False),
            sa.Column('language', sa.String(length=10), server_default='km', nullable=False),
            sa.Column('reference_audio_path', sa.String(length=1024), nullable=False),
            sa.Column('reference_audio_duration', sa.Float(), nullable=True),
            sa.Column('reference_audio_sample_rate', sa.Integer(), server_default='48000', nullable=True),
            sa.Column('reference_transcript', sa.Text(), nullable=True),
            sa.Column('audio_format', sa.String(length=20), server_default='wav', nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
            sa.Column('consent_id', sa.String(length=36), sa.ForeignKey('voice_consents.id', ondelete='CASCADE'), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    """Downgrade schema: drop voice_profiles and voice_consents tables."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'voice_profiles' in tables:
        op.drop_table('voice_profiles')
    if 'voice_consents' in tables:
        op.drop_table('voice_consents')
