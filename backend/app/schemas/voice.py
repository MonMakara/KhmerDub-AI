from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.project import VoiceOptionResponse, ProjectSpeakerResponse


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
    is_library: bool = True
    project_id: Optional[str] = None
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


class CloneCandidateResponse(BaseModel):
    candidate_id: str
    segment_order: int
    segment_ids: List[str]
    start_time: float
    end_time: float
    duration: float
    text: str
    score: float
    preview_url: str


class CloneCandidatesListResponse(BaseModel):
    project_id: str
    candidates: List[CloneCandidateResponse]
    recommended_candidate_id: Optional[str] = None


class CloneFromVideoRequest(BaseModel):
    segment_id: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    voice_name: Optional[str] = None
    set_as_project_voice: bool = True
    store_in_voice_studio: bool = True


class CloneSpeakerVoiceRequest(BaseModel):
    speaker_label: Optional[str] = None  # If None, clones all detected speakers
    store_in_voice_studio: bool = False  # User can choose whether to store in Voice Studio


class ClonedSpeakerItem(BaseModel):
    speaker_label: str
    display_name: str
    voice_profile_id: str
    voice_profile_name: str
    assigned_voice_provider: str = "voxcpm"
    is_library: bool


class CloneSpeakerVoiceResponse(BaseModel):
    project_id: str
    cloned_speakers: List[ClonedSpeakerItem]
    created_profiles_count: int
    message: str


class AutoDiarizeAndCloneRequest(BaseModel):
    min_speakers: int = 1
    max_speakers: int = 6
    store_in_voice_studio: bool = False


class AutoDiarizeAndCloneResponse(BaseModel):
    project_id: str
    speakers_detected: int
    cloned_voices_count: int
    speakers: List[ProjectSpeakerResponse]
    cloned_speakers: List[ClonedSpeakerItem]
    message: str

