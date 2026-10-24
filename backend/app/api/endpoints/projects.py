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
from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProcessingJob,
    ProjectStatus,
    JobStatus,
)
from app.schemas.project import (
    ProjectCreate,
    ProjectResponse,
    ProjectSummaryResponse,
    ProcessingJobResponse,
    TranscriptSegmentResponse,
    TranscriptSegmentUpdate,
    TranscriptResponse,
    TranslationSegmentResponse,
    TranslationSegmentUpdate,
    TranslationListResponse,
    GeneratedAudioResponse,
    GeneratedAudioListResponse,
)
from app.services.video.ffmpeg import FFmpegVideoProcessor
from app.services.video.exceptions import (
    CorruptedVideoError,
    InvalidVideoFormatError,
    VideoProcessingError,
)
from app.services.translation.nllb import NLLBTranslationProvider
from app.services.tts.google import GoogleTTSProvider
from app.workers.audio_extraction import process_audio_extraction
from app.workers.transcription import process_transcription
from app.workers.translation import process_translation
from app.workers.tts import process_tts, synthesize_segment_audio

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

    old_text = segment.text
    segment.text = clean_text

    # If transcript text changed, mark corresponding translation as outdated
    if old_text != clean_text:
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

    db.commit()
    db.refresh(segment)
    return segment


def _enrich_translation_segment(
    trans_seg: TranslationSegment,
) -> TranslationSegmentResponse:
    """Enrich TranslationSegment with timing and English transcript text."""
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

    provider = NLLBTranslationProvider()
    translated_texts = provider.translate(
        texts=[segment.transcript_segment.text],
        source_lang=project.original_language or "eng_Latn",
        target_lang=project.target_language or "khm_Khmr",
        contexts=[context_text],
    )

    if not translated_texts or not translated_texts[0]:
        raise HTTPException(
            status_code=500, detail="Failed to generate translation for this segment"
        )

    segment.khmer_text = translated_texts[0]
    segment.is_manually_edited = False
    segment.is_outdated = False
    if segment.generated_audio:
        segment.generated_audio.is_outdated = True
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
        provider = GoogleTTSProvider()
        audio_record = synthesize_segment_audio(project_id, segment, provider, db)
    except Exception as e:
        logger.error("Failed to regenerate audio segment %s: %s", segment_id, e)
        raise HTTPException(status_code=500, detail=f"Failed to generate speech: {e}")

    return _enrich_generated_audio(audio_record, project_id)


@router.get("/{project_id}/tts/{segment_id}/audio")
def stream_audio_segment(
    project_id: str,
    segment_id: str,
    db: Session = Depends(get_db),
):
    """Stream synthesized MP3 audio for browser playback."""
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

    file_path = Path(audio_record.audio_path)
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="Audio file not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type="audio/mpeg",
        filename=f"tts_{project_id}_{segment_id}.mp3",
    )

