import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    DateTime,
    ForeignKey,
    Text,
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship
import enum

from app.database.session import Base


class ProjectStatus(str, enum.Enum):
    CREATED = "created"
    UPLOADED = "uploaded"
    AUDIO_EXTRACTED = "audio_extracted"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    TRANSLATING = "translating"
    TRANSLATED = "translated"
    GENERATING_VOICE = "generating_voice"
    VOICE_GENERATED = "voice_generated"
    SYNCHRONIZING = "synchronizing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    original_video_path = Column(String(1024), nullable=True)
    original_language = Column(String(10), default="en", nullable=False)
    target_language = Column(String(10), default="km", nullable=False)
    status = Column(
        SQLEnum(ProjectStatus),
        default=ProjectStatus.CREATED,
        nullable=False,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    video = relationship("Video", back_populates="project", uselist=False, cascade="all, delete-orphan")
    transcript_segments = relationship(
        "TranscriptSegment",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="TranscriptSegment.start_time",
    )
    translation_segments = relationship(
        "TranslationSegment",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="TranslationSegment.segment_order",
    )
    jobs = relationship(
        "ProcessingJob",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProcessingJob.created_at.desc()",
    )
    generated_audios = relationship(
        "GeneratedAudio",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class Video(Base):
    __tablename__ = "videos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), unique=True, nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(1024), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    duration_seconds = Column(Float, nullable=True)
    extracted_audio_path = Column(String(1024), nullable=True)
    exported_video_path = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="video")


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    segment_order = Column(Integer, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="transcript_segments")


class TranslationSegment(Base):
    __tablename__ = "translation_segments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    transcript_segment_id = Column(String(36), ForeignKey("transcript_segments.id"), nullable=True)
    segment_order = Column(Integer, nullable=False)
    khmer_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="translation_segments")
    generated_audio = relationship("GeneratedAudio", back_populates="translation_segment", uselist=False)


class GeneratedAudio(Base):
    __tablename__ = "generated_audios"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    translation_segment_id = Column(String(36), ForeignKey("translation_segments.id"), nullable=True)
    audio_path = Column(String(1024), nullable=False)
    duration_seconds = Column(Float, nullable=True)
    provider = Column(String(50), default="gtts", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="generated_audios")
    translation_segment = relationship("TranslationSegment", back_populates="generated_audio")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    job_type = Column(String(50), nullable=False)  # e.g., extract_audio, transcribe, translate, tts, dub
    status = Column(SQLEnum(JobStatus), default=JobStatus.PENDING, nullable=False)
    progress_percentage = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="jobs")
