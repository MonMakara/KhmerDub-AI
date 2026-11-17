"""Add multi-speaker diarization support and project_speakers table."""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f60708"
down_revision = "b2c3d4e5f607"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Add speaker_label to transcript_segments if not exists
    t_cols = {c["name"] for c in inspector.get_columns("transcript_segments")}
    if "speaker_label" not in t_cols:
        op.add_column("transcript_segments", sa.Column("speaker_label", sa.String(50), nullable=True))

    # 2. Add speaker_label to translation_segments if not exists
    tr_cols = {c["name"] for c in inspector.get_columns("translation_segments")}
    if "speaker_label" not in tr_cols:
        op.add_column("translation_segments", sa.Column("speaker_label", sa.String(50), nullable=True))

    # 3. Create project_speakers table if not exists
    tables = inspector.get_table_names()
    if "project_speakers" not in tables:
        op.create_table(
            "project_speakers",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("speaker_label", sa.String(50), nullable=False),
            sa.Column("display_name", sa.String(100), nullable=False),
            sa.Column("detected_gender", sa.String(20), server_default="unknown", nullable=False),
            sa.Column("average_pitch_hz", sa.Float(), nullable=True),
            sa.Column("color", sa.String(30), server_default="indigo", nullable=False),
            sa.Column("assigned_voice_provider", sa.String(50), nullable=True),
            sa.Column("assigned_voice_id", sa.String(100), nullable=True),
            sa.Column("segment_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("total_duration", sa.Float(), server_default="0.0", nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("project_speakers")
    op.drop_column("translation_segments", "speaker_label")
    op.drop_column("transcript_segments", "speaker_label")
