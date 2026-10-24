from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from app.models.project import ProjectStatus


class VideoResponse(BaseModel):
    id: str
    filename: str
    file_size_bytes: int
    duration_seconds: Optional[float] = None
    extracted_audio_path: Optional[str] = None
    exported_video_path: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TranscriptSegmentResponse(BaseModel):
    id: str
    segment_order: int
    start_time: float
    end_time: float
    text: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TranslationSegmentResponse(BaseModel):
    id: str
    transcript_segment_id: Optional[str] = None
    segment_order: int
    khmer_text: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
    transcript_segments: List[TranscriptSegmentResponse] = []
    translation_segments: List[TranslationSegmentResponse] = []

    model_config = ConfigDict(from_attributes=True)
