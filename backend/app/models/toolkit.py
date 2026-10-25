import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, Text

from app.database.session import Base


class ToolkitTask(Base):
    """Represents a discrete media processing task within the AI Media Toolkit workspace."""

    __tablename__ = "toolkit_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tool_type = Column(String(50), default="video_to_audio", nullable=False)  # e.g. video_to_audio
    source_type = Column(String(20), default="upload", nullable=False)  # upload or project
    source_project_id = Column(String(36), nullable=True)
    source_filename = Column(String(255), nullable=False)
    source_file_path = Column(String(1024), nullable=False)
    source_media_metadata = Column(Text, nullable=True)  # JSON encoded metadata
    target_format = Column(String(20), default="mp3", nullable=False)  # mp3, wav, m4a
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
