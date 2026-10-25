from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.project import VoiceOptionResponse


class VoiceConsentResponse(BaseModel):
    id: str
    speaker_name: str
    authorized_by: str
    consent_statement: str
    signature_hash: str
    granted_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VoiceProfileResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    gender: str = "neutral"
    language: str = "km"
    reference_audio_duration: Optional[float] = None
    reference_audio_sample_rate: Optional[int] = 48000
    reference_transcript: Optional[str] = None
    audio_format: str = "wav"
    is_active: bool = True
    consent: VoiceConsentResponse
    created_at: datetime
    updated_at: datetime
    model_status: str = "Not Configured (Phase 13B Research)"

    model_config = ConfigDict(from_attributes=True)


class VoiceProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    gender: Optional[str] = None
    reference_transcript: Optional[str] = None


class VoiceStudioResponse(BaseModel):
    system_voices: List[VoiceOptionResponse]
    custom_profiles: List[VoiceProfileResponse]
    total_custom_profiles: int
    cloning_engine_status: str = "Not Configured (Phase 13B Research)"
    default_provider: str
    default_voice: str
