from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
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
    exported_video_path: Optional[str] = None
    created_at: datetime

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


class ProjectCreate(BaseModel):
    title: str
    original_language: str = "en"
    target_language: str = "km"


class ProjectSummaryResponse(BaseModel):
    id: str
    title: str
    original_language: str
    target_language: str
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
