import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, field_validator, Field
from app.models.project import ProjectStatus, JobStatus


class VideoResponse(BaseModel):
    id: str
    filename: str
    file_path: Optional[str] = None
    file_size_bytes: int
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    extracted_audio_path: Optional[str] = None
    audio_timeline_path: Optional[str] = None
    exported_video_path: Optional[str] = None
    exported_duration_seconds: Optional[float] = None
    exported_file_size_bytes: Optional[int] = None
    is_export_outdated: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ProcessingJobResponse(BaseModel):
    id: str
    project_id: str
    job_type: str
    status: JobStatus
    progress_percentage: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TranscriptSegmentResponse(BaseModel):
    source_word_ids: List[str] = Field(default_factory=list)
    source_audio_reference: Optional[str] = None
    duration_seconds: Optional[float] = None
    id: str
    segment_order: int
    start_time: float
    end_time: float
    text: str
    is_approximate: bool = False
    is_manually_edited: bool = False
    dubbing_unit_id: Optional[str] = None
    speaker_label: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TranscriptSegmentUpdate(BaseModel):
    text: str


class TranscriptResponse(BaseModel):
    project_id: str
    status: ProjectStatus
    segmentation_mode: Optional[str] = "sentence"
    segments: List[TranscriptSegmentResponse]


class SegmentationPreviewItem(BaseModel):
    segment_order: int
    start_time: float
    end_time: float
    duration: float
    text: str
    is_approximate: bool = False


class SegmentationPreviewResponse(BaseModel):
    project_id: str
    current_mode: str
    requested_mode: str
    current_segment_count: int
    proposed_segment_count: int
    proposed_segments: List[SegmentationPreviewItem]
    has_user_edits: bool
    has_translations: bool
    translation_count: int
    has_audio: bool
    audio_count: int
    has_exported_video: bool
    requires_confirmation: bool
    impact_warning: Optional[str] = None


class SegmentationApplyRequest(BaseModel):
    mode: str
    confirm: bool = False


class SegmentationApplyResponse(BaseModel):
    project_id: str
    segmentation_mode: str
    segment_count: int
    message: str
    segments: List[TranscriptSegmentResponse]
    invalidated_translations: int
    invalidated_audios: int


class SegmentSplitRequest(BaseModel):
    word_index: int


class SegmentSplitResponse(BaseModel):
    message: str
    segments: List[TranscriptSegmentResponse]


class SegmentVoiceUpdate(BaseModel):
    provider: Optional[str] = None
    voice: Optional[str] = None
    style: Optional[str] = None
    emotion_style: Optional[str] = None


class BulkSegmentVoiceUpdate(SegmentVoiceUpdate):
    segment_ids: List[str] = Field(min_length=1, max_length=1000)


class TranslationSegmentResponse(BaseModel):
    voice_override_provider: Optional[str] = None
    voice_override_id: Optional[str] = None
    effective_tts_provider: Optional[str] = None
    effective_tts_voice: Optional[str] = None
    voice_revision: int = 0
    tts_error: Optional[str] = None
    speaker_label: Optional[str] = None
    id: str
    project_id: str
    transcript_segment_id: Optional[str] = None
    segment_order: int
    khmer_text: str
    english_text: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    source_segment_ids: Optional[List[str]] = None
    source_text: Optional[str] = None
    style: Optional[str] = "natural"
    explanation: Optional[str] = None
    is_manually_edited: bool = False
    is_outdated: bool = False
    created_at: datetime
    updated_at: datetime

    @field_validator("source_segment_ids", mode="before")
    @classmethod
    def parse_source_segment_ids(cls, v: Any) -> Optional[List[str]]:
        if v is None:
            return None
        if isinstance(v, list):
            return [str(x) for x in v]
        if isinstance(v, str):
            v_str = v.strip()
            if not v_str:
                return []
            try:
                parsed = json.loads(v_str)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except Exception:
                pass
            return [v_str]
        return None

    model_config = ConfigDict(from_attributes=True)


class TranslationSegmentUpdate(BaseModel):
    khmer_text: str


class TranslationListResponse(BaseModel):
    project_id: str
    status: ProjectStatus
    segments: List[TranslationSegmentResponse]


class GeneratedAudioResponse(BaseModel):
    voice_revision: Optional[int] = None
    id: str
    project_id: str
    translation_segment_id: Optional[str] = None
    segment_order: Optional[int] = None
    khmer_text: Optional[str] = None
    audio_path: str
    duration_seconds: Optional[float] = None
    provider: str
    voice: str
    is_outdated: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    audio_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class GeneratedAudioListResponse(BaseModel):
    project_id: str
    status: ProjectStatus
    audios: List[GeneratedAudioResponse]
    total_duration_seconds: float = 0.0
    current_count: int = 0
    outdated_count: int = 0
    missing_count: int = 0


class TimingConflictResponse(BaseModel):
    segment_order: int
    transcript_segment_id: str
    start_time: float
    end_time: float
    original_duration: float
    khmer_duration: float
    available_window: float
    effective_window: float
    safety_margin_seconds: float = 0.05
    required_tempo: float
    max_tempo_factor: float = 1.25
    tempo_factor: float
    overflow_seconds: float
    suggested_action: str
    message: str


class AudioStatusSummary(BaseModel):
    total_dubbing_units: int
    current: int
    outdated: int
    missing: int
    generating: int = 0
    failed: int = 0


class ExportStatusResponse(BaseModel):
    project_id: str
    status: ProjectStatus
    job: Optional[ProcessingJobResponse] = None
    is_export_ready: bool
    is_export_outdated: bool
    exported_video_path: Optional[str] = None
    audio_timeline_path: Optional[str] = None
    exported_duration_seconds: Optional[float] = None
    exported_file_size_bytes: Optional[int] = None
    timing_conflicts: List[TimingConflictResponse] = []
    timing_summary: Optional[Dict[str, Any]] = None
    audio_status: Optional[AudioStatusSummary] = None
    pipeline_version: str = "v2.3"
    video_url: Optional[str] = None
    download_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class VoiceOptionResponse(BaseModel):
    provider: str
    voice: str
    label: str
    gender: str
    description: str
    language: Optional[str] = "km"
    sample_rate: Optional[int] = 24000
    is_custom: Optional[bool] = False
    profile_id: Optional[str] = None
    is_available: Optional[bool] = True


class VoiceListResponse(BaseModel):
    voices: List[VoiceOptionResponse]
    default_provider: str
    default_voice: str


class VoicePreviewRequest(BaseModel):
    provider: str = "edge"
    voice: str = "km-KH-PisethNeural"
    text: Optional[str] = None
    emotion_style: Optional[str] = None
    pitch: Optional[str] = None
    volume: Optional[str] = None
    rate: Optional[str] = None


class EmotionStyleResponse(BaseModel):
    id: str
    label_km: str
    label_en: str
    category: str
    icon: str
    description: str
    prosody: Dict[str, str]
    translation_guidance: Optional[str] = None


class EmotionListResponse(BaseModel):
    emotions: List[EmotionStyleResponse]
    default_emotion: str = "calm"


class TranslationProviderResponse(BaseModel):
    id: str
    name: str
    type: str
    description: str
    requires_api_key: bool
    is_configured: bool
    masked_key: Optional[str] = None
    supports_styles: bool
    supports_alternatives: bool
    default_model: str
    available_models: List[str]
    base_url: Optional[str] = None
    configured_model: Optional[str] = None
    requires_base_url: Optional[bool] = False


class TranslationStyleOption(BaseModel):
    id: str
    label: str
    description: str


class TranslationProviderListResponse(BaseModel):
    providers: List[TranslationProviderResponse]
    default_provider: str
    default_style: str
    styles: List[TranslationStyleOption]


class TestConnectionRequest(BaseModel):
    provider: str = "gemini"
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
    provider: str


class SaveCredentialsRequest(BaseModel):
    provider: str
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None


class AIImproveRequest(BaseModel):
    style: Optional[str] = "natural"
    target_duration: Optional[float] = None
    custom_prompt: Optional[str] = None


class AIImproveResponse(BaseModel):
    segment_id: str
    original_text: str
    current_khmer_text: str
    improved_khmer_text: str
    explanation: str
    style: str
    provider: str
    model: str


class AlternativeOption(BaseModel):
    style: str
    label: str
    khmer_text: str
    explanation: Optional[str] = None


class AlternativesResponse(BaseModel):
    segment_id: str
    english_text: str
    current_khmer_text: str
    alternatives: List[AlternativeOption]


class ApplyTranslationRequest(BaseModel):
    khmer_text: str
    style: Optional[str] = None
    explanation: Optional[str] = None


class ProjectTranslationSettingsUpdate(BaseModel):
    translation_provider: str
    translation_style: str


class ProjectVoiceUpdate(BaseModel):
    tts_provider: str
    tts_voice: str


class ProjectCreate(BaseModel):
    title: str
    original_language: str = "en"
    target_language: str = "km"
    translation_provider: Optional[str] = "nllb"
    translation_style: Optional[str] = "natural"
    tts_provider: Optional[str] = "edge"
    tts_voice: Optional[str] = "km-KH-PisethNeural"
    pipeline_version: Optional[str] = "v2.3"


class ProjectUpdate(BaseModel):
    title: str

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        if v is None:
            raise ValueError("Project title cannot be empty")
        stripped = v.strip()
        if not stripped:
            raise ValueError("Project title cannot be empty")
        if len(stripped) > 255:
            raise ValueError("Project title cannot exceed 255 characters")
        return stripped


class ProjectDeleteResponse(BaseModel):
    message: str
    id: str
    deleted_files_count: int = 0


class ProjectSummaryResponse(BaseModel):
    id: str
    title: str
    original_language: str
    target_language: str
    translation_provider: str = "nllb"
    translation_style: str = "natural"
    tts_provider: str = "edge"
    tts_voice: str = "km-KH-PisethNeural"
    pipeline_version: str = "v2.3"
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectResponse(ProjectSummaryResponse):
    original_video_path: Optional[str] = None
    video: Optional[VideoResponse] = None
    jobs: List[ProcessingJobResponse] = []
    transcript_segments: List[TranscriptSegmentResponse] = []
    translation_segments: List[TranslationSegmentResponse] = []
    generated_audios: List[GeneratedAudioResponse] = []

    model_config = ConfigDict(from_attributes=True)


class SubtitleSegmentItem(BaseModel):
    id: str
    segment_order: int
    start_time: float
    end_time: float
    text: str
    source_text: Optional[str] = None
    source_segment_order: Optional[int] = None
    timing_confidence: Optional[str] = "verified"  # "verified", "estimated", "manual"
    is_source_outdated: bool = False
    is_customized: bool = False
    language: str = "km"
    readability: Optional[Dict[str, Any]] = None


class SubtitleListResponse(BaseModel):
    project_id: str
    language: str
    has_custom_edits: bool
    total_segments: int
    segments: List[SubtitleSegmentItem]


class SubtitleSegmentUpdate(BaseModel):
    text: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    language: Optional[str] = "km"


class SubtitleAutoSplitRequest(BaseModel):
    language: Optional[str] = "km"
    max_chars: Optional[int] = 75
    max_duration: Optional[float] = 6.5


class SubtitleManualSplitRequest(BaseModel):
    language: Optional[str] = "km"
    split_index: Optional[int] = None
    split_ratio: Optional[float] = 0.5


class SubtitleMergeRequest(BaseModel):
    language: Optional[str] = "km"


class SubtitleKeepEditsRequest(BaseModel):
    language: Optional[str] = "km"


class SubtitleResetResponse(BaseModel):
    message: str
    deleted_count: int
    language: str


class ProjectSpeakerResponse(BaseModel):
    id: str
    project_id: str
    speaker_label: str
    display_name: str
    detected_gender: str
    average_pitch_hz: Optional[float] = None
    color: str
    assigned_voice_provider: Optional[str] = None
    assigned_voice_id: Optional[str] = None
    segment_count: int = 0
    total_duration: float = 0.0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectSpeakerUpdate(BaseModel):
    display_name: Optional[str] = None
    assigned_voice_provider: Optional[str] = None
    assigned_voice_id: Optional[str] = None
    color: Optional[str] = None


class SegmentSpeakerUpdate(BaseModel):
    speaker_label: Optional[str] = None


class BulkSegmentSpeakerUpdate(BaseModel):
    segment_ids: List[str] = Field(min_length=1, max_length=1000)
    speaker_label: Optional[str] = None


class DiarizationRunRequest(BaseModel):
    min_speakers: Optional[int] = Field(default=1, ge=1, le=10)
    max_speakers: Optional[int] = Field(default=6, ge=1, le=10)


class DiarizationRunResponse(BaseModel):
    project_id: str
    speakers_detected: int
    speakers: List[ProjectSpeakerResponse]
    assigned_segments_count: int
    message: str


