import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.database.session import Base


class ToolkitTask(Base):
    """Represents a discrete media processing task within the AI Media Toolkit workspace."""

    __tablename__ = "toolkit_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tool_type = Column(String(50), default="video_to_audio", nullable=False)  # video_to_audio, video_to_transcript, video_to_text, audio_to_transcript, audio_to_text
    source_type = Column(String(20), default="upload", nullable=False)  # upload or project
    source_project_id = Column(String(36), nullable=True)
    source_filename = Column(String(255), nullable=False)
    source_file_path = Column(String(1024), nullable=False)
    source_media_metadata = Column(Text, nullable=True)  # JSON encoded metadata
    target_format = Column(String(20), default="mp3", nullable=False)  # mp3, wav, m4a, srt, vtt, txt, json, csv
    status = Column(String(20), default="pending", nullable=False)  # pending, processing, completed, failed
    progress_percentage = Column(Integer, default=0, nullable=False)
    output_file_path = Column(String(1024), nullable=True)
    output_filename = Column(String(255), nullable=True)
    output_duration_seconds = Column(Float, nullable=True)
    output_file_size_bytes = Column(Integer, nullable=True)
    output_media_metadata = Column(Text, nullable=True)  # JSON encoded metadata
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    segments = relationship(
        "ToolkitTranscriptSegment",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="ToolkitTranscriptSegment.segment_order",
    )
    tts_segments = relationship(
        "ToolkitTTSSegment",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="ToolkitTTSSegment.segment_order",
    )


class ToolkitTranscriptSegment(Base):
    """Represents a discrete timestamped speech segment within a toolkit task."""

    __tablename__ = "toolkit_transcript_segments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("toolkit_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_order = Column(Integer, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    raw_text = Column(Text, nullable=False)
    edited_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    task = relationship("ToolkitTask", back_populates="segments")


class ToolkitTTSSegment(Base):
    """Represents a single synthesized speech segment within a text-to-speech toolkit task."""

    __tablename__ = "toolkit_tts_segments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("toolkit_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_order = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    start_time = Column(Float, nullable=True)
    end_time = Column(Float, nullable=True)
    voice = Column(String(100), nullable=True)
    provider = Column(String(50), nullable=True)
    audio_file_path = Column(String(1024), nullable=True)
    duration_seconds = Column(Float, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    status = Column(String(20), default="pending", nullable=False)  # pending, completed, failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    task = relationship("ToolkitTask", back_populates="tts_segments")

