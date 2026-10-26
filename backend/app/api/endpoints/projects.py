import os
import re
import json
import math
import shutil
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from app.core.timezone import get_cambodia_now_naive

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    BackgroundTasks,
    Query,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import (
    resolve_audio_file,
    get_timeline_audio_path,
    get_exported_video_path,
    get_project_output_dir,
    delete_project_storage,
)
from app.database.session import get_db
from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    SubtitleSegment,
    ProcessingJob,
    ProjectStatus,
    JobStatus,
)
from app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectDeleteResponse,
    ProjectResponse,
    ProjectSummaryResponse,
    ProcessingJobResponse,
    TranscriptSegmentResponse,
    TranscriptSegmentUpdate,
    TranscriptResponse,
    SegmentationPreviewItem,
    SegmentationPreviewResponse,
    SegmentationApplyRequest,
    SegmentationApplyResponse,
    SegmentSplitRequest,
    SegmentSplitResponse,
    TranslationSegmentResponse,
    TranslationSegmentUpdate,
    TranslationListResponse,
    GeneratedAudioResponse,
    GeneratedAudioListResponse,
    TimingConflictResponse,
    ExportStatusResponse,
    ProjectVoiceUpdate,
    ProjectTranslationSettingsUpdate,
    AIImproveRequest,
    AIImproveResponse,
    AlternativeOption,
    AlternativesResponse,
    ApplyTranslationRequest,
)
from app.services.video.ffmpeg import FFmpegVideoProcessor
from app.services.video.exceptions import (
    CorruptedVideoError,
    InvalidVideoFormatError,
    VideoProcessingError,
)
from app.services.translation.nllb import NLLBTranslationProvider
from app.services.translation.registry import (
    get_translation_provider,
    validate_translation_provider,
    get_active_ai_provider_name,
)
from app.services.translation.exceptions import (
    TranslationError,
    ProviderAuthenticationError,
    RateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.services.tts.google import GoogleTTSProvider
from app.services.tts.registry import (
    get_tts_provider,
    is_valid_voice_combination,
    DEFAULT_PROVIDER,
    DEFAULT_VOICE,
)
from app.workers.audio_extraction import process_audio_extraction
from app.workers.transcription import process_transcription
from app.services.transcription.base import TranscriptionSegment, WordTiming
from app.services.transcription.segmentation import (
    segment_transcript,
    split_segment_at_word,
    merge_adjacent_segments,
)
from app.workers.translation import process_translation
from app.workers.tts import process_tts, synthesize_segment_audio
from app.workers.dubbing import process_dubbing
from app.services.dubbing import AutoFitService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and shell injection."""
    name = Path(filename).name
    # Strip any characters except alphanumeric, dashes, dots, and underscores
    sanitized = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return sanitized or "video.mp4"


@router.get("", response_model=List[ProjectSummaryResponse])
def list_projects(db: Session = Depends(get_db)) -> List[ProjectSummaryResponse]:
    """Retrieve all dubbing projects, excluding any currently undergoing deletion."""
    projects = (
        db.query(Project)
        .filter(Project.status != ProjectStatus.DELETING)
        .order_by(Project.created_at.desc())
        .all()
    )
    return projects


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectResponse:
    """Create a new dubbing project."""
    tts_provider = (payload.tts_provider or DEFAULT_PROVIDER).strip().lower()
    tts_voice = (payload.tts_voice or DEFAULT_VOICE).strip()
    if not is_valid_voice_combination(tts_provider, tts_voice, db=db):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid voice combination: provider='{tts_provider}', voice='{tts_voice}'",
        )

    trans_provider = (payload.translation_provider or "nllb").strip().lower()
    trans_style = (payload.translation_style or "natural").strip().lower()
    if not validate_translation_provider(trans_provider):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid translation provider: '{trans_provider}'",
        )

    project = Project(
        title=payload.title,
        original_language=payload.original_language,
        target_language=payload.target_language,
        translation_provider=trans_provider,
        translation_style=trans_style,
        tts_provider=tts_provider,
        tts_voice=tts_voice,
        status=ProjectStatus.CREATED,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.patch("/{project_id}/voice", response_model=ProjectResponse)
def update_project_voice(
    project_id: str,
    voice_update: ProjectVoiceUpdate,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Update selected TTS provider and voice for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    provider = (voice_update.tts_provider or DEFAULT_PROVIDER).strip().lower()
    voice = (voice_update.tts_voice or DEFAULT_VOICE).strip()

    if not is_valid_voice_combination(provider, voice, db=db):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid voice combination: provider='{provider}', voice='{voice}'",
        )

    if project.tts_provider != provider or project.tts_voice != voice:
        project.tts_provider = provider
        project.tts_voice = voice
        # Mark all existing generated audios as outdated
        db.query(GeneratedAudio).filter(GeneratedAudio.project_id == project_id).update(
            {GeneratedAudio.is_outdated: True}
        )
        if project.video and project.video.exported_video_path:
            project.video.is_export_outdated = True
        db.commit()
        db.refresh(project)

    return project


@router.patch("/{project_id}/translation-settings", response_model=ProjectResponse)
def update_project_translation_settings(
    project_id: str,
    payload: ProjectTranslationSettingsUpdate,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Update selected translation provider and style for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    provider_id = (payload.translation_provider or "nllb").strip().lower()
    style_id = (payload.translation_style or "natural").strip().lower()

    if not validate_translation_provider(provider_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid translation provider: '{provider_id}'. Valid options: nllb, gemini",
        )

    valid_styles = ["natural", "simple", "formal", "short", "standard"]
    if style_id not in valid_styles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid translation style: '{style_id}'. Valid options: {', '.join(valid_styles)}",
        )

    project.translation_provider = provider_id
    project.translation_style = style_id
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectResponse:
    """Retrieve details for a specific project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )
    return project


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Rename an existing project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot rename a project that is being deleted",
        )

    project.title = payload.title
    project.updated_at = get_cambodia_now_naive()
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", response_model=ProjectDeleteResponse)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
) -> ProjectDeleteResponse:
    """
    Safely delete a project and all associated files and database records.
    Precondition: Project must not have active background processing jobs.
    Two-stage deletion:
      Stage 1: Mark project status as 'deleting' to block new jobs and mutations.
      Stage 2: Safely remove files and cascade-delete database records.
    Idempotent and resilient: if deletion was interrupted, safely resumes Stage 2.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 1. Check for active background processing jobs
    active_job = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.project_id == project_id,
            ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
        .first()
    )
    active_project_statuses = [
        ProjectStatus.TRANSCRIBING,
        ProjectStatus.TRANSLATING,
        ProjectStatus.GENERATING_VOICE,
        ProjectStatus.SYNCHRONIZING,
    ]
    if active_job or project.status in active_project_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete project with active background processing jobs. Please wait for the job to complete or fail before deleting.",
        )

    title = project.title

    # 2. Stage 1: Mark project as deleting to prevent new incoming jobs and mutations
    if project.status != ProjectStatus.DELETING:
        project.status = ProjectStatus.DELETING
        db.commit()

    # 3. Stage 2: Clean up project files on disk
    deleted_files_count = 0
    try:
        storage_info = delete_project_storage(project_id)
        deleted_files_count = storage_info.get("deleted_count", 0)
    except Exception as e:
        logger.error(f"Error deleting storage for project {project_id}: {e}")

    # 4. Safe explicit database cleanup in foreign-key dependency order
    try:
        db.query(SubtitleSegment).filter(SubtitleSegment.project_id == project_id).delete(synchronize_session=False)
        db.query(GeneratedAudio).filter(GeneratedAudio.project_id == project_id).delete(synchronize_session=False)
        db.query(TranslationSegment).filter(TranslationSegment.project_id == project_id).delete(synchronize_session=False)
        db.query(TranscriptSegment).filter(TranscriptSegment.project_id == project_id).delete(synchronize_session=False)
        db.query(Video).filter(Video.project_id == project_id).delete(synchronize_session=False)
        db.query(ProcessingJob).filter(ProcessingJob.project_id == project_id).delete(synchronize_session=False)
        db.delete(project)
        db.commit()
    except Exception as db_err:
        db.rollback()
        logger.error(f"Failed to delete database records for project {project_id}: {db_err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error during project deletion: {str(db_err)}",
        )

    return ProjectDeleteResponse(
        message=f"Project '{title}' and all associated assets have been successfully deleted.",
        id=project_id,
        deleted_files_count=deleted_files_count,
    )


@router.post("/{project_id}/upload", response_model=ProjectResponse)
async def upload_video(
    project_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Upload an MP4 video file, validate with FFprobe, and trigger audio extraction."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    if not file.filename:
        raise HTTPException(status_code=400, detail="Empty filename provided")

    safe_name = sanitize_filename(file.filename)
    if not safe_name.lower().endswith((".mp4", ".mov")):
        raise HTTPException(status_code=400, detail="Only MP4 video files are accepted")

    project_dir = settings.UPLOADS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    dest_path = project_dir / safe_name

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    total_bytes = 0
    chunk_size = 1024 * 1024  # 1MB buffer

    try:
        with open(dest_path, "wb") as f:
            while chunk := await file.read(chunk_size):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    f.close()
                    dest_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                        if hasattr(status, "HTTP_413_CONTENT_TOO_LARGE")
                        else 413,
                        detail=f"Video file exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        dest_path.unlink(missing_ok=True)
        logger.error("Error streaming uploaded file: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to save uploaded file: {e}"
        ) from e
    finally:
        await file.close()

    if total_bytes == 0:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes)")

    # Validate actual media container with FFprobe
    processor = FFmpegVideoProcessor()
    try:
        metadata = processor.get_metadata(dest_path)
    except (CorruptedVideoError, InvalidVideoFormatError) as e:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except VideoProcessingError as e:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400, detail=f"Media validation error: {e}"
        ) from e
    except Exception as e:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500, detail=f"Unexpected error validating video: {e}"
        ) from e

    # Persist or update Video entity
    video = db.query(Video).filter(Video.project_id == project_id).first()
    if not video:
        video = Video(
            project_id=project_id,
            filename=safe_name,
            file_path=str(dest_path),
            file_size_bytes=total_bytes,
            duration_seconds=metadata.duration_seconds,
            width=metadata.width,
            height=metadata.height,
            video_codec=metadata.video_codec,
            audio_codec=metadata.audio_codec,
        )
        db.add(video)
    else:
        # If replacing an existing video, delete old file if distinct
        if video.file_path and video.file_path != str(dest_path):
            try:
                Path(video.file_path).unlink(missing_ok=True)
            except Exception:
                pass
        video.filename = safe_name
        video.file_path = str(dest_path)
        video.file_size_bytes = total_bytes
        video.duration_seconds = metadata.duration_seconds
        video.width = metadata.width
        video.height = metadata.height
        video.video_codec = metadata.video_codec
        video.audio_codec = metadata.audio_codec
        video.extracted_audio_path = None

    project.original_video_path = str(dest_path)
    project.status = ProjectStatus.UPLOADED

    # Create extraction processing job
    job = ProcessingJob(
        project_id=project_id,
        job_type="extract_audio",
        status=JobStatus.PENDING,
        progress_percentage=0,
    )
    db.add(job)
    db.commit()
    db.refresh(project)

    # Dispatch audio extraction in background
    background_tasks.add_task(process_audio_extraction, project_id, job.id)

    return project


@router.post("/{project_id}/extract-audio", response_model=ProcessingJobResponse)
def trigger_audio_extraction(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ProcessingJobResponse:
    """Manually trigger or retry audio extraction for an uploaded video."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    video = db.query(Video).filter(Video.project_id == project_id).first()
    if not video or not video.file_path or not Path(video.file_path).exists():
        raise HTTPException(
            status_code=400, detail="No uploaded video found for this project"
        )

    # Check for existing active audio extraction job
    active_job = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.project_id == project_id,
            ProcessingJob.job_type == "extract_audio",
            ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
        .first()
    )
    if active_job:
        return active_job

    job = ProcessingJob(
        project_id=project_id,
        job_type="extract_audio",
        status=JobStatus.PENDING,
        progress_percentage=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(process_audio_extraction, project_id, job.id)
    return job


@router.get("/{project_id}/jobs", response_model=List[ProcessingJobResponse])
def get_project_jobs(
    project_id: str, db: Session = Depends(get_db)
) -> List[ProcessingJobResponse]:
    """Retrieve all processing jobs for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    jobs = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.project_id == project_id)
        .order_by(ProcessingJob.created_at.desc())
        .all()
    )
    return jobs


@router.api_route("/{project_id}/video", methods=["GET", "HEAD"])
def get_project_video(project_id: str, db: Session = Depends(get_db)):
    """Stream or preview the uploaded video file."""
    video = db.query(Video).filter(Video.project_id == project_id).first()
    if not video or not video.file_path or not Path(video.file_path).exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    return FileResponse(
        video.file_path,
        media_type="video/mp4",
        filename=video.filename,
    )


@router.api_route("/{project_id}/audio", methods=["GET", "HEAD"])
def get_project_audio(project_id: str, db: Session = Depends(get_db)):
    """Stream or preview the extracted WAV audio file."""
    video = db.query(Video).filter(Video.project_id == project_id).first()
    if (
        not video
        or not video.extracted_audio_path
        or not Path(video.extracted_audio_path).exists()
    ):
        raise HTTPException(
            status_code=404, detail="Extracted audio file not found"
        )

    return FileResponse(
        video.extracted_audio_path,
        media_type="audio/wav",
        filename="extracted_audio.wav",
        content_disposition_type="inline",
    )


@router.post("/{project_id}/transcribe", response_model=ProcessingJobResponse)
def start_transcription(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ProcessingJobResponse:
    """Start asynchronous speech-to-text transcription using faster-whisper."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    video = db.query(Video).filter(Video.project_id == project_id).first()
    if (
        not video
        or not video.extracted_audio_path
        or not Path(video.extracted_audio_path).exists()
    ):
        raise HTTPException(
            status_code=400,
            detail="Extracted audio file not found. Please upload a video first.",
        )

    # Prevent duplicate concurrent transcription jobs
    active_job = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.project_id == project_id,
            ProcessingJob.job_type == "transcribe",
            ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
        .first()
    )
    if active_job:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A transcription job is already in progress for this project.",
        )

    job = ProcessingJob(
        project_id=project_id,
        job_type="transcribe",
        status=JobStatus.PENDING,
        progress_percentage=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(process_transcription, project_id, job.id)
    return job


@router.get("/{project_id}/transcript", response_model=TranscriptResponse)
def get_transcript(
    project_id: str, db: Session = Depends(get_db)
) -> TranscriptResponse:
    """Retrieve all transcribed segments for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segments = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.project_id == project_id)
        .order_by(TranscriptSegment.segment_order.asc())
        .all()
    )
    return TranscriptResponse(
        project_id=project_id,
        status=project.status,
        segmentation_mode=project.segmentation_mode or "sentence",
        segments=segments,
    )


@router.patch(
    "/{project_id}/transcript/{segment_id}",
    response_model=TranscriptSegmentResponse,
)
def update_transcript_segment(
    project_id: str,
    segment_id: str,
    payload: TranscriptSegmentUpdate,
    db: Session = Depends(get_db),
) -> TranscriptSegmentResponse:
    """Update transcription text for a single segment."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segment = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.id == segment_id,
            TranscriptSegment.project_id == project_id,
        )
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Transcript segment not found")

    clean_text = payload.text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Segment text cannot be empty")

    old_text = segment.text
    segment.text = clean_text

    # If transcript text changed, mark corresponding translation as outdated
    if old_text != clean_text:
        segment.is_manually_edited = True
        linked_trans = (
            db.query(TranslationSegment)
            .filter(
                TranslationSegment.project_id == project_id,
                TranslationSegment.transcript_segment_id == segment_id,
            )
            .first()
        )
        if linked_trans:
            linked_trans.is_outdated = True
            if linked_trans.generated_audio:
                linked_trans.generated_audio.is_outdated = True
        if project.video and project.video.exported_video_path:
            project.video.is_export_outdated = True

    db.commit()
    db.refresh(segment)
    return segment


def _load_raw_segments_for_project(project: Project, db: Session) -> List[TranscriptionSegment]:
    """Retrieve raw transcription segments with word timings for a project."""
    if project.raw_transcript_json:
        try:
            data = json.loads(project.raw_transcript_json)
            return [TranscriptionSegment.from_dict(d) for d in data]
        except Exception as e:
            logger.warning("Failed to deserialize project.raw_transcript_json: %s", e)

    # Check data/projects/{project_id}/asr_raw.json
    try:
        asr_dir = Path(settings.PROJECTS_DATA_DIR if hasattr(settings, "PROJECTS_DATA_DIR") else "/app/data/projects") / project.id
        asr_file = asr_dir / "asr_raw.json"
        if asr_file.exists():
            data = json.loads(asr_file.read_text(encoding="utf-8"))
            return [TranscriptionSegment.from_dict(d) for d in data]
    except Exception as e:
        logger.warning("Failed to read asr_raw.json: %s", e)

    # Fallback to current db TranscriptSegment rows
    db_segs = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.project_id == project.id)
        .order_by(TranscriptSegment.segment_order.asc())
        .all()
    )
    result = []
    for s in db_segs:
        words = None
        if s.words_json:
            try:
                w_list = json.loads(s.words_json)
                words = [WordTiming.from_dict(w) for w in w_list]
            except Exception:
                pass
        result.append(
            TranscriptionSegment(
                segment_order=s.segment_order,
                start_time=s.start_time,
                end_time=s.end_time,
                text=s.text,
                words=words,
                is_approximate=s.is_approximate,
                is_manually_edited=s.is_manually_edited,
            )
        )
    return result


@router.get(
    "/{project_id}/transcript/segmentation/preview",
    response_model=SegmentationPreviewResponse,
)
def preview_transcript_segmentation(
    project_id: str,
    mode: str = Query("sentence", description="Segmentation mode: original, sentence, or dubbing"),
    db: Session = Depends(get_db),
) -> SegmentationPreviewResponse:
    """Preview proposed transcript segments and assess downstream invalidation impact."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    raw_segs = _load_raw_segments_for_project(project, db)
    if not raw_segs:
        raise HTTPException(status_code=400, detail="No transcript available to segment")

    mode_clean = mode.lower().strip()
    if mode_clean not in ("original", "sentence", "dubbing"):
        raise HTTPException(status_code=400, detail=f"Unsupported segmentation mode: {mode}")

    proposed = segment_transcript(raw_segs, mode=mode_clean)
    curr_segs = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.project_id == project_id)
        .order_by(TranscriptSegment.segment_order.asc())
        .all()
    )
    has_user_edits = any(s.is_manually_edited for s in curr_segs)
    trans_count = db.query(TranslationSegment).filter(TranslationSegment.project_id == project_id).count()
    audio_count = db.query(GeneratedAudio).filter(GeneratedAudio.project_id == project_id).count()
    has_video_export = bool(project.video and project.video.exported_video_path)

    requires_confirmation = has_user_edits or trans_count > 0 or audio_count > 0
    impact_warning = None
    if requires_confirmation:
        parts = []
        if has_user_edits:
            parts.append("manual transcript edits")
        if trans_count > 0:
            parts.append(f"{trans_count} Khmer translation(s)")
        if audio_count > 0:
            parts.append(f"{audio_count} generated audio clip(s)")
        impact_warning = (
            f"Applying {mode_clean.title()} segmentation will change transcript segment boundaries and mark "
            + " and ".join(parts)
            + " as outdated. Re-translation will be required."
        )

    preview_items = [
        SegmentationPreviewItem(
            segment_order=s.segment_order,
            start_time=s.start_time,
            end_time=s.end_time,
            duration=round(s.end_time - s.start_time, 2),
            text=s.text,
            is_approximate=s.is_approximate,
        )
        for s in proposed
    ]

    return SegmentationPreviewResponse(
        project_id=project_id,
        current_mode=project.segmentation_mode or "sentence",
        requested_mode=mode_clean,
        current_segment_count=len(curr_segs),
        proposed_segment_count=len(proposed),
        proposed_segments=preview_items,
        has_user_edits=has_user_edits,
        has_translations=trans_count > 0,
        translation_count=trans_count,
        has_audio=audio_count > 0,
        audio_count=audio_count,
        has_exported_video=has_video_export,
        requires_confirmation=requires_confirmation,
        impact_warning=impact_warning,
    )


@router.post(
    "/{project_id}/transcript/segmentation/apply",
    response_model=SegmentationApplyResponse,
)
def apply_transcript_segmentation(
    project_id: str,
    payload: SegmentationApplyRequest,
    db: Session = Depends(get_db),
) -> SegmentationApplyResponse:
    """Apply the selected segmentation mode to the project transcript and invalidate downstream outputs."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project is deleting")

    raw_segs = _load_raw_segments_for_project(project, db)
    if not raw_segs:
        raise HTTPException(status_code=400, detail="No transcript available to segment")

    mode = payload.mode.lower().strip()
    if mode not in ("original", "sentence", "dubbing"):
        raise HTTPException(status_code=400, detail=f"Unsupported segmentation mode: {payload.mode}")

    curr_segs = db.query(TranscriptSegment).filter(TranscriptSegment.project_id == project_id).all()
    has_user_edits = any(s.is_manually_edited for s in curr_segs)
    trans_count = db.query(TranslationSegment).filter(TranslationSegment.project_id == project_id).count()
    audio_count = db.query(GeneratedAudio).filter(GeneratedAudio.project_id == project_id).count()

    needs_confirm = has_user_edits or trans_count > 0 or audio_count > 0
    if needs_confirm and not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required: applying new segmentation will invalidate existing translations or audio."
        )

    new_segs = segment_transcript(raw_segs, mode=mode)

    # Invalidate downstream outputs
    inv_trans = 0
    inv_aud = 0
    if trans_count > 0:
        db.query(TranslationSegment).filter(TranslationSegment.project_id == project_id).update(
            {TranslationSegment.is_outdated: True}
        )
        inv_trans = trans_count
    if audio_count > 0:
        db.query(GeneratedAudio).filter(GeneratedAudio.project_id == project_id).update(
            {GeneratedAudio.is_outdated: True}
        )
        inv_aud = audio_count
    if project.video and project.video.exported_video_path:
        project.video.is_export_outdated = True

    # Replace TranscriptSegment rows
    db.query(TranscriptSegment).filter(TranscriptSegment.project_id == project_id).delete()
    saved_segs: List[TranscriptSegment] = []
    for s in new_segs:
        words_data = json.dumps([w.to_dict() for w in s.words], ensure_ascii=False) if s.words else None
        db_seg = TranscriptSegment(
            project_id=project_id,
            segment_order=s.segment_order,
            start_time=s.start_time,
            end_time=s.end_time,
            text=s.text,
            words_json=words_data,
            is_approximate=s.is_approximate,
            is_manually_edited=False,
        )
        db.add(db_seg)
        saved_segs.append(db_seg)

    project.segmentation_mode = mode
    db.commit()
    for s in saved_segs:
        db.refresh(s)

    return SegmentationApplyResponse(
        project_id=project_id,
        segmentation_mode=mode,
        segment_count=len(saved_segs),
        message=f"Successfully applied {mode.title()} segmentation with {len(saved_segs)} segments",
        segments=saved_segs,
        invalidated_translations=inv_trans,
        invalidated_audios=inv_aud,
    )


@router.post(
    "/{project_id}/transcript/{segment_id}/split",
    response_model=SegmentSplitResponse,
)
def split_transcript_segment(
    project_id: str,
    segment_id: str,
    payload: SegmentSplitRequest,
    db: Session = Depends(get_db),
) -> SegmentSplitResponse:
    """Manually split a transcript segment at the specified word index."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    target_seg = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.id == segment_id, TranscriptSegment.project_id == project_id)
        .first()
    )
    if not target_seg:
        raise HTTPException(status_code=404, detail="Segment not found")

    words = None
    if target_seg.words_json:
        try:
            words = [WordTiming.from_dict(w) for w in json.loads(target_seg.words_json)]
        except Exception:
            pass

    t_seg = TranscriptionSegment(
        segment_order=target_seg.segment_order,
        start_time=target_seg.start_time,
        end_time=target_seg.end_time,
        text=target_seg.text,
        words=words,
        is_approximate=target_seg.is_approximate,
        is_manually_edited=target_seg.is_manually_edited,
    )

    try:
        s1, s2 = split_segment_at_word(t_seg, payload.word_index)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Shift following segment orders up by 1
    following = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order > target_seg.segment_order,
        )
        .all()
    )
    for f in following:
        f.segment_order += 1

    # Update target segment to s1
    target_seg.start_time = s1.start_time
    target_seg.end_time = s1.end_time
    target_seg.text = s1.text
    target_seg.words_json = json.dumps([w.to_dict() for w in s1.words], ensure_ascii=False) if s1.words else None
    target_seg.is_approximate = s1.is_approximate
    target_seg.is_manually_edited = True

    # Add s2 segment
    new_db_seg = TranscriptSegment(
        project_id=project_id,
        segment_order=s2.segment_order,
        start_time=s2.start_time,
        end_time=s2.end_time,
        text=s2.text,
        words_json=json.dumps([w.to_dict() for w in s2.words], ensure_ascii=False) if s2.words else None,
        is_approximate=s2.is_approximate,
        is_manually_edited=True,
    )
    db.add(new_db_seg)

    # Invalidate linked translation
    linked_trans = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.project_id == project_id,
            TranslationSegment.transcript_segment_id == segment_id,
        )
        .first()
    )
    if linked_trans:
        linked_trans.is_outdated = True
        if linked_trans.generated_audio:
            linked_trans.generated_audio.is_outdated = True
    if project.video and project.video.exported_video_path:
        project.video.is_export_outdated = True

    db.commit()

    all_segs = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.project_id == project_id)
        .order_by(TranscriptSegment.segment_order.asc())
        .all()
    )
    return SegmentSplitResponse(
        message="Segment successfully split into two",
        segments=all_segs,
    )


@router.post(
    "/{project_id}/transcript/{segment_id}/merge-next",
    response_model=SegmentSplitResponse,
)
def merge_transcript_segment_next(
    project_id: str,
    segment_id: str,
    db: Session = Depends(get_db),
) -> SegmentSplitResponse:
    """Manually merge a transcript segment with its next neighbor."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    target_seg = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.id == segment_id, TranscriptSegment.project_id == project_id)
        .first()
    )
    if not target_seg:
        raise HTTPException(status_code=404, detail="Segment not found")

    next_seg = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order == target_seg.segment_order + 1,
        )
        .first()
    )
    if not next_seg:
        raise HTTPException(status_code=400, detail="No adjacent next segment found to merge with")

    words1 = [WordTiming.from_dict(w) for w in json.loads(target_seg.words_json)] if target_seg.words_json else None
    words2 = [WordTiming.from_dict(w) for w in json.loads(next_seg.words_json)] if next_seg.words_json else None

    t1 = TranscriptionSegment(target_seg.segment_order, target_seg.start_time, target_seg.end_time, target_seg.text, words=words1)
    t2 = TranscriptionSegment(next_seg.segment_order, next_seg.start_time, next_seg.end_time, next_seg.text, words=words2)

    merged = merge_adjacent_segments(t1, t2)

    target_seg.start_time = merged.start_time
    target_seg.end_time = merged.end_time
    target_seg.text = merged.text
    target_seg.words_json = json.dumps([w.to_dict() for w in merged.words], ensure_ascii=False) if merged.words else None
    target_seg.is_manually_edited = True

    # Delete next_seg
    db.delete(next_seg)

    # Shift following segment orders down by 1
    following = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order > next_seg.segment_order,
        )
        .all()
    )
    for f in following:
        f.segment_order -= 1

    # Invalidate linked translation
    linked_trans = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.project_id == project_id,
            TranslationSegment.transcript_segment_id == segment_id,
        )
        .first()
    )
    if linked_trans:
        linked_trans.is_outdated = True
        if linked_trans.generated_audio:
            linked_trans.generated_audio.is_outdated = True
    if project.video and project.video.exported_video_path:
        project.video.is_export_outdated = True

    db.commit()

    all_segs = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.project_id == project_id)
        .order_by(TranscriptSegment.segment_order.asc())
        .all()
    )
    return SegmentSplitResponse(
        message="Segments successfully merged",
        segments=all_segs,
    )


def _enrich_translation_segment(
    trans_seg: TranslationSegment,
) -> TranslationSegmentResponse:
    """Enrich TranslationSegment with timing, style, explanation, and English transcript text."""
    english_text = trans_seg.transcript_segment.text if trans_seg.transcript_segment else None
    start_time = trans_seg.transcript_segment.start_time if trans_seg.transcript_segment else None
    end_time = trans_seg.transcript_segment.end_time if trans_seg.transcript_segment else None

    return TranslationSegmentResponse(
        id=trans_seg.id,
        project_id=trans_seg.project_id,
        transcript_segment_id=trans_seg.transcript_segment_id,
        segment_order=trans_seg.segment_order,
        khmer_text=trans_seg.khmer_text,
        english_text=english_text,
        start_time=start_time,
        end_time=end_time,
        style=getattr(trans_seg, "style", "natural") or "natural",
        explanation=getattr(trans_seg, "explanation", None),
        is_manually_edited=trans_seg.is_manually_edited,
        is_outdated=trans_seg.is_outdated,
        created_at=trans_seg.created_at,
        updated_at=trans_seg.updated_at,
    )


@router.post("/{project_id}/translate", response_model=ProcessingJobResponse)
def start_translation(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ProcessingJobResponse:
    """Start asynchronous English-to-Khmer translation using NLLB-200."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    # Verify transcript segments exist
    transcript_count = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.project_id == project_id)
        .count()
    )
    if transcript_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No transcript segments found. Please transcribe audio before translating.",
        )

    # Prevent duplicate concurrent translation jobs
    active_job = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.project_id == project_id,
            ProcessingJob.job_type == "translate",
            ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
        .first()
    )
    if active_job:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A translation job is already in progress for this project.",
        )

    job = ProcessingJob(
        project_id=project_id,
        job_type="translate",
        status=JobStatus.PENDING,
        progress_percentage=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(process_translation, project_id, job.id)
    return job


@router.get("/{project_id}/translations", response_model=TranslationListResponse)
def get_translations(
    project_id: str, db: Session = Depends(get_db)
) -> TranslationListResponse:
    """Retrieve all translated segments for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segments = (
        db.query(TranslationSegment)
        .filter(TranslationSegment.project_id == project_id)
        .order_by(TranslationSegment.segment_order.asc())
        .all()
    )

    enriched = [_enrich_translation_segment(seg) for seg in segments]

    return TranslationListResponse(
        project_id=project_id,
        status=project.status,
        segments=enriched,
    )


@router.patch(
    "/{project_id}/translations/{segment_id}",
    response_model=TranslationSegmentResponse,
)
def update_translation_segment(
    project_id: str,
    segment_id: str,
    payload: TranslationSegmentUpdate,
    db: Session = Depends(get_db),
) -> TranslationSegmentResponse:
    """Manually update Khmer translation text for a single segment."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segment = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.id == segment_id,
            TranslationSegment.project_id == project_id,
        )
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Translation segment not found")

    clean_text = payload.khmer_text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Translation text cannot be empty")

    if clean_text != segment.khmer_text:
        segment.khmer_text = clean_text
        segment.is_manually_edited = True
        segment.is_outdated = False
        if segment.generated_audio:
            segment.generated_audio.is_outdated = True
        if project.video and project.video.exported_video_path:
            project.video.is_export_outdated = True
        db.commit()
        db.refresh(segment)

    return _enrich_translation_segment(segment)


@router.post(
    "/{project_id}/translations/{segment_id}/retranslate",
    response_model=TranslationSegmentResponse,
)
def retranslate_segment(
    project_id: str,
    segment_id: str,
    db: Session = Depends(get_db),
) -> TranslationSegmentResponse:
    """Retranslate a single segment from its corresponding English transcript."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segment = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.id == segment_id,
            TranslationSegment.project_id == project_id,
        )
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Translation segment not found")

    if not segment.transcript_segment or not segment.transcript_segment.text:
        raise HTTPException(
            status_code=400,
            detail="Corresponding English transcript text is missing",
        )

    # Build lightweight context from surrounding transcript segments
    prev_seg = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order == segment.segment_order - 1,
        )
        .first()
    )
    next_seg = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order == segment.segment_order + 1,
        )
        .first()
    )
    context_text = f"{prev_seg.text + ' ' if prev_seg else ''}{segment.transcript_segment.text}{' ' + next_seg.text if next_seg else ''}".strip()

    provider_id = (project.translation_provider or "nllb").lower()
    style = project.translation_style or "natural"
    try:
        if provider_id == "nllb":
            provider = NLLBTranslationProvider()
        else:
            provider = get_translation_provider(provider_id)
        translated_texts = provider.translate(
            texts=[segment.transcript_segment.text],
            source_lang=project.original_language or "eng_Latn",
            target_lang=project.target_language or "khm_Khmr",
            contexts=[context_text],
            style=style,
        )
    except ProviderAuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to retranslate segment %s: %s", segment_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to translate segment: {str(exc)}")

    if not translated_texts or not translated_texts[0]:
        raise HTTPException(
            status_code=500, detail="Failed to generate translation for this segment"
        )

    segment.khmer_text = translated_texts[0]
    segment.style = style
    segment.explanation = None
    segment.is_manually_edited = False
    segment.is_outdated = False
    if segment.generated_audio:
        segment.generated_audio.is_outdated = True
    if project.video and project.video.exported_video_path:
        project.video.is_export_outdated = True
    db.commit()
    db.refresh(segment)

    return _enrich_translation_segment(segment)


@router.post(
    "/{project_id}/translations/{segment_id}/ai-improve",
    response_model=AIImproveResponse,
)
def ai_improve_segment(
    project_id: str,
    segment_id: str,
    payload: AIImproveRequest,
    db: Session = Depends(get_db),
) -> AIImproveResponse:
    """Use AI LLM (Gemini) to improve, naturalize, or shorten a translation segment."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segment = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.id == segment_id,
            TranslationSegment.project_id == project_id,
        )
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Translation segment not found")

    if not segment.transcript_segment or not segment.transcript_segment.text:
        raise HTTPException(
            status_code=400,
            detail="Corresponding English transcript text is missing",
        )

    # Calculate target duration if not provided
    target_duration = payload.target_duration
    if target_duration is None and segment.transcript_segment:
        target_duration = segment.transcript_segment.end_time - segment.transcript_segment.start_time

    # Build surrounding context
    prev_seg = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order == segment.segment_order - 1,
        )
        .first()
    )
    next_seg = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order == segment.segment_order + 1,
        )
        .first()
    )
    context_parts = []
    if prev_seg:
        context_parts.append(f"Previous English: {prev_seg.text}")
    context_parts.append(f"Current English: {segment.transcript_segment.text}")
    if next_seg:
        context_parts.append(f"Next English: {next_seg.text}")
    context_str = " | ".join(context_parts)

    provider_id = (
        project.translation_provider
        if project.translation_provider and project.translation_provider != "nllb"
        else get_active_ai_provider_name()
    )
    try:
        provider = get_translation_provider(provider_id)
        result = provider.improve_translation(
            english_text=segment.transcript_segment.text,
            current_khmer_text=segment.khmer_text,
            context=context_str,
            target_duration=target_duration,
            style=payload.style or project.translation_style or "natural",
            custom_prompt=payload.custom_prompt,
        )
    except ProviderAuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to AI improve segment %s: %s", segment_id, exc)
        raise HTTPException(status_code=500, detail=f"AI improve failed: {str(exc)}")

    return AIImproveResponse(
        segment_id=segment.id,
        original_text=segment.transcript_segment.text,
        current_khmer_text=segment.khmer_text,
        improved_khmer_text=result.improved_khmer_text,
        explanation=result.explanation,
        style=result.style,
        provider=getattr(provider, "name", "gemini"),
        model=getattr(provider, "model", "gemini-3.5-flash"),
    )


@router.post(
    "/{project_id}/translations/{segment_id}/alternatives",
    response_model=AlternativesResponse,
)
def get_translation_alternatives(
    project_id: str,
    segment_id: str,
    db: Session = Depends(get_db),
) -> AlternativesResponse:
    """Generate 3 structured translation alternatives (Natural, Simple, Short) using AI LLM."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segment = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.id == segment_id,
            TranslationSegment.project_id == project_id,
        )
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Translation segment not found")

    if not segment.transcript_segment or not segment.transcript_segment.text:
        raise HTTPException(
            status_code=400,
            detail="Corresponding English transcript text is missing",
        )

    target_duration = (
        segment.transcript_segment.end_time - segment.transcript_segment.start_time
        if segment.transcript_segment
        else None
    )

    prev_seg = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order == segment.segment_order - 1,
        )
        .first()
    )
    next_seg = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.project_id == project_id,
            TranscriptSegment.segment_order == segment.segment_order + 1,
        )
        .first()
    )
    context_parts = []
    if prev_seg:
        context_parts.append(f"Previous: {prev_seg.text}")
    context_parts.append(f"Current: {segment.transcript_segment.text}")
    if next_seg:
        context_parts.append(f"Next: {next_seg.text}")
    context_str = " | ".join(context_parts)

    provider_id = (
        project.translation_provider
        if project.translation_provider and project.translation_provider != "nllb"
        else get_active_ai_provider_name()
    )
    try:
        provider = get_translation_provider(provider_id)
        alts = provider.generate_alternatives(
            english_text=segment.transcript_segment.text,
            current_khmer_text=segment.khmer_text,
            context=context_str,
            target_duration=target_duration,
        )
    except ProviderAuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to generate alternatives for segment %s: %s", segment_id, exc)
        raise HTTPException(status_code=500, detail=f"Alternatives generation failed: {str(exc)}")

    return AlternativesResponse(
        segment_id=segment.id,
        english_text=segment.transcript_segment.text,
        current_khmer_text=segment.khmer_text,
        alternatives=[
            AlternativeOption(
                style=alt.style,
                label=alt.label,
                khmer_text=alt.khmer_text,
                explanation=alt.explanation,
            )
            for alt in alts
        ],
    )


@router.post(
    "/{project_id}/translations/{segment_id}/apply",
    response_model=TranslationSegmentResponse,
)
def apply_translation_suggestion(
    project_id: str,
    segment_id: str,
    payload: ApplyTranslationRequest,
    db: Session = Depends(get_db),
) -> TranslationSegmentResponse:
    """Apply an AI suggestion or alternative to a translation segment."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segment = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.id == segment_id,
            TranslationSegment.project_id == project_id,
        )
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Translation segment not found")

    clean_text = payload.khmer_text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Translation text cannot be empty")

    segment.khmer_text = clean_text
    if payload.style:
        segment.style = payload.style
    if payload.explanation is not None:
        segment.explanation = payload.explanation
    segment.is_manually_edited = True
    segment.is_outdated = False

    # Mark generated audio as outdated so user regenerates speech
    if segment.generated_audio:
        segment.generated_audio.is_outdated = True
    if project.video and project.video.exported_video_path:
        project.video.is_export_outdated = True

    db.commit()
    db.refresh(segment)

    return _enrich_translation_segment(segment)


def _enrich_generated_audio(
    audio: GeneratedAudio, project_id: str
) -> GeneratedAudioResponse:
    """Enrich GeneratedAudio with segment order, khmer text, and streaming URL."""
    segment_order = (
        audio.translation_segment.segment_order if audio.translation_segment else None
    )
    khmer_text = (
        audio.translation_segment.khmer_text if audio.translation_segment else None
    )
    audio_url = (
        f"/api/projects/{project_id}/tts/{audio.translation_segment_id}/audio"
        if audio.translation_segment_id
        else None
    )
    return GeneratedAudioResponse(
        id=audio.id,
        project_id=audio.project_id,
        translation_segment_id=audio.translation_segment_id,
        segment_order=segment_order,
        khmer_text=khmer_text,
        audio_path=audio.audio_path,
        duration_seconds=audio.duration_seconds,
        provider=audio.provider,
        voice=audio.voice,
        is_outdated=audio.is_outdated,
        created_at=audio.created_at,
        updated_at=audio.updated_at,
        audio_url=audio_url,
    )


@router.post("/{project_id}/tts", response_model=ProcessingJobResponse)
def start_tts(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ProcessingJobResponse:
    """Trigger background text-to-speech generation for all translated Khmer segments."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    translation_count = (
        db.query(TranslationSegment)
        .filter(TranslationSegment.project_id == project_id)
        .count()
    )
    if translation_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No Khmer translation segments found. Please translate transcript first.",
        )

    # Check for existing pending/running job
    active_job = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.project_id == project_id,
            ProcessingJob.job_type == "tts",
            ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
        .first()
    )
    if active_job:
        return active_job

    job = ProcessingJob(
        project_id=project_id,
        job_type="tts",
        status=JobStatus.PENDING,
        progress_percentage=0,
    )
    db.add(job)
    project.status = ProjectStatus.GENERATING_VOICE
    db.commit()
    db.refresh(job)

    background_tasks.add_task(process_tts, project_id, job.id)
    return job


@router.get("/{project_id}/generated-audio", response_model=GeneratedAudioListResponse)
def get_generated_audio(
    project_id: str,
    db: Session = Depends(get_db),
) -> GeneratedAudioListResponse:
    """Retrieve all generated audio records for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    audios = (
        db.query(GeneratedAudio)
        .join(TranslationSegment, GeneratedAudio.translation_segment_id == TranslationSegment.id)
        .filter(GeneratedAudio.project_id == project_id)
        .order_by(TranslationSegment.segment_order.asc())
        .all()
    )

    enriched = [_enrich_generated_audio(a, project_id) for a in audios]
    total_duration = sum(a.duration_seconds or 0.0 for a in enriched)

    return GeneratedAudioListResponse(
        project_id=project_id,
        status=project.status,
        audios=enriched,
        total_duration_seconds=round(total_duration, 2),
    )


@router.post(
    "/{project_id}/tts/{segment_id}/regenerate",
    response_model=GeneratedAudioResponse,
)
def regenerate_audio_segment(
    project_id: str,
    segment_id: str,
    db: Session = Depends(get_db),
) -> GeneratedAudioResponse:
    """Regenerate Khmer speech audio for a specific segment."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    segment = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.id == segment_id,
            TranslationSegment.project_id == project_id,
        )
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Translation segment not found")

    if not segment.khmer_text or not segment.khmer_text.strip():
        raise HTTPException(status_code=400, detail="Cannot synthesize empty Khmer text")

    try:
        provider_name = project.tts_provider or DEFAULT_PROVIDER
        voice_name = project.tts_voice or DEFAULT_VOICE
        provider = get_tts_provider(provider_name)
        audio_record = synthesize_segment_audio(
            project_id=project_id,
            segment=segment,
            provider=provider,
            db=db,
            voice=voice_name,
        )
        if project.video and project.video.exported_video_path:
            project.video.is_export_outdated = True
            db.commit()
    except Exception as e:
        logger.error("Failed to regenerate audio segment %s: %s", segment_id, e)
        raise HTTPException(status_code=500, detail=f"Failed to generate speech: {e}")

    return _enrich_generated_audio(audio_record, project_id)


@router.api_route("/{project_id}/tts/{segment_id}/audio", methods=["GET", "HEAD"])
def stream_audio_segment(
    project_id: str,
    segment_id: str,
    db: Session = Depends(get_db),
):
    """Stream synthesized MP3 audio for browser playback with Range request support."""
    audio_record = (
        db.query(GeneratedAudio)
        .filter(
            GeneratedAudio.project_id == project_id,
            GeneratedAudio.translation_segment_id == segment_id,
        )
        .first()
    )
    if not audio_record:
        raise HTTPException(status_code=404, detail="Generated audio record not found")

    file_path = resolve_audio_file(project_id, segment_id, audio_record.audio_path)
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="Audio file not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type="audio/mpeg",
        filename=f"tts_{project_id}_{segment_id}.mp3",
        content_disposition_type="inline",
    )


@router.post("/{project_id}/export", response_model=ProcessingJobResponse)
def start_dubbing_export(
    project_id: str,
    background_tasks: BackgroundTasks,
    max_tempo: float = Query(1.25, ge=1.0, le=2.0),
    trim_silence: bool = Query(True),
    db: Session = Depends(get_db),
) -> ProcessingJobResponse:
    """Trigger background audio synchronization and dubbed video export."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    video = project.video
    if not video or not video.file_path or not Path(video.file_path).exists():
        raise HTTPException(
            status_code=400,
            detail="Original video file is missing or not uploaded.",
        )

    translation_segments = (
        db.query(TranslationSegment)
        .filter(TranslationSegment.project_id == project_id)
        .order_by(TranslationSegment.segment_order.asc())
        .all()
    )
    if not translation_segments:
        raise HTTPException(
            status_code=400,
            detail="No Khmer translation segments found. Please translate transcript first.",
        )

    # Validate that every segment has generated audio and none is outdated
    for trans_seg in translation_segments:
        audio = trans_seg.generated_audio
        if not audio:
            audio = (
                db.query(GeneratedAudio)
                .filter(GeneratedAudio.translation_segment_id == trans_seg.id)
                .first()
            )
        if not audio:
            raise HTTPException(
                status_code=400,
                detail=f"Missing generated audio for segment #{trans_seg.segment_order}. Please generate audio first.",
            )
        if audio.is_outdated:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Generated audio for segment #{trans_seg.segment_order} is outdated "
                    f"because translation text was modified. Please regenerate audio before export."
                ),
            )

    # Check for active running export job
    active_job = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.project_id == project_id,
            ProcessingJob.job_type == "dub",
            ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
        .first()
    )
    if active_job:
        return active_job

    job = ProcessingJob(
        project_id=project_id,
        job_type="dub",
        status=JobStatus.PENDING,
        progress_percentage=0,
    )
    db.add(job)
    project.status = ProjectStatus.SYNCHRONIZING
    db.commit()
    db.refresh(job)

    background_tasks.add_task(
        process_dubbing,
        project_id,
        job.id,
        max_tempo_factor=max_tempo,
        trim_silence=trim_silence,
    )
    return job


@router.get("/{project_id}/export/status", response_model=ExportStatusResponse)
def get_export_status(
    project_id: str,
    max_tempo: float = Query(1.25, ge=1.0, le=2.0),
    db: Session = Depends(get_db),
) -> ExportStatusResponse:
    """Check export readiness, current job status, timing conflicts, and media details."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    video = project.video
    dub_job = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.project_id == project_id, ProcessingJob.job_type == "dub")
        .order_by(ProcessingJob.created_at.desc())
        .first()
    )

    is_ready = bool(
        video and video.exported_video_path and Path(video.exported_video_path).exists()
    )
    is_outdated = bool(video and video.is_export_outdated)

    video_url = f"/api/projects/{project_id}/export/video" if is_ready else None
    download_url = f"/api/projects/{project_id}/export/download" if is_ready else None

    # Calculate any timing conflicts from current segments
    timing_conflicts: List[TimingConflictResponse] = []
    if project.translation_segments:
        target_dur = float(video.duration_seconds or 0.0) if video else 0.0
        sorted_trans = sorted(project.translation_segments, key=lambda s: s.segment_order)
        for idx, trans_seg in enumerate(sorted_trans):
            t_seg = trans_seg.transcript_segment
            audio_rec = trans_seg.generated_audio
            if t_seg and audio_rec and audio_rec.duration_seconds:
                start_time = max(0.0, float(t_seg.start_time))
                end_time = max(start_time, float(t_seg.end_time))
                orig_dur = max(0.1, end_time - start_time)

                if idx < len(sorted_trans) - 1:
                    next_t = sorted_trans[idx + 1].transcript_segment
                    next_start = float(next_t.start_time) if next_t else end_time
                    if next_start > start_time:
                        avail_window = min(next_start - start_time, target_dur - start_time) if target_dur > 0 else (next_start - start_time)
                    else:
                        avail_window = orig_dur
                else:
                    avail_window = (target_dur - start_time) if target_dur > 0 else orig_dur

                avail_window = max(0.1, avail_window)
                raw_dur = float(audio_rec.duration_seconds)

                if raw_dur > avail_window:
                    safety_margin = 0.05
                    effective_window = max(0.05, round(avail_window - safety_margin, 3))
                    required_tempo = round(raw_dur / effective_window, 2)
                    if required_tempo > max_tempo:
                        adjusted_est = raw_dur / max_tempo
                        overflow = round(adjusted_est - effective_window, 2)
                        if overflow > 0.05:
                            est_words = max(1, math.ceil(overflow / 0.35))
                            action = (
                                f"Shorten the Khmer translation for Segment #{t_seg.segment_order} by approximately "
                                f"{est_words} word(s) (~{overflow:.1f}s excess), regenerate audio, and retry export."
                            )
                            timing_conflicts.append(
                                TimingConflictResponse(
                                    segment_order=t_seg.segment_order,
                                    transcript_segment_id=t_seg.id,
                                    start_time=round(start_time, 2),
                                    end_time=round(end_time, 2),
                                    original_duration=round(orig_dur, 2),
                                    khmer_duration=round(raw_dur, 2),
                                    available_window=round(avail_window, 2),
                                    effective_window=round(effective_window, 2),
                                    safety_margin_seconds=safety_margin,
                                    required_tempo=required_tempo,
                                    max_tempo_factor=max_tempo,
                                    tempo_factor=max_tempo,
                                    overflow_seconds=overflow,
                                    suggested_action=action,
                                    message=(
                                        f"Segment #{t_seg.segment_order} ({raw_dur:.1f}s) exceeds available window "
                                        f"({avail_window:.2f}s raw, {effective_window:.2f}s effective with {int(safety_margin * 1000)}ms safety margin) "
                                        f"by {overflow:.1f}s even at {max_tempo}x speed. "
                                        f"{action}"
                                    ),
                                )
                            )

    job_resp = ProcessingJobResponse.model_validate(dub_job) if dub_job else None

    return ExportStatusResponse(
        project_id=project_id,
        status=project.status,
        job=job_resp,
        is_export_ready=is_ready,
        is_export_outdated=is_outdated,
        exported_video_path=video.exported_video_path if video else None,
        audio_timeline_path=video.audio_timeline_path if video else None,
        exported_duration_seconds=video.exported_duration_seconds if video else None,
        exported_file_size_bytes=video.exported_file_size_bytes if video else None,
        timing_conflicts=timing_conflicts,
        video_url=video_url,
        download_url=download_url,
    )


@router.post("/{project_id}/dubbing/auto-fit", response_model=ExportStatusResponse)
def auto_fit_project_timing(
    project_id: str,
    max_tempo: float = Query(1.25, ge=1.0, le=2.0),
    db: Session = Depends(get_db),
) -> ExportStatusResponse:
    """Automatically shorten Khmer translations and re-synthesize speech to fit within video timestamps."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    auto_fit_service = AutoFitService()
    auto_fit_service.auto_fit_project(project_id, db, max_tempo=max_tempo)

    return get_export_status(project_id=project_id, max_tempo=max_tempo, db=db)


@router.api_route("/{project_id}/export/video", methods=["GET", "HEAD"])
def stream_exported_video(
    project_id: str,
    db: Session = Depends(get_db),
):
    """Stream or preview the exported Khmer-dubbed MP4 video file with HTTP byte ranges."""
    video = db.query(Video).filter(Video.project_id == project_id).first()
    if not video or not video.exported_video_path or not Path(video.exported_video_path).exists():
        raise HTTPException(status_code=404, detail="Exported dubbed video not found")

    return FileResponse(
        video.exported_video_path,
        media_type="video/mp4",
        filename=f"dubbed_{project_id}.mp4",
    )


@router.get("/{project_id}/export/download")
def download_exported_video(
    project_id: str,
    db: Session = Depends(get_db),
):
    """Download the exported Khmer-dubbed MP4 video file as an attachment."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == ProjectStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already in the process of being deleted",
        )

    video = project.video
    if not video or not video.exported_video_path or not Path(video.exported_video_path).exists():
        raise HTTPException(status_code=404, detail="Exported dubbed video not found")

    safe_title = sanitize_filename(project.title).replace(".mp4", "")
    download_filename = f"dubbed_{safe_title}.mp4"

    return FileResponse(
        path=video.exported_video_path,
        media_type="video/mp4",
        filename=download_filename,
        headers={"Content-Disposition": f'attachment; filename="{download_filename}"'},
    )


