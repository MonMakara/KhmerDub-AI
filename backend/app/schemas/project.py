from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, field_validator
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
    id: str
    segment_order: int
    start_time: float
    end_time: float
    text: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TranscriptSegmentUpdate(BaseModel):
    text: str


class TranscriptResponse(BaseModel):
    project_id: str
    status: ProjectStatus
    segments: List[TranscriptSegmentResponse]


class TranslationSegmentResponse(BaseModel):
    id: str
    project_id: str
    transcript_segment_id: Optional[str] = None
    segment_order: int
    khmer_text: str
    english_text: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    style: Optional[str] = "natural"
    explanation: Optional[str] = None
    is_manually_edited: bool = False
    is_outdated: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TranslationSegmentUpdate(BaseModel):
    khmer_text: str


class TranslationListResponse(BaseModel):
    project_id: str
    status: ProjectStatus
    segments: List[TranslationSegmentResponse]


class GeneratedAudioResponse(BaseModel):
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
    video_url: Optional[str] = None
    download_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class VoiceOptionResponse(BaseModel):
    provider: str
    voice: str
    label: str
    gender: str
    description: str
    sample_rate: Optional[int] = 24000
    is_custom: Optional[bool] = False
    profile_id: Optional[str] = None
    is_available: Optional[bool] = True


class VoiceListResponse(BaseModel):
    voices: List[VoiceOptionResponse]
    default_provider: str
    default_voice: str


class VoicePreviewRequest(BaseModel):
    provider: str = "gtts"
    voice: str = "default"
    text: Optional[str] = None


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
    tts_provider: Optional[str] = "gtts"
    tts_voice: Optional[str] = "default"


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
    tts_provider: str = "gtts"
    tts_voice: str = "default"
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

