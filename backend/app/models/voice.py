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
    Boolean,
)
from sqlalchemy.orm import relationship

from app.database.session import Base


class VoiceConsent(Base):
    __tablename__ = "voice_consents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    speaker_name = Column(String(255), nullable=False)
    authorized_by = Column(String(255), nullable=False)
    consent_statement = Column(Text, nullable=False)
    is_authorized = Column(Boolean, default=True, nullable=False)
    signature_hash = Column(String(64), nullable=False)
    granted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    profiles = relationship(
        "VoiceProfile",
        back_populates="consent",
        cascade="all, delete-orphan",
    )


class VoiceProfile(Base):
    __tablename__ = "voice_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    gender = Column(String(20), default="neutral", nullable=False)
    language = Column(String(10), default="km", nullable=False)
    reference_audio_path = Column(String(1024), nullable=False)
    reference_audio_duration = Column(Float, nullable=True)
    reference_audio_sample_rate = Column(Integer, default=48000, nullable=True)
    reference_transcript = Column(Text, nullable=True)
    audio_format = Column(String(20), default="wav", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    consent_id = Column(
        String(36),
        ForeignKey("voice_consents.id", ondelete="CASCADE"),
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
    consent = relationship("VoiceConsent", back_populates="profiles")
