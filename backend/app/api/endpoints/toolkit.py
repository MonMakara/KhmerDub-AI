import json
import logging
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import (
    delete_toolkit_task_storage,
    get_toolkit_task_dir,
    get_toolkit_task_input_dir,
    get_toolkit_task_output_dir,
    sanitize_toolkit_task_id,
)
from app.database.session import get_db
from app.models.project import Project
from app.models.toolkit import ToolkitTask
from app.services.video.exceptions import (
    CorruptedVideoError,
    InvalidVideoFormatError,
    NoAudioTrackError,
    VideoProcessingError,
)
from app.services.video.ffmpeg import FFmpegVideoProcessor

logger = logging.getLogger(__name__)

router = APIRouter()
video_processor = FFmpegVideoProcessor()

# MIME types for supported extracted formats
AUDIO_MIME_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
}


class ToolkitTaskResponse(BaseModel):
    id: str
    tool_type: str
    source_type: str
    source_project_id: Optional[str] = None
    source_filename: str
    target_format: str
    status: str
    progress_percentage: int
    output_filename: Optional[str] = None
    output_duration_seconds: Optional[float] = None
    output_file_size_bytes: Optional[int] = None
    source_media_metadata: Optional[Dict[str, Any]] = None
    output_media_metadata: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


def _serialize_task(task: ToolkitTask) -> Dict[str, Any]:
    """Helper to convert task SQLAlchemy model to dict with parsed JSON metadata."""
    src_meta = None
    if task.source_media_metadata:
        try:
            src_meta = json.loads(task.source_media_metadata)
        except Exception:
            pass

    out_meta = None
    if task.output_media_metadata:
        try:
            out_meta = json.loads(task.output_media_metadata)
        except Exception:
            pass

    return {
        "id": task.id,
        "tool_type": task.tool_type,
        "source_type": task.source_type,
        "source_project_id": task.source_project_id,
        "source_filename": task.source_filename,
        "target_format": task.target_format,
        "status": task.status,
        "progress_percentage": task.progress_percentage,
        "output_filename": task.output_filename,
        "output_duration_seconds": task.output_duration_seconds,
        "output_file_size_bytes": task.output_file_size_bytes,
        "source_media_metadata": src_meta,
        "output_media_metadata": out_meta,
        "error_message": task.error_message,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


@router.get("/capabilities")
def get_toolkit_capabilities():
    """Return overview of supported and planned AI Media Toolkit capabilities and language mappings."""
    return {
        "version": "1.0.0",
        "tools": [
            {
                "id": "video_to_audio",
                "title": "Video to Audio",
                "description": "Extract pristine audio track from video files into MP3, WAV, or M4A formats with intelligent remuxing.",
                "category": "Extraction",
                "status": "available",
                "phase": "13E.1",
                "supported_formats": ["mp3", "wav", "m4a"],
            },
            {
                "id": "video_to_transcript",
                "title": "Video to Transcript",
                "description": "Generate timestamped transcripts from videos using Faster-Whisper ASR.",
                "category": "Transcription",
                "status": "planned",
                "phase": "13E.2",
                "supported_formats": ["json", "srt", "vtt"],
            },
            {
                "id": "video_to_text",
                "title": "Video to Text",
                "description": "Extract plain flowing text transcripts from video speeches.",
                "category": "Transcription",
                "status": "planned",
                "phase": "13E.2",
                "supported_formats": ["txt", "docx"],
            },
            {
                "id": "audio_to_transcript",
                "title": "Audio to Transcript",
                "description": "Transcribe standalone audio recordings with segment timestamps.",
                "category": "Transcription",
                "status": "planned",
                "phase": "13E.2",
                "supported_formats": ["json", "srt", "vtt"],
            },
            {
                "id": "audio_to_text",
                "title": "Audio to Text",
                "description": "Convert voice notes, interviews, and audio recordings to continuous text.",
                "category": "Transcription",
                "status": "planned",
                "phase": "13E.2",
                "supported_formats": ["txt"],
            },
            {
                "id": "text_to_speech",
                "title": "Text to Speech Studio",
                "description": "Standalone Khmer speech synthesis using Google Khmer, Edge Piseth/Sreymom, or VoxCPM2 voice cloning.",
                "category": "Synthesis",
                "status": "planned",
                "phase": "13E.3",
                "supported_formats": ["mp3", "wav"],
            },
            {
                "id": "transcript_to_audio",
                "title": "Transcript to Audio",
                "description": "Turn structured transcripts into continuous audio narration or timing-aligned speech tracks.",
                "category": "Synthesis",
                "status": "planned",
                "phase": "13E.4",
                "supported_formats": ["mp3", "wav"],
            },
        ],
        "language_capabilities": {
            "transcription": {
                "en": "Faster-Whisper (Full Timestamp & Punctuation Support)",
                "km": "Requires verified Khmer ASR engine",
            },
            "translation": {
                "en_to_km": "NLLB-200 / Gemini / Claude Neural Translation",
            },
            "speech_synthesis": {
                "km": "Google Khmer, Microsoft Piseth, Microsoft Sreymom, VoxCPM2 Voice Cloning",
            },
        },
    }


@router.post("/extract-audio", response_model=ToolkitTaskResponse)
async def extract_audio_from_video(
    file: Optional[UploadFile] = File(None),
    project_id: Optional[str] = Form(None),
    target_format: str = Form("mp3"),
    db: Session = Depends(get_db),
):
    """Extract audio from uploaded video or existing project video into MP3, WAV, or M4A."""
    clean_fmt = target_format.strip().lower().lstrip(".")
    if clean_fmt not in ["mp3", "wav", "m4a"]:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported target format: '{target_format}'. Supported formats are: mp3, wav, m4a.",
        )

    if not file and not project_id:
        raise HTTPException(
            status_code=400,
            detail="Either a video file upload or an existing project_id must be provided.",
        )

    task_id = str(uuid.uuid4())
    source_type = "upload" if file else "project"
    source_project_id = None
    source_filename = ""
    source_path: Optional[Path] = None

    try:
        if project_id:
            # Reusing existing authorized project video without duplicating large files
            project = db.query(Project).filter(Project.id == project_id.strip()).first()
            if not project:
                raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
            if not project.video or not project.video.file_path:
                raise HTTPException(
                    status_code=400,
                    detail=f"Project '{project.title}' does not have an uploaded video.",
                )

            p_video_path = Path(project.video.file_path)
            if not p_video_path.exists() or p_video_path.stat().st_size == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Project video file not found on disk or is empty.",
                )

            source_type = "project"
            source_project_id = project.id
            source_filename = project.video.filename or f"{project.title}.mp4"
            source_path = p_video_path
        else:
            # New video upload
            assert file is not None
            raw_filename = file.filename or "video.mp4"
            clean_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", raw_filename)
            ext = Path(clean_name).suffix.lower()
            if ext not in [".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".3gp"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported video file extension '{ext}'. Supported formats: MP4, MOV, MKV, WebM.",
                )

            input_dir = get_toolkit_task_input_dir(task_id)
            source_path = input_dir / clean_name
            source_filename = clean_name

            # Stream save uploaded video
            try:
                with open(source_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
            except Exception as e:
                logger.error("Failed to write uploaded video: %s", e)
                raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

            if not source_path.exists() or source_path.stat().st_size == 0:
                raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")

            # Check max file size limit
            max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
            if source_path.stat().st_size > max_bytes:
                delete_toolkit_task_storage(task_id)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum allowed upload size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
                )

        # Step 1: Probe video container and verify audio track existence
        try:
            v_meta = video_processor.get_metadata(source_path)
        except NoAudioTrackError as no_audio_err:
            if source_type == "upload":
                delete_toolkit_task_storage(task_id)
            raise HTTPException(status_code=400, detail=str(no_audio_err))
        except CorruptedVideoError as corrupt_err:
            if source_type == "upload":
                delete_toolkit_task_storage(task_id)
            raise HTTPException(status_code=400, detail=str(corrupt_err))
        except InvalidVideoFormatError as fmt_err:
            if source_type == "upload":
                delete_toolkit_task_storage(task_id)
            raise HTTPException(status_code=400, detail=str(fmt_err))
        except Exception as e:
            if source_type == "upload":
                delete_toolkit_task_storage(task_id)
            raise HTTPException(status_code=400, detail=f"Video validation failed: {e}")

        if not v_meta.has_audio:
            if source_type == "upload":
                delete_toolkit_task_storage(task_id)
            raise HTTPException(
                status_code=400,
                detail="The selected video does not contain an audio track to extract.",
            )

        src_meta_dict = {
            "duration_seconds": v_meta.duration_seconds,
            "width": v_meta.width,
            "height": v_meta.height,
            "video_codec": v_meta.video_codec,
            "audio_codec": v_meta.audio_codec,
            "audio_sample_rate": v_meta.audio_sample_rate,
            "audio_channels": v_meta.audio_channels,
            "file_size_bytes": source_path.stat().st_size,
        }

        # Step 2: Create task record in database
        task = ToolkitTask(
            id=task_id,
            tool_type="video_to_audio",
            source_type=source_type,
            source_project_id=source_project_id,
            source_filename=source_filename,
            source_file_path=str(source_path),
            source_media_metadata=json.dumps(src_meta_dict),
            target_format=clean_fmt,
            status="processing",
            progress_percentage=40,
        )
        db.add(task)
        db.commit()

        # Step 3: Execute audio extraction
        output_dir = get_toolkit_task_output_dir(task_id)
        stem = Path(source_filename).stem
        output_filename = f"{stem}_extracted.{clean_fmt}"
        output_path = output_dir / output_filename

        video_processor.extract_audio_format(source_path, output_path, target_format=clean_fmt)

        # Step 4: Measure extracted audio metadata
        out_meta = video_processor.get_audio_metadata(output_path)
        out_file_size = output_path.stat().st_size

        out_meta_dict = {
            "duration_seconds": out_meta.duration_seconds,
            "codec_name": out_meta.codec_name,
            "sample_rate": out_meta.sample_rate,
            "channels": out_meta.channels,
            "bit_rate": out_meta.bit_rate,
            "channel_layout": out_meta.channel_layout,
            "file_size_bytes": out_file_size,
        }

        # Step 5: Mark task complete
        task.status = "completed"
        task.progress_percentage = 100
        task.output_file_path = str(output_path)
        task.output_filename = output_filename
        task.output_duration_seconds = out_meta.duration_seconds
        task.output_file_size_bytes = out_file_size
        task.output_media_metadata = json.dumps(out_meta_dict)
        db.commit()
        db.refresh(task)

        logger.info(
            "Toolkit task %s completed: Extracted %s (%ss) from %s",
            task_id,
            clean_fmt.upper(),
            out_meta.duration_seconds,
            source_filename,
        )
        return _serialize_task(task)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error during audio extraction: %s", e)
        # Attempt to record failure in task if created
        existing_task = db.query(ToolkitTask).filter(ToolkitTask.id == task_id).first()
        if existing_task:
            existing_task.status = "failed"
            existing_task.error_message = str(e)
            db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Audio extraction failed: {e}",
        )


@router.get("/tasks", response_model=List[ToolkitTaskResponse])
def list_toolkit_tasks(
    tool_type: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Retrieve history of toolkit tasks, ordered by most recent."""
    query = db.query(ToolkitTask)
    if tool_type:
        query = query.filter(ToolkitTask.tool_type == tool_type.strip())
    tasks = query.order_by(ToolkitTask.created_at.desc()).limit(limit).all()
    return [_serialize_task(t) for t in tasks]


@router.get("/tasks/{task_id}", response_model=ToolkitTaskResponse)
def get_toolkit_task(task_id: str, db: Session = Depends(get_db)):
    """Retrieve details and status for a specific toolkit task."""
    safe_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Toolkit task '{task_id}' not found.")
    return _serialize_task(task)


@router.get("/tasks/{task_id}/stream")
def stream_toolkit_audio(task_id: str, db: Session = Depends(get_db)):
    """Stream extracted audio for in-browser audio preview player."""
    safe_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Toolkit task '{task_id}' not found.")

    if not task.output_file_path:
        raise HTTPException(status_code=404, detail="Extracted audio output not ready.")

    audio_path = Path(task.output_file_path)
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="Extracted audio file missing from disk.")

    fmt = task.target_format.lower().lstrip(".")
    mime_type = AUDIO_MIME_TYPES.get(fmt, "audio/mpeg")

    return FileResponse(
        path=str(audio_path),
        media_type=mime_type,
        filename=task.output_filename or audio_path.name,
        content_disposition_type="inline",
    )


@router.get("/tasks/{task_id}/download")
def download_toolkit_audio(task_id: str, db: Session = Depends(get_db)):
    """Download extracted audio file with standard Content-Disposition attachment header."""
    safe_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Toolkit task '{task_id}' not found.")

    if not task.output_file_path:
        raise HTTPException(status_code=404, detail="Extracted audio output not ready.")

    audio_path = Path(task.output_file_path)
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="Extracted audio file missing from disk.")

    fmt = task.target_format.lower().lstrip(".")
    mime_type = AUDIO_MIME_TYPES.get(fmt, "application/octet-stream")

    return FileResponse(
        path=str(audio_path),
        media_type=mime_type,
        filename=task.output_filename or audio_path.name,
        content_disposition_type="attachment",
    )


@router.delete("/tasks/{task_id}")
def delete_toolkit_task(task_id: str, db: Session = Depends(get_db)):
    """Delete a toolkit task record and remove its workspace storage."""
    safe_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Toolkit task '{task_id}' not found.")

    # Remove task database record
    db.delete(task)
    db.commit()

    # Clean up workspace directory safely
    cleanup_res = delete_toolkit_task_storage(safe_id)
    logger.info("Deleted toolkit task %s: %s", safe_id, cleanup_res)

    return {
        "success": True,
        "task_id": safe_id,
        "message": "Toolkit task and associated files deleted successfully.",
    }
