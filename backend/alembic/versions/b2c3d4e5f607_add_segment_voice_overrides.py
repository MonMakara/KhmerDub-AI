"""Add optional unit voice assignments; legacy audio keeps a null revision."""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f607"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("translation_segments")}
    additions = [
        sa.Column("voice_override_provider", sa.String(50), nullable=True),
        sa.Column("voice_override_id", sa.String(100), nullable=True),
        sa.Column("voice_source_keys", sa.Text(), nullable=True),
        sa.Column("voice_revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tts_error", sa.Text(), nullable=True),
    ]
    for column in additions:
        if column.name not in columns:
            op.add_column("translation_segments", column)
    audio_columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("generated_audios")}
    if "voice_revision" not in audio_columns:
        op.add_column("generated_audios", sa.Column("voice_revision", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("generated_audios", "voice_revision")
    for name in ("tts_error", "voice_revision", "voice_source_keys", "voice_override_id", "voice_override_provider"):
        op.drop_column("translation_segments", name)
