import os
import re
import shutil
import logging
from pathlib import Path
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    BackgroundTasks,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db
from app.models.project import Project, Video, TranscriptSegment, ProcessingJob, ProjectStatus, JobStatus
from app.schemas.project import (
    ProjectCreate,
    ProjectResponse,
    ProjectSummaryResponse,
    ProcessingJobResponse,
    TranscriptSegmentResponse,
    TranscriptSegmentUpdate,
    TranscriptResponse,
)
from app.services.video.ffmpeg import FFmpegVideoProcessor
from app.services.video.exceptions import (
    CorruptedVideoError,
    InvalidVideoFormatError,
    VideoProcessingError,
)
from app.workers.audio_extraction import process_audio_extraction
from app.workers.transcription import process_transcription

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
    """Retrieve all dubbing projects."""
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return projects


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectResponse:
    """Create a new dubbing project."""
    project = Project(
        title=payload.title,
        original_language=payload.original_language,
        target_language=payload.target_language,
        status=ProjectStatus.CREATED,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectResponse:
    """Retrieve details for a specific project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


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

    video = db.query(Video).filter(Video.project_id == project_id).first()
    if not video or not video.file_path or not Path(video.file_path).exists():
        raise HTTPException(
            status_code=400, detail="No uploaded video found for this project"
        )

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

    segments = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.project_id == project_id)
        .order_by(TranscriptSegment.segment_order.asc())
        .all()
    )
    return TranscriptResponse(
        project_id=project_id,
        status=project.status,
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

    segment.text = clean_text
    db.commit()
    db.refresh(segment)
    return segment
