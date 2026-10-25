import csv
import json
import logging
import re
import shutil
import subprocess
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
    Response,
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
from app.models.toolkit import ToolkitTask, ToolkitTranscriptSegment, ToolkitTTSSegment
from app.schemas.project import VoiceOptionResponse
from app.services.subtitles.generator import (
    SubtitleCue,
    generate_csv,
    generate_srt,
    generate_txt,
    generate_vtt,
)
from app.services.transcription.whisper import FasterWhisperTranscriptionProvider
from app.services.tts.registry import (
    get_tts_provider,
    is_valid_voice_combination,
    list_supported_voices,
)
from app.services.tts.voxcpm import VoxCPM2TTSProvider
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
whisper_provider = FasterWhisperTranscriptionProvider()

# MIME types for audio and exported file formats
AUDIO_MIME_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
}

EXPORT_MIME_TYPES = {
    "txt": "text/plain; charset=utf-8",
    "srt": "application/x-subrip; charset=utf-8",
    "vtt": "text/vtt; charset=utf-8",
    "json": "application/json; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
}

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".3gp"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg", ".wma"}
ALL_MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


class ToolkitTranscriptSegmentResponse(BaseModel):
    id: str
    task_id: str
    segment_order: int
    start_time: float
    end_time: float
    raw_text: str
    edited_text: Optional[str] = None
    text: str
    is_edited: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ToolkitTTSSegmentResponse(BaseModel):
    id: str
    task_id: str
    segment_order: int
    text: str
    audio_file_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    file_size_bytes: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TTSPreviewRequest(BaseModel):
    text: str
    provider: str
    voice: str
    language: str = "km"


class TTSGenerateRequest(BaseModel):
    text: str
    provider: str
    voice: str
    language: str = "km"
    target_format: str = "mp3"
    pause_duration_seconds: float = 0.4


class TTSSegmentRegenerateRequest(BaseModel):
    text: Optional[str] = None
    pause_duration_seconds: Optional[float] = None


class SegmentUpdateRequest(BaseModel):
    text: str


class ResetEditsRequest(BaseModel):
    segment_id: Optional[str] = None


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
    segments: Optional[List[ToolkitTranscriptSegmentResponse]] = None
    tts_segments: Optional[List[ToolkitTTSSegmentResponse]] = None
    full_text: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


def _serialize_segment(seg: ToolkitTranscriptSegment) -> Dict[str, Any]:
    """Helper to convert segment model to dict."""
    active_text = seg.edited_text if seg.edited_text is not None else seg.raw_text
    return {
        "id": seg.id,
        "task_id": seg.task_id,
        "segment_order": seg.segment_order,
        "start_time": seg.start_time,
        "end_time": seg.end_time,
        "raw_text": seg.raw_text,
        "edited_text": seg.edited_text,
        "text": active_text,
        "is_edited": seg.edited_text is not None and seg.edited_text != seg.raw_text,
        "created_at": seg.created_at,
        "updated_at": seg.updated_at,
    }


def _serialize_tts_segment(seg: ToolkitTTSSegment) -> Dict[str, Any]:
    """Helper to convert TTS segment model to dict."""
    return {
        "id": seg.id,
        "task_id": seg.task_id,
        "segment_order": seg.segment_order,
        "text": seg.text,
        "audio_file_path": seg.audio_file_path,
        "duration_seconds": seg.duration_seconds,
        "file_size_bytes": seg.file_size_bytes,
        "status": seg.status,
        "error_message": seg.error_message,
        "created_at": seg.created_at,
        "updated_at": seg.updated_at,
    }


def _serialize_task(task: ToolkitTask) -> Dict[str, Any]:
    """Helper to convert task SQLAlchemy model to dict with parsed JSON metadata and segments."""
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

    serialized_segments: List[Dict[str, Any]] = []
    full_text_parts: List[str] = []
    if hasattr(task, "segments") and task.segments:
        for s in sorted(task.segments, key=lambda seg: seg.segment_order):
            seg_dict = _serialize_segment(s)
            serialized_segments.append(seg_dict)
            if seg_dict["text"].strip():
                full_text_parts.append(seg_dict["text"].strip())

    serialized_tts_segments: List[Dict[str, Any]] = []
    if hasattr(task, "tts_segments") and task.tts_segments:
        for s in sorted(task.tts_segments, key=lambda seg: seg.segment_order):
            serialized_tts_segments.append(_serialize_tts_segment(s))
            if s.text and s.text.strip():
                full_text_parts.append(s.text.strip())

    full_text = "\n\n".join(full_text_parts) if full_text_parts else None

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
        "segments": serialized_segments or None,
        "tts_segments": serialized_tts_segments or None,
        "full_text": full_text,
    }


def _generate_transcript_files_on_disk(
    task_id: str, source_stem: str, segments: List[ToolkitTranscriptSegment]
) -> Dict[str, Path]:
    """Generate TXT, SRT, VTT, JSON, and CSV transcript files in task output directory."""
    output_dir = get_toolkit_task_output_dir(task_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    cues: List[SubtitleCue] = []
    for s in sorted(segments, key=lambda seg: seg.segment_order):
        active_text = s.edited_text if s.edited_text is not None else s.raw_text
        cues.append(
            SubtitleCue(
                sequence=s.segment_order,
                start_time=s.start_time,
                end_time=s.end_time,
                text=active_text,
            )
        )

    # 1. TXT
    txt_content = generate_txt(cues)
    txt_path = output_dir / f"{source_stem}_transcript.txt"
    txt_path.write_text(txt_content, encoding="utf-8")

    # 2. SRT
    srt_content = generate_srt(cues)
    srt_path = output_dir / f"{source_stem}_subtitles.srt"
    srt_path.write_text(srt_content, encoding="utf-8")

    # 3. VTT
    vtt_content = generate_vtt(cues)
    vtt_path = output_dir / f"{source_stem}_subtitles.vtt"
    vtt_path.write_text(vtt_content, encoding="utf-8")

    # 4. CSV
    csv_content = generate_csv(cues)
    csv_path = output_dir / f"{source_stem}_transcript.csv"
    csv_path.write_text(csv_content, encoding="utf-8")

    # 5. JSON
    json_data = [
        {
            "sequence": c.sequence,
            "start_time": c.start_time,
            "end_time": c.end_time,
            "text": c.text,
        }
        for c in cues
    ]
    json_path = output_dir / f"{source_stem}_transcript.json"
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "txt": txt_path,
        "srt": srt_path,
        "vtt": vtt_path,
        "csv": csv_path,
        "json": json_path,
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
                "description": "Generate timestamped transcripts from videos using Faster-Whisper ASR with subtitle export.",
                "category": "Transcription",
                "status": "available",
                "phase": "13E.2",
                "supported_formats": ["srt", "vtt", "json", "csv", "txt"],
            },
            {
                "id": "video_to_text",
                "title": "Video to Text",
                "description": "Extract flowing plain text transcripts from video speeches with one-click copying and TXT download.",
                "category": "Transcription",
                "status": "available",
                "phase": "13E.2",
                "supported_formats": ["txt", "json"],
            },
            {
                "id": "audio_to_transcript",
                "title": "Audio to Transcript",
                "description": "Transcribe standalone audio recordings (WAV, MP3, M4A, FLAC) into structured timestamped speech segments.",
                "category": "Transcription",
                "status": "available",
                "phase": "13E.2",
                "supported_formats": ["srt", "vtt", "json", "csv", "txt"],
            },
            {
                "id": "audio_to_text",
                "title": "Audio to Text",
                "description": "Convert voice notes, interviews, and audio recordings to continuous text.",
                "category": "Transcription",
                "status": "available",
                "phase": "13E.2",
                "supported_formats": ["txt", "json"],
            },
            {
                "id": "text_to_speech",
                "title": "Text to Speech Studio",
                "description": "Standalone Khmer & English speech synthesis using Google Khmer, Edge Piseth/Sreymom/Aria/Guy, or authorized VoxCPM2 voice cloning.",
                "category": "Synthesis",
                "status": "available",
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
                "en": "Faster-Whisper (Full Timestamp & Punctuation Support) - Available",
                "km": "Khmer ASR requires verified specialized Khmer engine (Currently Unavailable)",
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
            assert file is not None
            raw_filename = file.filename or "video.mp4"
            clean_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", raw_filename)
            ext = Path(clean_name).suffix.lower()
            if ext not in VIDEO_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported video file extension '{ext}'. Supported formats: MP4, MOV, MKV, WebM.",
                )

            input_dir = get_toolkit_task_input_dir(task_id)
            source_path = input_dir / clean_name
            source_filename = clean_name

            try:
                with open(source_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
            except Exception as e:
                logger.error("Failed to write uploaded video: %s", e)
                raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

            if not source_path.exists() or source_path.stat().st_size == 0:
                raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")

            max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
            if source_path.stat().st_size > max_bytes:
                delete_toolkit_task_storage(task_id)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum allowed upload size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
                )

        # Probe video container and verify audio track existence
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

        output_dir = get_toolkit_task_output_dir(task_id)
        stem = Path(source_filename).stem
        output_filename = f"{stem}_extracted.{clean_fmt}"
        output_path = output_dir / output_filename

        video_processor.extract_audio_format(source_path, output_path, target_format=clean_fmt)

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
        existing_task = db.query(ToolkitTask).filter(ToolkitTask.id == task_id).first()
        if existing_task:
            existing_task.status = "failed"
            existing_task.error_message = str(e)
            db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Audio extraction failed: {e}",
        )


@router.post("/transcribe", response_model=ToolkitTaskResponse)
async def transcribe_media(
    file: Optional[UploadFile] = File(None),
    project_id: Optional[str] = Form(None),
    tool_type: str = Form("video_to_transcript"),
    target_format: str = Form("srt"),
    language: str = Form("en"),
    reuse_existing: bool = Form(True),
    db: Session = Depends(get_db),
):
    """Transcribe video or audio media into timestamped segments and plain text.

    Supported tool_types:
      - video_to_transcript: Timestamped speech segments from video.
      - video_to_text: Readable continuous text transcript from video.
      - audio_to_transcript: Timestamped speech segments from standalone audio.
      - audio_to_text: Readable continuous text transcript from standalone audio.

    Supports instant transcript reuse from existing projects and completed tasks.
    """
    valid_tools = ["video_to_transcript", "video_to_text", "audio_to_transcript", "audio_to_text"]
    if tool_type not in valid_tools:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tool_type '{tool_type}'. Valid tools are: {', '.join(valid_tools)}.",
        )

    clean_lang = (language or "en").strip().lower()
    if clean_lang in ["km", "khmer"]:
        raise HTTPException(
            status_code=400,
            detail="Khmer speech recognition is not officially supported by the current Whisper checkpoint and requires a verified Khmer ASR engine. Please select English (en).",
        )
    elif clean_lang not in ["en", "english"]:
        raise HTTPException(
            status_code=400,
            detail=f"Language '{language}' is not supported. Supported transcription language: 'en' (English).",
        )

    if not file and not project_id:
        raise HTTPException(
            status_code=400,
            detail="Either a media file upload or an existing project_id must be provided.",
        )

    task_id = str(uuid.uuid4())
    source_type = "upload" if file else "project"
    source_project_id = None
    source_filename = ""
    source_path: Optional[Path] = None

    try:
        # Step A: Resolve media source
        if project_id:
            project = db.query(Project).filter(Project.id == project_id.strip()).first()
            if not project:
                raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
            if not project.video or not project.video.file_path:
                raise HTTPException(
                    status_code=400,
                    detail=f"Project '{project.title}' does not have an uploaded video or audio track.",
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

            # Instant Reuse Check: If project already has transcripts, reuse directly!
            if reuse_existing and project.transcript_segments:
                logger.info(
                    "Reusing %d existing transcripts from project %s for toolkit task %s",
                    len(project.transcript_segments),
                    project.id,
                    task_id,
                )
                stem = Path(source_filename).stem
                task = ToolkitTask(
                    id=task_id,
                    tool_type=tool_type,
                    source_type=source_type,
                    source_project_id=source_project_id,
                    source_filename=source_filename,
                    source_file_path=str(source_path),
                    target_format=target_format,
                    status="completed",
                    progress_percentage=100,
                    output_duration_seconds=project.video.duration_seconds,
                    output_file_size_bytes=source_path.stat().st_size,
                )
                db.add(task)

                seg_records: List[ToolkitTranscriptSegment] = []
                for p_seg in sorted(project.transcript_segments, key=lambda s: s.start_time):
                    seg_rec = ToolkitTranscriptSegment(
                        id=str(uuid.uuid4()),
                        task_id=task_id,
                        segment_order=p_seg.segment_order,
                        start_time=round(float(p_seg.start_time), 2),
                        end_time=round(float(p_seg.end_time), 2),
                        raw_text=p_seg.text.strip(),
                        edited_text=None,
                    )
                    db.add(seg_rec)
                    seg_records.append(seg_rec)

                # Generate export files on disk
                files_on_disk = _generate_transcript_files_on_disk(task_id, stem, seg_records)
                primary_export = files_on_disk.get(target_format, files_on_disk["srt"])
                task.output_file_path = str(primary_export)
                task.output_filename = primary_export.name

                total_words = sum(len(s.raw_text.split()) for s in seg_records)
                task.output_media_metadata = json.dumps({
                    "language": "en",
                    "segment_count": len(seg_records),
                    "word_count": total_words,
                    "reused_from_project": project.id,
                })
                db.commit()
                db.refresh(task)
                return _serialize_task(task)

        else:
            # Uploaded file
            assert file is not None
            raw_filename = file.filename or "media_upload"
            clean_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", raw_filename)
            ext = Path(clean_name).suffix.lower()

            # Tool-type specific extension check
            is_audio_tool = tool_type in ["audio_to_transcript", "audio_to_text"]
            if is_audio_tool and ext not in AUDIO_EXTENSIONS and ext not in VIDEO_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file format '{ext}' for audio transcription. Supported formats: WAV, MP3, M4A, FLAC, OGG, AAC.",
                )
            elif not is_audio_tool and ext not in ALL_MEDIA_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file format '{ext}' for video transcription. Supported formats: MP4, MOV, MKV, WebM.",
                )

            input_dir = get_toolkit_task_input_dir(task_id)
            source_path = input_dir / clean_name
            source_filename = clean_name

            try:
                with open(source_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
            except Exception as e:
                logger.error("Failed to write uploaded media: %s", e)
                raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

            if not source_path.exists() or source_path.stat().st_size == 0:
                raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")

            max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
            if source_path.stat().st_size > max_bytes:
                delete_toolkit_task_storage(task_id)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum allowed upload size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
                )

        # Step B: Probe media audio stream
        try:
            audio_meta = video_processor.get_audio_metadata(source_path)
        except NoAudioTrackError as no_audio_err:
            if source_type == "upload":
                delete_toolkit_task_storage(task_id)
            raise HTTPException(status_code=400, detail=str(no_audio_err))
        except CorruptedVideoError as corrupt_err:
            if source_type == "upload":
                delete_toolkit_task_storage(task_id)
            raise HTTPException(status_code=400, detail=str(corrupt_err))
        except Exception as e:
            if source_type == "upload":
                delete_toolkit_task_storage(task_id)
            raise HTTPException(status_code=400, detail=f"Media audio validation failed: {e}")

        src_meta_dict = {
            "duration_seconds": audio_meta.duration_seconds,
            "codec_name": audio_meta.codec_name,
            "sample_rate": audio_meta.sample_rate,
            "channels": audio_meta.channels,
            "file_size_bytes": source_path.stat().st_size,
        }

        # Step C: Create task record
        task = ToolkitTask(
            id=task_id,
            tool_type=tool_type,
            source_type=source_type,
            source_project_id=source_project_id,
            source_filename=source_filename,
            source_file_path=str(source_path),
            source_media_metadata=json.dumps(src_meta_dict),
            target_format=target_format,
            status="processing",
            progress_percentage=25,
        )
        db.add(task)
        db.commit()

        # Step D: Prepare 16kHz mono WAV for Whisper
        task_dir = get_toolkit_task_dir(task_id)
        wav_prep_path = task_dir / "prepared_audio_16k.wav"
        video_processor.prepare_audio_for_transcription(source_path, wav_prep_path)

        task.progress_percentage = 50
        db.commit()

        # Step E: Perform Whisper Transcription
        logger.info("Transcribing audio %s with Faster-Whisper...", wav_prep_path.name)
        raw_segments = whisper_provider.transcribe(wav_prep_path, language="en")
        task.progress_percentage = 85
        db.commit()

        # Step F: Store segments in DB
        stem = Path(source_filename).stem
        seg_records: List[ToolkitTranscriptSegment] = []
        for order, s in enumerate(raw_segments, start=1):
            seg_rec = ToolkitTranscriptSegment(
                id=str(uuid.uuid4()),
                task_id=task_id,
                segment_order=order,
                start_time=s.start_time,
                end_time=s.end_time,
                raw_text=s.text.strip(),
                edited_text=None,
            )
            db.add(seg_rec)
            seg_records.append(seg_rec)

        db.commit()

        # Step G: Pre-generate export files on disk
        files_on_disk = _generate_transcript_files_on_disk(task_id, stem, seg_records)
        clean_target_fmt = target_format.lower().lstrip(".")
        primary_export = files_on_disk.get(clean_target_fmt, files_on_disk["srt"])

        total_words = sum(len(s.raw_text.split()) for s in seg_records)
        out_meta_dict = {
            "language": "en",
            "segment_count": len(seg_records),
            "word_count": total_words,
            "duration_seconds": audio_meta.duration_seconds,
        }

        task.status = "completed"
        task.progress_percentage = 100
        task.output_file_path = str(primary_export)
        task.output_filename = primary_export.name
        task.output_duration_seconds = audio_meta.duration_seconds
        task.output_file_size_bytes = primary_export.stat().st_size
        task.output_media_metadata = json.dumps(out_meta_dict)
        db.commit()
        db.refresh(task)

        logger.info(
            "Toolkit transcription task %s completed: %d segments (%d words) for %s",
            task_id,
            len(seg_records),
            total_words,
            source_filename,
        )
        return _serialize_task(task)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error during transcription: %s", e)
        existing_task = db.query(ToolkitTask).filter(ToolkitTask.id == task_id).first()
        if existing_task:
            existing_task.status = "failed"
            existing_task.error_message = str(e)
            db.commit()
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")


@router.put("/tasks/{task_id}/segments/{segment_id}", response_model=ToolkitTranscriptSegmentResponse)
def update_transcript_segment(
    task_id: str,
    segment_id: str,
    body: SegmentUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update edited text of a specific transcript segment. Edits persist across reloads."""
    safe_task_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Toolkit task '{task_id}' not found.")

    segment = (
        db.query(ToolkitTranscriptSegment)
        .filter(
            ToolkitTranscriptSegment.id == segment_id.strip(),
            ToolkitTranscriptSegment.task_id == safe_task_id,
        )
        .first()
    )
    if not segment:
        raise HTTPException(
            status_code=404,
            detail=f"Segment '{segment_id}' not found for task '{task_id}'.",
        )

    new_text = body.text.strip()
    segment.edited_text = new_text
    segment.updated_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(segment)

    # Re-generate export files on disk so downloads reflect updated edits
    all_segments = (
        db.query(ToolkitTranscriptSegment)
        .filter(ToolkitTranscriptSegment.task_id == safe_task_id)
        .order_by(ToolkitTranscriptSegment.segment_order)
        .all()
    )
    stem = Path(task.source_filename).stem
    _generate_transcript_files_on_disk(safe_task_id, stem, all_segments)

    return _serialize_segment(segment)


@router.post("/tasks/{task_id}/reset-edits")
def reset_transcript_edits(
    task_id: str,
    body: Optional[ResetEditsRequest] = None,
    db: Session = Depends(get_db),
):
    """Revert segment text back to original verbatim raw ASR recognition."""
    safe_task_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Toolkit task '{task_id}' not found.")

    query = db.query(ToolkitTranscriptSegment).filter(ToolkitTranscriptSegment.task_id == safe_task_id)
    if body and body.segment_id:
        query = query.filter(ToolkitTranscriptSegment.id == body.segment_id.strip())

    segments = query.all()
    if not segments:
        raise HTTPException(status_code=404, detail="No matching segments found to reset.")

    for s in segments:
        s.edited_text = None
        s.updated_at = datetime.utcnow()

    task.updated_at = datetime.utcnow()
    db.commit()

    all_segments = (
        db.query(ToolkitTranscriptSegment)
        .filter(ToolkitTranscriptSegment.task_id == safe_task_id)
        .order_by(ToolkitTranscriptSegment.segment_order)
        .all()
    )
    stem = Path(task.source_filename).stem
    _generate_transcript_files_on_disk(safe_task_id, stem, all_segments)

    return {
        "success": True,
        "reset_count": len(segments),
        "segments": [_serialize_segment(s) for s in all_segments],
    }


@router.get("/tasks/{task_id}/export/{format}")
def export_toolkit_transcript(
    task_id: str,
    format: str,
    db: Session = Depends(get_db),
):
    """Export transcript in specified format: txt, srt, vtt, json, csv."""
    safe_task_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Toolkit task '{task_id}' not found.")

    clean_fmt = format.lower().strip().lstrip(".")
    if clean_fmt not in EXPORT_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported export format '{format}'. Supported formats: {', '.join(EXPORT_MIME_TYPES.keys())}.",
        )

    all_segments = (
        db.query(ToolkitTranscriptSegment)
        .filter(ToolkitTranscriptSegment.task_id == safe_task_id)
        .order_by(ToolkitTranscriptSegment.segment_order)
        .all()
    )
    if not all_segments:
        raise HTTPException(
            status_code=404,
            detail="This task does not have any transcript segments to export.",
        )

    stem = Path(task.source_filename).stem
    files_on_disk = _generate_transcript_files_on_disk(safe_task_id, stem, all_segments)
    target_file = files_on_disk[clean_fmt]

    mime_type = EXPORT_MIME_TYPES[clean_fmt]
    filename = f"{stem}_transcript.{clean_fmt}"
    if clean_fmt in ["srt", "vtt"]:
        filename = f"{stem}_subtitles.{clean_fmt}"

    return FileResponse(
        path=str(target_file),
        media_type=mime_type,
        filename=filename,
        content_disposition_type="attachment",
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
    """Retrieve details, status, and transcript segments for a specific toolkit task."""
    safe_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Toolkit task '{task_id}' not found.")
    return _serialize_task(task)


@router.get("/tasks/{task_id}/stream")
def stream_toolkit_audio(task_id: str, db: Session = Depends(get_db)):
    """Stream extracted audio or prepared audio for in-browser audio preview player."""
    safe_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Toolkit task '{task_id}' not found.")

    audio_path: Optional[Path] = None
    if task.output_file_path and Path(task.output_file_path).suffix.lower() in [".mp3", ".wav", ".m4a"]:
        audio_path = Path(task.output_file_path)
    else:
        # Check if prepared WAV exists in task workspace
        prep_wav = get_toolkit_task_dir(safe_id) / "prepared_audio_16k.wav"
        if prep_wav.exists() and prep_wav.stat().st_size > 0:
            audio_path = prep_wav

    if not audio_path or not audio_path.exists() or audio_path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="Audio file not ready or missing from disk.")

    fmt = audio_path.suffix.lower().lstrip(".")
    mime_type = AUDIO_MIME_TYPES.get(fmt, "audio/wav")

    return FileResponse(
        path=str(audio_path),
        media_type=mime_type,
        filename=audio_path.name,
        content_disposition_type="inline",
    )


@router.get("/tasks/{task_id}/download")
def download_toolkit_file(task_id: str, db: Session = Depends(get_db)):
    """Download primary output file with standard Content-Disposition attachment header."""
    safe_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Toolkit task '{task_id}' not found.")

    if not task.output_file_path:
        raise HTTPException(status_code=404, detail="Task output not ready.")

    file_path = Path(task.output_file_path)
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="Task output file missing from disk.")

    ext = file_path.suffix.lower().lstrip(".")
    mime_type = AUDIO_MIME_TYPES.get(ext) or EXPORT_MIME_TYPES.get(ext, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        media_type=mime_type,
        filename=task.output_filename or file_path.name,
        content_disposition_type="attachment",
    )


@router.delete("/tasks/{task_id}")
def delete_toolkit_task(task_id: str, db: Session = Depends(get_db)):
    """Delete a toolkit task record and remove its workspace storage."""
    safe_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Toolkit task '{task_id}' not found.")

    # Remove task database record (cascade deletes segments)
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


def split_tts_text(text: str, language: str = "km", max_chars: int = 150) -> List[str]:
    """Split text into natural segments suitable for speech synthesis.
    Respects Khmer sentence terminators (។, ៕), punctuation, newlines, and length constraints.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    raw_paragraphs = [p.strip() for p in cleaned.split("\n") if p.strip()]
    segments: List[str] = []
    boundary_pattern = re.compile(r"([^។៕.!?;\n]+[។៕.!?;\n]*)")

    for para in raw_paragraphs:
        chunks = [c.strip() for c in boundary_pattern.findall(para) if c.strip()]
        if not chunks:
            chunks = [para]

        for chunk in chunks:
            if len(chunk) <= max_chars:
                segments.append(chunk)
            else:
                sub_parts = re.split(r"([,፣\s]+)", chunk)
                current = ""
                for part in sub_parts:
                    if len(current) + len(part) <= max_chars:
                        current += part
                    else:
                        if current.strip():
                            segments.append(current.strip())
                        current = part
                if current.strip():
                    segments.append(current.strip())

    final_segments = [s.strip() for s in segments if s.strip()]
    return final_segments if final_segments else [cleaned]


def assemble_tts_narration(
    task_id: str,
    segments: List[ToolkitTTSSegment],
    pause_duration_seconds: float = 0.4,
    target_format: str = "mp3",
    ffmpeg_bin: str = "ffmpeg",
) -> tuple[Path, Path, Path, float]:
    """Assemble synthesized segment audio files into a unified narration audio file.
    Inserts a silence interval of pause_duration_seconds between segments if specified.
    Returns: (primary_output_path, wav_output_path, mp3_output_path, total_duration_seconds)
    """
    output_dir = get_toolkit_task_output_dir(task_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    standard_segments_dir = output_dir / "standard_segments"
    standard_segments_dir.mkdir(parents=True, exist_ok=True)

    valid_segments = [
        s for s in segments
        if s.audio_file_path and Path(s.audio_file_path).exists() and Path(s.audio_file_path).stat().st_size > 0
    ]
    if not valid_segments:
        raise RuntimeError("No synthesized audio segments available to assemble narration.")

    # Convert each segment to standard 44.1kHz stereo 16-bit PCM WAV
    standard_segment_paths: List[Path] = []
    for s in valid_segments:
        src = Path(s.audio_file_path)
        dst = standard_segments_dir / f"std_{s.segment_order:03d}.wav"
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", str(src),
            "-acodec", "pcm_s16le",
            "-ar", "44100",
            "-ac", "2",
            str(dst),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg failed to standardize segment {s.segment_order}: {res.stderr}")
        standard_segment_paths.append(dst)

    # Generate silence file if pause is specified and more than 1 segment
    silence_path: Optional[Path] = None
    if pause_duration_seconds > 0.01 and len(standard_segment_paths) > 1:
        silence_path = standard_segments_dir / "pause_silence.wav"
        dur = max(0.01, round(pause_duration_seconds, 3))
        cmd = [
            ffmpeg_bin,
            "-y",
            "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=stereo",
            "-t", f"{dur:.3f}",
            "-acodec", "pcm_s16le",
            "-ar", "44100",
            "-ac", "2",
            str(silence_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg failed to generate silence: {res.stderr}")

    # Build concat manifest
    manifest_path = standard_segments_dir / "concat_list.txt"
    with open(manifest_path, "w", encoding="utf-8") as f:
        for idx, seg_path in enumerate(standard_segment_paths):
            f.write(f"file '{seg_path.absolute()}'\n")
            if silence_path and idx < len(standard_segment_paths) - 1:
                f.write(f"file '{silence_path.absolute()}'\n")

    # Concat into WAV
    wav_output_path = output_dir / "narration.wav"
    cmd_concat = [
        ffmpeg_bin,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(manifest_path),
        "-c", "copy",
        str(wav_output_path),
    ]
    res = subprocess.run(cmd_concat, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {res.stderr}")

    # Transcode to MP3
    mp3_output_path = output_dir / "narration.mp3"
    cmd_mp3 = [
        ffmpeg_bin,
        "-y",
        "-i", str(wav_output_path),
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(mp3_output_path),
    ]
    res_mp3 = subprocess.run(cmd_mp3, capture_output=True, text=True, check=False)
    if res_mp3.returncode != 0:
        raise RuntimeError(f"FFmpeg MP3 transcoding failed: {res_mp3.stderr}")

    total_duration = video_processor.get_audio_duration(wav_output_path)
    primary_output = wav_output_path if target_format.lower().lstrip(".") == "wav" else mp3_output_path

    return primary_output, wav_output_path, mp3_output_path, total_duration


# --- Phase 13E.3 Text to Speech Studio Endpoints ---


@router.get("/tts/voices")
def get_tts_voices(language: Optional[str] = None, db: Session = Depends(get_db)):
    """List all supported system and authorized custom TTS voices, optionally filtered by language."""
    return list_supported_voices(db=db, language=language)


@router.post("/tts/preview")
def preview_tts(request: TTSPreviewRequest, db: Session = Depends(get_db)):
    """Generate a short audio preview for the selected voice and sample text."""
    clean_text = (request.text or "").strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Preview text cannot be empty.")
    sample_text = clean_text[:200]
    provider_name = request.provider.strip().lower()
    voice = request.voice.strip()

    if not is_valid_voice_combination(provider_name, voice, db=db):
        raise HTTPException(
            status_code=400,
            detail=f"Voice '{voice}' with provider '{provider_name}' is not supported or not authorized.",
        )

    if provider_name in ("voxcpm", "voxcpm2", "custom"):
        vox = VoxCPM2TTSProvider()
        if not vox.is_worker_online():
            raise HTTPException(
                status_code=503,
                detail="VoxCPM2 GPU inference worker is currently offline. Please ensure the worker is running or switch to Edge/Google TTS.",
            )

    try:
        provider = get_tts_provider(provider_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    temp_preview_dir = settings.TEMP_DIR / "tts_previews"
    temp_preview_dir.mkdir(parents=True, exist_ok=True)
    preview_id = str(uuid.uuid4())
    ext = "wav" if provider_name in ("voxcpm", "voxcpm2", "custom") else "mp3"
    preview_file = temp_preview_dir / f"preview_{preview_id}.{ext}"

    try:
        provider.synthesize(
            text=sample_text,
            output_path=preview_file,
            language=request.language,
            voice=voice,
        )
    except Exception as e:
        logger.error("TTS preview synthesis failed: %s", e)
        raise HTTPException(status_code=500, detail=f"TTS synthesis error: {e}")

    mime = AUDIO_MIME_TYPES.get(ext, "audio/wav")
    return FileResponse(
        path=str(preview_file),
        media_type=mime,
        filename=preview_file.name,
        content_disposition_type="inline",
    )


@router.post("/tts/generate", response_model=ToolkitTaskResponse)
def generate_tts(request: TTSGenerateRequest, db: Session = Depends(get_db)):
    """Convert multi-sentence plain text into structured speech segments and assembled narration."""
    clean_text = (request.text or "").strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    provider_name = request.provider.strip().lower()
    voice = request.voice.strip()
    target_format = request.target_format.lower().lstrip(".")
    if target_format not in ["mp3", "wav"]:
        target_format = "mp3"

    if not is_valid_voice_combination(provider_name, voice, db=db):
        raise HTTPException(
            status_code=400,
            detail=f"Voice '{voice}' with provider '{provider_name}' is not supported or not authorized.",
        )

    if provider_name in ("voxcpm", "voxcpm2", "custom"):
        vox = VoxCPM2TTSProvider()
        if not vox.is_worker_online():
            raise HTTPException(
                status_code=503,
                detail="VoxCPM2 GPU inference worker is currently offline. Please ensure the worker is running or switch to Edge/Google TTS.",
            )

    task_id = str(uuid.uuid4())
    task_dir = get_toolkit_task_dir(task_id)
    input_dir = get_toolkit_task_input_dir(task_id)
    output_dir = get_toolkit_task_output_dir(task_id)
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    text_source_path = input_dir / "source_text.txt"
    text_source_path.write_text(clean_text, encoding="utf-8")

    task = ToolkitTask(
        id=task_id,
        tool_type="text_to_speech",
        source_type="direct_text",
        source_filename=f"tts_{request.language}_{provider_name}_{voice[:8]}.txt",
        source_file_path=str(text_source_path),
        target_format=target_format,
        status="processing",
        progress_percentage=5,
        source_media_metadata=json.dumps({
            "character_count": len(clean_text),
            "language": request.language,
            "provider": provider_name,
            "voice": voice,
            "pause_duration_seconds": request.pause_duration_seconds,
        }),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Split text into segments
    segment_texts = split_tts_text(clean_text, language=request.language)
    segments_objs: List[ToolkitTTSSegment] = []
    for idx, s_text in enumerate(segment_texts, start=1):
        seg = ToolkitTTSSegment(
            id=str(uuid.uuid4()),
            task_id=task.id,
            segment_order=idx,
            text=s_text,
            status="pending",
        )
        db.add(seg)
        segments_objs.append(seg)
    db.commit()

    provider = get_tts_provider(provider_name)
    seg_ext = "wav" if provider_name in ("voxcpm", "voxcpm2", "custom") else "mp3"

    for idx, seg in enumerate(segments_objs):
        seg_file = output_dir / f"segment_{seg.segment_order:03d}.{seg_ext}"
        try:
            provider.synthesize(
                text=seg.text,
                output_path=seg_file,
                language=request.language,
                voice=voice,
            )
            dur = video_processor.get_audio_duration(seg_file)
            seg.audio_file_path = str(seg_file)
            seg.duration_seconds = dur
            seg.file_size_bytes = seg_file.stat().st_size
            seg.status = "completed"
        except Exception as e:
            logger.error("Segment %d synthesis failed: %s", seg.segment_order, e)
            seg.status = "failed"
            seg.error_message = str(e)
        db.commit()
        task.progress_percentage = 10 + int(70 * (idx + 1) / len(segments_objs))
        db.commit()

    completed_segs = [s for s in segments_objs if s.status == "completed"]
    if not completed_segs:
        task.status = "failed"
        task.error_message = "All text segments failed to synthesize."
        db.commit()
        db.refresh(task)
        raise HTTPException(status_code=500, detail="Text-to-speech synthesis failed for all segments.")

    try:
        primary_out, wav_out, mp3_out, total_dur = assemble_tts_narration(
            task_id=task.id,
            segments=completed_segs,
            pause_duration_seconds=request.pause_duration_seconds,
            target_format=target_format,
        )
        task.output_file_path = str(primary_out)
        task.output_filename = primary_out.name
        task.output_duration_seconds = total_dur
        task.output_file_size_bytes = primary_out.stat().st_size
        task.output_media_metadata = json.dumps({
            "provider": provider_name,
            "voice": voice,
            "language": request.language,
            "segment_count": len(segments_objs),
            "pause_duration_seconds": request.pause_duration_seconds,
            "wav_path": str(wav_out),
            "mp3_path": str(mp3_out),
        })
        task.progress_percentage = 100
        task.status = "completed"
    except Exception as e:
        logger.error("Narration assembly failed: %s", e)
        task.status = "failed"
        task.error_message = f"Narration assembly failed: {e}"
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))

    db.commit()
    db.refresh(task)
    return _serialize_task(task)


@router.post("/tts/tasks/{task_id}/segments/{segment_id}/regenerate", response_model=ToolkitTaskResponse)
def regenerate_tts_segment(
    task_id: str,
    segment_id: str,
    request: TTSSegmentRegenerateRequest,
    db: Session = Depends(get_db),
):
    """Regenerate a single TTS speech segment with optional text update, and rebuild narration."""
    safe_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id, ToolkitTask.tool_type == "text_to_speech").first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Text-to-speech task '{task_id}' not found.")

    seg = db.query(ToolkitTTSSegment).filter(ToolkitTTSSegment.id == segment_id, ToolkitTTSSegment.task_id == safe_id).first()
    if not seg:
        raise HTTPException(status_code=404, detail=f"TTS segment '{segment_id}' not found in task '{task_id}'.")

    if request.text and request.text.strip():
        seg.text = request.text.strip()

    meta = {}
    if task.output_media_metadata:
        try:
            meta = json.loads(task.output_media_metadata)
        except Exception:
            pass
    if not meta and task.source_media_metadata:
        try:
            meta = json.loads(task.source_media_metadata)
        except Exception:
            pass

    provider_name = meta.get("provider", "gtts")
    voice = meta.get("voice", "default")
    language = meta.get("language", "km")
    pause_dur = request.pause_duration_seconds if request.pause_duration_seconds is not None else meta.get("pause_duration_seconds", 0.4)

    if provider_name in ("voxcpm", "voxcpm2", "custom"):
        vox = VoxCPM2TTSProvider()
        if not vox.is_worker_online():
            raise HTTPException(
                status_code=503,
                detail="VoxCPM2 GPU inference worker is currently offline. Cannot regenerate segment.",
            )

    provider = get_tts_provider(provider_name)
    output_dir = get_toolkit_task_output_dir(safe_id)
    seg_ext = "wav" if provider_name in ("voxcpm", "voxcpm2", "custom") else "mp3"
    seg_file = output_dir / f"segment_{seg.segment_order:03d}.{seg_ext}"

    try:
        provider.synthesize(
            text=seg.text,
            output_path=seg_file,
            language=language,
            voice=voice,
        )
        dur = video_processor.get_audio_duration(seg_file)
        seg.audio_file_path = str(seg_file)
        seg.duration_seconds = dur
        seg.file_size_bytes = seg_file.stat().st_size
        seg.status = "completed"
        seg.error_message = None
        db.commit()
    except Exception as e:
        logger.error("Segment regeneration failed: %s", e)
        seg.status = "failed"
        seg.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Segment regeneration failed: {e}")

    # Reassemble narration
    all_segs = db.query(ToolkitTTSSegment).filter(ToolkitTTSSegment.task_id == safe_id).order_by(ToolkitTTSSegment.segment_order).all()
    completed_segs = [s for s in all_segs if s.status == "completed"]
    if completed_segs:
        primary_out, wav_out, mp3_out, total_dur = assemble_tts_narration(
            task_id=safe_id,
            segments=completed_segs,
            pause_duration_seconds=pause_dur,
            target_format=task.target_format,
        )
        task.output_file_path = str(primary_out)
        task.output_filename = primary_out.name
        task.output_duration_seconds = total_dur
        task.output_file_size_bytes = primary_out.stat().st_size
        meta["duration"] = total_dur
        meta["pause_duration_seconds"] = pause_dur
        meta["wav_path"] = str(wav_out)
        meta["mp3_path"] = str(mp3_out)
        task.output_media_metadata = json.dumps(meta)
        db.commit()

    db.refresh(task)
    return _serialize_task(task)


@router.get("/tts/tasks/{task_id}/segments/{segment_id}/stream")
def stream_tts_segment(task_id: str, segment_id: str, db: Session = Depends(get_db)):
    """Stream audio for an individual synthesized speech segment."""
    safe_id = sanitize_toolkit_task_id(task_id)
    seg = db.query(ToolkitTTSSegment).filter(ToolkitTTSSegment.id == segment_id, ToolkitTTSSegment.task_id == safe_id).first()
    if not seg or not seg.audio_file_path:
        raise HTTPException(status_code=404, detail="Segment audio not found.")

    p = Path(seg.audio_file_path)
    if not p.exists() or p.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="Segment audio file missing from disk.")

    ext = p.suffix.lower().lstrip(".")
    mime = AUDIO_MIME_TYPES.get(ext, "audio/wav")
    return FileResponse(path=str(p), media_type=mime, filename=p.name, content_disposition_type="inline")


@router.get("/tts/tasks/{task_id}/segments/{segment_id}/download")
def download_tts_segment(task_id: str, segment_id: str, db: Session = Depends(get_db)):
    """Download audio for an individual synthesized speech segment."""
    safe_id = sanitize_toolkit_task_id(task_id)
    seg = db.query(ToolkitTTSSegment).filter(ToolkitTTSSegment.id == segment_id, ToolkitTTSSegment.task_id == safe_id).first()
    if not seg or not seg.audio_file_path:
        raise HTTPException(status_code=404, detail="Segment audio not found.")

    p = Path(seg.audio_file_path)
    if not p.exists() or p.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="Segment audio file missing from disk.")

    ext = p.suffix.lower().lstrip(".")
    mime = AUDIO_MIME_TYPES.get(ext, "audio/wav")
    return FileResponse(path=str(p), media_type=mime, filename=p.name, content_disposition_type="attachment")


@router.get("/tts/tasks/{task_id}/export")
def export_tts_narration(
    task_id: str,
    format: str = "mp3",
    db: Session = Depends(get_db),
):
    """Export the assembled narration in either MP3 or WAV format."""
    safe_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id, ToolkitTask.tool_type == "text_to_speech").first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Text-to-speech task '{task_id}' not found.")

    output_dir = get_toolkit_task_output_dir(safe_id)
    req_fmt = format.lower().lstrip(".")
    if req_fmt not in ["mp3", "wav"]:
        req_fmt = "mp3"

    target_path = output_dir / f"narration.{req_fmt}"
    if not target_path.exists() or target_path.stat().st_size == 0:
        if task.output_file_path and Path(task.output_file_path).exists():
            target_path = Path(task.output_file_path)
        else:
            raise HTTPException(status_code=404, detail=f"Narration file for format '{req_fmt}' not found.")

    ext = target_path.suffix.lower().lstrip(".")
    mime = AUDIO_MIME_TYPES.get(ext, "audio/wav")
    return FileResponse(
        path=str(target_path),
        media_type=mime,
        filename=f"narration_{safe_id[:8]}.{ext}",
        content_disposition_type="attachment",
    )
