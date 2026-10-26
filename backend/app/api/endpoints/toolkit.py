import csv
import json
import logging
import re
import shutil
import subprocess
import uuid
import zipfile
from datetime import datetime
from app.core.timezone import get_cambodia_now, get_cambodia_now_naive
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
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
from app.services.downloader.service import downloader_service
from app.core.storage import (
    delete_toolkit_task_storage,
    get_toolkit_task_dir,
    get_toolkit_task_input_dir,
    get_toolkit_task_output_dir,
    sanitize_toolkit_task_id,
)
from app.core.credentials import is_api_key_configured
from app.database.session import get_db
from app.models.project import Project
from app.models.toolkit import (
    ToolkitTask,
    ToolkitTranscriptSegment,
    ToolkitTTSSegment,
    ToolkitTranslationSegment,
)
from app.schemas.project import VoiceOptionResponse
from app.services.subtitles.generator import (
    SubtitleCue,
    generate_csv,
    generate_srt,
    generate_txt,
    generate_vtt,
)
from app.services.subtitles.parser import (
    parse_transcript_content,
    TranscriptParseError,
)
from app.services.dubbing.synchronizer import (
    AudioSynchronizationService,
    TimingConflict,
)
from app.services.transcription.whisper import FasterWhisperTranscriptionProvider
from app.services.translation.registry import (
    get_translation_provider,
    list_translation_providers,
    validate_translation_provider,
)
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

# MIME types for audio, video, and exported file formats
AUDIO_MIME_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
}

MEDIA_MIME_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "webm": "video/webm",
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
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    voice: Optional[str] = None
    provider: Optional[str] = None
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
    source_task_id: Optional[str] = None


class TTSSegmentRegenerateRequest(BaseModel):
    text: Optional[str] = None
    pause_duration_seconds: Optional[float] = None
    voice: Optional[str] = None
    provider: Optional[str] = None


class TranscriptToAudioParseRequest(BaseModel):
    content: str
    filename: Optional[str] = None


class TranscriptToAudioSegmentInput(BaseModel):
    segment_order: int
    text: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    voice: Optional[str] = None
    provider: Optional[str] = None


class TranscriptToAudioGenerateRequest(BaseModel):
    segments: List[TranscriptToAudioSegmentInput]
    mode: str = "narration"  # "narration" or "timed"
    provider: str = "gtts"
    voice: str = "default"
    language: str = "km"
    target_format: str = "mp3"
    pause_duration_seconds: float = 0.4
    source_task_id: Optional[str] = None
    filename: Optional[str] = "transcript.srt"


class TranscriptSegmentUpdateRequest(BaseModel):
    text: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    voice: Optional[str] = None
    provider: Optional[str] = None


class SegmentUpdateRequest(BaseModel):
    text: str


class ResetEditsRequest(BaseModel):
    segment_id: Optional[str] = None


class ToolkitTranslationSegmentResponse(BaseModel):
    id: str
    task_id: str
    segment_order: int
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    source_text: str
    translated_text: str
    edited_text: Optional[str] = None
    text: str
    is_edited: bool
    status: str
    error_message: Optional[str] = None
    estimated_duration_seconds: Optional[float] = None
    is_overflow_risk: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TranslateTextRequest(BaseModel):
    text: str
    source_lang: str = "en"
    target_lang: str = "km"
    provider: str = "nllb"
    source_task_id: Optional[str] = None


class TranslateTranscriptSegmentInput(BaseModel):
    segment_order: int
    text: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None


class TranslateTranscriptRequest(BaseModel):
    segments: Optional[List[TranslateTranscriptSegmentInput]] = None
    content: Optional[str] = None
    source_lang: str = "en"
    target_lang: str = "km"
    provider: str = "nllb"
    source_task_id: Optional[str] = None
    filename: Optional[str] = "transcript.srt"


class TranslationSegmentUpdateRequest(BaseModel):
    text: str


class SubtitleConvertRequest(BaseModel):
    content: Optional[str] = None
    source_task_id: Optional[str] = None
    source_format: str = "srt"
    target_format: str = "vtt"
    filename: Optional[str] = "subtitles.vtt"


class DownloaderInfoRequest(BaseModel):
    url: str


class DownloaderStartRequest(BaseModel):
    url: str
    output_type: str = "video"
    quality: str = "best"
    audio_format: str = "mp3"
    rights_confirmed: bool = True


class DownloaderImportDubbingRequest(BaseModel):
    title: Optional[str] = None
    original_language: str = "en"
    target_language: str = "km"


class DownloaderHandoffRequest(BaseModel):
    target_tool: str


class ToolkitTaskResponse(BaseModel):
    id: str
    tool_type: str
    source_type: str
    source_project_id: Optional[str] = None
    source_task_id: Optional[str] = None
    is_outdated: bool = False
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
    translation_segments: Optional[List[ToolkitTranslationSegmentResponse]] = None
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
        "start_time": seg.start_time,
        "end_time": seg.end_time,
        "voice": seg.voice,
        "provider": seg.provider,
        "audio_file_path": seg.audio_file_path,
        "duration_seconds": seg.duration_seconds,
        "file_size_bytes": seg.file_size_bytes,
        "status": seg.status,
        "error_message": seg.error_message,
        "created_at": seg.created_at,
        "updated_at": seg.updated_at,
    }


def _serialize_translation_segment(seg: ToolkitTranslationSegment) -> Dict[str, Any]:
    """Helper to convert translation segment model to dict."""
    active_text = seg.edited_text if seg.edited_text is not None else seg.translated_text
    avail_window = (seg.end_time - seg.start_time) if (seg.start_time is not None and seg.end_time is not None) else None
    est_dur = round(len(active_text.strip()) / 12.0, 2) if active_text else 0.0
    is_overflow_risk = bool(avail_window is not None and avail_window > 0 and est_dur > (avail_window * 1.15))
    return {
        "id": seg.id,
        "task_id": seg.task_id,
        "segment_order": seg.segment_order,
        "start_time": seg.start_time,
        "end_time": seg.end_time,
        "source_text": seg.source_text,
        "translated_text": seg.translated_text,
        "edited_text": seg.edited_text,
        "text": active_text,
        "is_edited": seg.edited_text is not None and seg.edited_text != seg.translated_text,
        "status": seg.status,
        "error_message": seg.error_message,
        "estimated_duration_seconds": est_dur,
        "is_overflow_risk": is_overflow_risk,
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

    serialized_translation_segments: List[Dict[str, Any]] = []
    if hasattr(task, "translation_segments") and task.translation_segments:
        for s in sorted(task.translation_segments, key=lambda seg: seg.segment_order):
            seg_dict = _serialize_translation_segment(s)
            serialized_translation_segments.append(seg_dict)
            if seg_dict["text"].strip():
                full_text_parts.append(seg_dict["text"].strip())

    full_text = "\n\n".join(full_text_parts) if full_text_parts else None

    return {
        "id": task.id,
        "tool_type": task.tool_type,
        "source_type": task.source_type,
        "source_project_id": task.source_project_id,
        "source_task_id": task.source_task_id,
        "is_outdated": bool(task.is_outdated),
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
        "translation_segments": serialized_translation_segments or None,
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


def _generate_translation_files_on_disk(
    task_id: str,
    source_stem: str,
    segments: List[ToolkitTranslationSegment],
) -> Dict[str, Path]:
    """Generate TXT, SRT, VTT, JSON, and CSV translation files in task output directory."""
    output_dir = get_toolkit_task_output_dir(task_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    sorted_segs = sorted(segments, key=lambda s: s.segment_order)

    # 1. TXT
    lines = []
    for s in sorted_segs:
        t = (s.edited_text if s.edited_text is not None else s.translated_text) or ""
        if t.strip():
            lines.append(t.strip())
    txt_content = "\n\n".join(lines)
    txt_path = output_dir / f"{source_stem}_translated.txt"
    txt_path.write_text(txt_content, encoding="utf-8")

    # 2. JSON
    json_data = [
        {
            "segment_order": s.segment_order,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "source_text": s.source_text,
            "translated_text": s.translated_text,
            "edited_text": s.edited_text,
            "text": s.edited_text if s.edited_text is not None else s.translated_text,
        }
        for s in sorted_segs
    ]
    json_path = output_dir / f"{source_stem}_translated.json"
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # 3. Cues for SRT, VTT, CSV
    cues: List[SubtitleCue] = []
    for s in sorted_segs:
        st = s.start_time if s.start_time is not None else 0.0
        et = s.end_time if s.end_time is not None else (st + 2.0)
        t = (s.edited_text if s.edited_text is not None else s.translated_text) or ""
        cues.append(SubtitleCue(sequence=s.segment_order, start_time=st, end_time=et, text=t))

    srt_path = output_dir / f"{source_stem}_translated.srt"
    vtt_path = output_dir / f"{source_stem}_translated.vtt"
    csv_path = output_dir / f"{source_stem}_translated.csv"

    srt_path.write_text(generate_srt(cues), encoding="utf-8")
    vtt_path.write_text(generate_vtt(cues), encoding="utf-8")
    csv_path.write_text(generate_csv(cues), encoding="utf-8")

    return {
        "txt": txt_path,
        "srt": srt_path,
        "vtt": vtt_path,
        "csv": csv_path,
        "json": json_path,
    }


def validate_task_provenance(
    source_task_id: Optional[str],
    current_task_id: Optional[str],
    db: Session,
) -> Optional[ToolkitTask]:
    """Validate that source_task_id exists and does not cause a cyclic lineage dependency."""
    if not source_task_id:
        return None
    source = db.query(ToolkitTask).filter(ToolkitTask.id == source_task_id.strip()).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source task '{source_task_id}' not found.")

    if current_task_id and source.id == current_task_id:
        raise HTTPException(status_code=400, detail="A task cannot have itself as source (cycle detected).")

    visited = {current_task_id} if current_task_id else set()
    curr: Optional[ToolkitTask] = source
    while curr:
        if curr.id in visited:
            raise HTTPException(status_code=400, detail="Cyclic task provenance lineage detected.")
        visited.add(curr.id)
        if curr.source_task_id:
            curr = db.query(ToolkitTask).filter(ToolkitTask.id == curr.source_task_id).first()
        else:
            curr = None
    return source


def build_task_bundle_zip(task: ToolkitTask, db: Session) -> Path:
    """Consolidate original transcripts, translations, and generated audio into a secure ZIP archive."""
    task_id = task.id
    output_dir = get_toolkit_task_output_dir(task_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{Path(task.source_filename).stem}_bundle.zip"

    lineage_tasks: List[ToolkitTask] = []

    # 1. Source parent
    if task.source_task_id:
        parent = db.query(ToolkitTask).filter(ToolkitTask.id == task.source_task_id).first()
        if parent:
            lineage_tasks.append(parent)

    # 2. Current task
    lineage_tasks.append(task)

    # 3. Downstream children
    children = db.query(ToolkitTask).filter(ToolkitTask.source_task_id == task_id).all()
    lineage_tasks.extend(children)

    added_files: set = set()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for t in lineage_tasks:
            t_out_dir = get_toolkit_task_output_dir(t.id)
            if not t_out_dir.exists():
                continue

            for f in t_out_dir.iterdir():
                if not f.is_file() or f.name.endswith(".zip"):
                    continue
                if f.resolve() in added_files:
                    continue

                folder = "general"
                suffix = f.suffix.lower()
                name_lower = f.name.lower()
                if "translated" in name_lower or t.tool_type in ["text_translation", "transcript_translation"]:
                    folder = "translated"
                elif suffix in [".mp3", ".wav", ".m4a"] or t.tool_type in ["text_to_speech", "transcript_to_audio"]:
                    folder = "audio"
                elif suffix in [".srt", ".vtt", ".txt", ".csv", ".json"] or t.tool_type in [
                    "video_to_transcript", "audio_to_transcript", "video_to_text", "audio_to_text"
                ]:
                    folder = "original"

                safe_arcname = f"{folder}/{f.name}"
                zf.write(f, arcname=safe_arcname)
                added_files.add(f.resolve())

        manifest_text = (
            f"KhmerDub AI - Task Bundle Archive\n"
            f"Generated At: {get_cambodia_now().isoformat()}\n"
            f"Task ID: {task.id}\n"
            f"Tool Type: {task.tool_type}\n"
            f"Source Filename: {task.source_filename}\n"
            f"Source Task ID: {task.source_task_id or 'None'}\n"
            f"Lineage Task Count: {len(lineage_tasks)}\n"
        )
        zf.writestr("README.txt", manifest_text)

    return zip_path


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
                "status": "available",
                "phase": "13E.4",
                "supported_formats": ["mp3", "wav"],
            },
            {
                "id": "text_translation",
                "title": "Translation Studio",
                "description": "Translate plain text or timestamped subtitle transcripts between English and Khmer using local NLLB-200 or cloud neural models.",
                "category": "Translation",
                "status": "available",
                "phase": "13E.5",
                "supported_formats": ["txt", "srt", "vtt", "json", "csv"],
            },
            {
                "id": "subtitle_conversion",
                "title": "Subtitle Converter",
                "description": "Convert subtitle cue files seamlessly between SubRip (.srt) and WebVTT (.vtt) formats while preserving timing and formatting.",
                "category": "Conversion",
                "status": "available",
                "phase": "13E.5",
                "supported_formats": ["srt", "vtt", "txt"],
            },
            {
                "id": "video_downloader",
                "title": "Video Downloader",
                "description": "Import permitted videos from supported links (YouTube, TikTok, direct media).",
                "category": "Import",
                "status": "available",
                "phase": "13F",
                "supported_formats": ["mp4", "mp3", "wav", "m4a"],
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
    segment.updated_at = get_cambodia_now_naive()
    task.updated_at = get_cambodia_now_naive()
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

    # Mark downstream tasks as outdated
    downstream_tasks = db.query(ToolkitTask).filter(ToolkitTask.source_task_id == safe_task_id).all()
    for dt in downstream_tasks:
        dt.is_outdated = True
    if downstream_tasks:
        db.commit()

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
        s.updated_at = get_cambodia_now_naive()

    task.updated_at = get_cambodia_now_naive()
    db.commit()

    all_segments = (
        db.query(ToolkitTranscriptSegment)
        .filter(ToolkitTranscriptSegment.task_id == safe_task_id)
        .order_by(ToolkitTranscriptSegment.segment_order)
        .all()
    )
    stem = Path(task.source_filename).stem
    _generate_transcript_files_on_disk(safe_task_id, stem, all_segments)

    # Mark downstream tasks as outdated
    downstream_tasks = db.query(ToolkitTask).filter(ToolkitTask.source_task_id == safe_task_id).all()
    for dt in downstream_tasks:
        dt.is_outdated = True
    if downstream_tasks:
        db.commit()

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
    """Export transcript or translation in specified format: txt, srt, vtt, json, csv."""
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

    # Check for translation segments first
    translation_segments = (
        db.query(ToolkitTranslationSegment)
        .filter(ToolkitTranslationSegment.task_id == safe_task_id)
        .order_by(ToolkitTranslationSegment.segment_order)
        .all()
    )
    if translation_segments:
        stem = Path(task.source_filename).stem
        files_on_disk = _generate_translation_files_on_disk(safe_task_id, stem, translation_segments)
        target_file = files_on_disk[clean_fmt]
        mime_type = EXPORT_MIME_TYPES[clean_fmt]
        filename = f"{stem}_translated.{clean_fmt}"
        if clean_fmt in ["srt", "vtt"]:
            filename = f"{stem}_translated_subtitles.{clean_fmt}"
        return FileResponse(
            path=str(target_file),
            media_type=mime_type,
            filename=filename,
            content_disposition_type="attachment",
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
            detail="This task does not have any transcript or translation segments to export.",
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
    """Stream extracted audio or video for in-browser preview player."""
    safe_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Toolkit task '{task_id}' not found.")

    media_path: Optional[Path] = None
    if task.output_file_path and Path(task.output_file_path).suffix.lower() in [".mp3", ".wav", ".m4a", ".mp4", ".mov", ".webm"]:
        media_path = Path(task.output_file_path)
    else:
        # Check if prepared WAV exists in task workspace
        prep_wav = get_toolkit_task_dir(safe_id) / "prepared_audio_16k.wav"
        if prep_wav.exists() and prep_wav.stat().st_size > 0:
            media_path = prep_wav

    if not media_path or not media_path.exists() or media_path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="Media file not ready or missing from disk.")

    fmt = media_path.suffix.lower().lstrip(".")
    mime_type = MEDIA_MIME_TYPES.get(fmt, "application/octet-stream")

    return FileResponse(
        path=str(media_path),
        media_type=mime_type,
        filename=media_path.name,
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
    mime_type = MEDIA_MIME_TYPES.get(ext) or EXPORT_MIME_TYPES.get(ext, "application/octet-stream")

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

    # Section 8: Deleting a source task must not unexpectedly destroy valuable derived content.
    # Disconnect downstream derived tasks and flag them as detached/outdated while preserving their files.
    derived_tasks = db.query(ToolkitTask).filter(ToolkitTask.source_task_id == safe_id).all()
    for dt in derived_tasks:
        dt.source_task_id = None
        dt.is_outdated = True
    db.flush()

    # Remove task database record (cascade deletes segments belonging to this task)
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


def _split_oversized_grapheme_string(s: str, max_chars: int) -> List[str]:
    """Break oversized string into chunks of at most max_chars without
    breaking Khmer combining diacritics, vowels, or Coeng subscript consonants (\u17D2).
    """
    import unicodedata
    chunks = []
    rem = s
    while len(rem) > max_chars:
        cut = max_chars
        # Don't cut right before a combining mark or right after a Khmer Coeng subscript joiner
        while cut > 0 and (unicodedata.combining(rem[cut]) != 0 or rem[cut - 1] == '\u17d2'):
            cut -= 1
        if cut == 0:
            cut = max_chars
        chunks.append(rem[:cut])
        rem = rem[cut:]
    if rem:
        chunks.append(rem)
    return chunks


def split_tts_text(text: str, language: str = "km", max_chars: int = 150) -> List[str]:
    """Split text into natural segments suitable for speech synthesis.
    Respects Khmer sentence terminators (។, ៕), punctuation, newlines, and length constraints.
    Guarantees Unicode grapheme clusters and combining diacritics are preserved.
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
                        if len(part) > max_chars:
                            part_splits = _split_oversized_grapheme_string(part, max_chars)
                            for ps in part_splits[:-1]:
                                if ps.strip():
                                    segments.append(ps.strip())
                            current = part_splits[-1]
                        else:
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
    if request.source_task_id:
        validate_task_provenance(request.source_task_id, task_id, db)

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
        source_type="imported_translation" if request.source_task_id else "direct_text",
        source_task_id=request.source_task_id,
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
        failed_msgs = [s.error_message for s in segments_objs if s.error_message]
        first_err = failed_msgs[0] if failed_msgs else "Unknown synthesis error"
        task.status = "failed"
        task.error_message = f"Text-to-speech synthesis failed: {first_err}"
        db.commit()
        db.refresh(task)
        raise HTTPException(
            status_code=500,
            detail=f"Text-to-speech synthesis failed: {first_err}",
        )

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
    task = db.query(ToolkitTask).filter(
        ToolkitTask.id == safe_id,
        ToolkitTask.tool_type.in_(["text_to_speech", "transcript_to_audio"]),
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Audio synthesis task '{task_id}' not found.")

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


# -------------------------------------------------------------------------
# Phase 13E.4: Transcript-to-Audio Studio Endpoints
# -------------------------------------------------------------------------

def _assemble_transcript_audio(
    task_id: str,
    mode: str,
    segments: List[ToolkitTTSSegment],
    target_format: str = "mp3",
    pause_duration_seconds: float = 0.4,
) -> tuple[Path, Path, Path, float, List[Dict[str, Any]]]:
    """Assemble segments according to mode ('narration' vs 'timed').
    Returns (primary_output, wav_path, mp3_path, duration, conflicts_list).
    """
    output_dir = get_toolkit_task_output_dir(task_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    clean_fmt = target_format.lower().lstrip(".")
    if clean_fmt not in ["mp3", "wav"]:
        clean_fmt = "mp3"

    valid_segs = [
        s for s in segments
        if s.audio_file_path and Path(s.audio_file_path).exists() and Path(s.audio_file_path).stat().st_size > 0
    ]
    if not valid_segs:
        raise RuntimeError("No valid synthesized audio segments available to assemble.")

    sorted_segs = sorted(valid_segs, key=lambda s: (s.start_time if s.start_time is not None else 0.0, s.segment_order))

    if mode == "timed":
        sync_items = [
            {
                "segment_order": s.segment_order,
                "segment_id": s.id,
                "start_time": s.start_time if s.start_time is not None else 0.0,
                "end_time": s.end_time if s.end_time is not None else ((s.start_time or 0.0) + (s.duration_seconds or 1.0)),
                "audio_path": Path(s.audio_file_path),
                "duration_seconds": s.duration_seconds or 1.0,
            }
            for s in sorted_segs
        ]
        sync_service = AudioSynchronizationService()
        wav_out = output_dir / "narration.wav"
        sync_res = sync_service.synchronize_timed_segments(
            task_id=task_id,
            segments=sync_items,
            output_timeline_path=wav_out,
            target_duration=None,
            strict_validation=False,
        )
        total_dur = sync_res.total_duration_seconds
        mp3_out = output_dir / "narration.mp3"
        cmd_mp3 = [
            "ffmpeg",
            "-y",
            "-i", str(wav_out),
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            str(mp3_out),
        ]
        res_mp3 = subprocess.run(cmd_mp3, capture_output=True, text=True, check=False)
        if res_mp3.returncode != 0:
            raise RuntimeError(f"FFmpeg MP3 transcoding failed: {res_mp3.stderr}")
        primary_out = mp3_out if clean_fmt == "mp3" else wav_out
        conflicts = [
            {
                "segment_order": c.segment_order,
                "transcript_segment_id": c.transcript_segment_id,
                "start_time": c.start_time,
                "end_time": c.end_time,
                "original_duration": c.original_duration,
                "khmer_duration": c.khmer_duration,
                "available_window": c.available_window,
                "effective_window": c.effective_window,
                "tempo_factor": c.tempo_factor,
                "overflow_seconds": c.overflow_seconds,
                "suggested_action": c.suggested_action,
                "message": c.message,
            }
            for c in sync_res.conflicts
        ]
        return primary_out, wav_out, mp3_out, total_dur, conflicts
    else:
        # Narration mode
        primary_out, wav_out, mp3_out, total_dur = assemble_tts_narration(
            task_id=task_id,
            segments=sorted_segs,
            pause_duration_seconds=pause_duration_seconds,
            target_format=clean_fmt,
        )
        return primary_out, wav_out, mp3_out, total_dur, []


@router.post("/transcript-to-audio/parse")
def parse_transcript_endpoint(request: TranscriptToAudioParseRequest):
    """Parse transcript string (SRT, VTT, or plain text) into validated segments."""
    try:
        parsed = parse_transcript_content(request.content, filename=request.filename)
        return {
            "format": parsed.format,
            "has_timestamps": parsed.has_timestamps,
            "segments": [
                {
                    "segment_order": s.segment_order,
                    "text": s.text,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                }
                for s in parsed.segments
            ],
            "warnings": parsed.warnings,
        }
    except TranscriptParseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to parse transcript: %s", e)
        raise HTTPException(status_code=400, detail=f"Failed to parse transcript: {e}")


@router.post("/transcript-to-audio/import/{task_id}")
def import_transcript_from_task(task_id: str, db: Session = Depends(get_db)):
    """Import segments from an existing completed toolkit transcription task."""
    safe_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Toolkit task '{task_id}' not found.")

    if not task.segments:
        raise HTTPException(status_code=400, detail="Selected task does not contain any transcript segments.")

    segs = sorted(task.segments, key=lambda s: s.segment_order)
    return {
        "format": "imported",
        "has_timestamps": True,
        "source_task_id": task.id,
        "source_filename": task.source_filename,
        "segments": [
            {
                "segment_order": s.segment_order,
                "text": s.edited_text if s.edited_text else s.raw_text,
                "start_time": s.start_time,
                "end_time": s.end_time,
            }
            for s in segs
        ],
        "warnings": [],
    }


@router.post("/transcript-to-audio/generate", response_model=ToolkitTaskResponse)
def generate_transcript_to_audio(
    request: TranscriptToAudioGenerateRequest,
    db: Session = Depends(get_db),
):
    """Convert timestamped or continuous transcript segments into speech."""
    if not request.segments:
        raise HTTPException(status_code=400, detail="Transcript segments list cannot be empty.")

    clean_mode = request.mode.strip().lower()
    if clean_mode not in ["narration", "timed"]:
        clean_mode = "narration"

    if clean_mode == "timed":
        missing_timing = [s for s in request.segments if s.start_time is None or s.end_time is None]
        if missing_timing:
            raise HTTPException(
                status_code=400,
                detail=f"Timed Mode requires timestamps on all segments. {len(missing_timing)} segment(s) lack start/end times. Please supply timestamps or use Narration Mode.",
            )
        negative_timing = [s for s in request.segments if s.start_time is not None and s.start_time < 0]
        if negative_timing:
            raise HTTPException(
                status_code=400,
                detail=f"Negative timestamps are rejected: segment #{negative_timing[0].segment_order} has start time {negative_timing[0].start_time}s.",
            )
        invalid_windows = [
            s for s in request.segments
            if s.start_time is not None and s.end_time is not None and s.end_time <= s.start_time
        ]
        if invalid_windows:
            raise HTTPException(
                status_code=400,
                detail=f"End time must exceed start time: segment #{invalid_windows[0].segment_order} has start {invalid_windows[0].start_time}s and end {invalid_windows[0].end_time}s.",
            )

    provider_name = request.provider.strip().lower()
    voice = request.voice.strip()
    target_format = request.target_format.lower().lstrip(".")
    if target_format not in ["mp3", "wav"]:
        target_format = "mp3"

    if not is_valid_voice_combination(provider_name, voice, db=db):
        raise HTTPException(
            status_code=400,
            detail=f"Global voice '{voice}' with provider '{provider_name}' is not supported or authorized.",
        )

    # Check if VoxCPM is used anywhere (global or per-segment)
    needs_voxcpm = provider_name in ("voxcpm", "voxcpm2", "custom") or any(
        (s.provider or "").lower() in ("voxcpm", "voxcpm2", "custom") for s in request.segments
    )
    if needs_voxcpm:
        vox = VoxCPM2TTSProvider()
        if not vox.is_worker_online():
            raise HTTPException(
                status_code=503,
                detail="VoxCPM2 GPU inference worker is currently offline. Please ensure the worker is running or switch to Edge/Google TTS.",
            )

    task_id = str(uuid.uuid4())
    if request.source_task_id:
        validate_task_provenance(request.source_task_id, task_id, db)

    input_dir = get_toolkit_task_input_dir(task_id)
    output_dir = get_toolkit_task_output_dir(task_id)
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_manifest_path = input_dir / "source_transcript.json"
    source_manifest_path.write_text(
        json.dumps([s.model_dump() for s in request.segments], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    source_fname = request.filename or (f"import_{request.source_task_id[:8]}.srt" if request.source_task_id else "transcript.srt")
    task = ToolkitTask(
        id=task_id,
        tool_type="transcript_to_audio",
        source_type="imported_transcript" if request.source_task_id else "transcript_input",
        source_project_id=request.source_task_id,
        source_task_id=request.source_task_id,
        source_filename=source_fname,
        source_file_path=str(source_manifest_path),
        target_format=target_format,
        status="processing",
        progress_percentage=10,
        source_media_metadata=json.dumps({
            "mode": clean_mode,
            "segment_count": len(request.segments),
            "language": request.language,
            "provider": provider_name,
            "voice": voice,
            "pause_duration_seconds": request.pause_duration_seconds,
            "source_task_id": request.source_task_id,
        }),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    segments_objs: List[ToolkitTTSSegment] = []
    for s_in in request.segments:
        seg = ToolkitTTSSegment(
            id=str(uuid.uuid4()),
            task_id=task.id,
            segment_order=s_in.segment_order,
            text=s_in.text.strip(),
            start_time=s_in.start_time,
            end_time=s_in.end_time,
            voice=s_in.voice.strip() if s_in.voice else None,
            provider=s_in.provider.strip().lower() if s_in.provider else None,
            status="pending",
        )
        db.add(seg)
        segments_objs.append(seg)
    db.commit()

    # Synthesize each segment
    for seg in segments_objs:
        seg_prov_name = seg.provider or provider_name
        seg_voice_name = seg.voice or voice
        prov = get_tts_provider(seg_prov_name)
        seg_ext = "wav" if seg_prov_name in ("voxcpm", "voxcpm2", "custom") else "mp3"
        seg_file = output_dir / f"segment_{seg.segment_order:03d}.{seg_ext}"

        try:
            prov.synthesize(
                text=seg.text,
                output_path=seg_file,
                language=request.language,
                voice=seg_voice_name,
            )
            dur = video_processor.get_audio_duration(seg_file)
            seg.audio_file_path = str(seg_file)
            seg.duration_seconds = dur
            seg.file_size_bytes = seg_file.stat().st_size
            seg.status = "completed"
            seg.error_message = None
            db.commit()
        except Exception as e:
            logger.error("Segment %d synthesis failed: %s", seg.segment_order, e)
            seg.status = "failed"
            seg.error_message = str(e)
            db.commit()

    completed_segs = [s for s in segments_objs if s.status == "completed"]
    if not completed_segs:
        task.status = "failed"
        task.error_message = "All transcript segments failed speech synthesis."
        db.commit()
        db.refresh(task)
        return _serialize_task(task)

    # Assemble timeline based on mode
    primary_out, wav_out, mp3_out, total_dur, conflicts = _assemble_transcript_audio(
        task_id=task.id,
        mode=clean_mode,
        segments=completed_segs,
        target_format=target_format,
        pause_duration_seconds=request.pause_duration_seconds,
    )

    task.status = "completed"
    task.progress_percentage = 100
    task.output_file_path = str(primary_out)
    task.output_filename = primary_out.name
    task.output_duration_seconds = total_dur
    task.output_file_size_bytes = primary_out.stat().st_size
    task.output_media_metadata = json.dumps({
        "mode": clean_mode,
        "provider": provider_name,
        "voice": voice,
        "language": request.language,
        "pause_duration_seconds": request.pause_duration_seconds,
        "duration": total_dur,
        "wav_path": str(wav_out),
        "mp3_path": str(mp3_out),
        "conflicts": conflicts,
    })
    db.commit()
    db.refresh(task)
    return _serialize_task(task)


@router.put("/transcript-to-audio/tasks/{task_id}/segments/{segment_id}", response_model=ToolkitTaskResponse)
def update_transcript_to_audio_segment(
    task_id: str,
    segment_id: str,
    request: TranscriptSegmentUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update text, timing, or voice override for an individual transcript segment."""
    safe_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id, ToolkitTask.tool_type == "transcript_to_audio").first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Transcript-to-audio task '{task_id}' not found.")

    seg = db.query(ToolkitTTSSegment).filter(ToolkitTTSSegment.id == segment_id, ToolkitTTSSegment.task_id == safe_id).first()
    if not seg:
        raise HTTPException(status_code=404, detail=f"Segment '{segment_id}' not found.")

    if request.text is not None:
        clean_text = request.text.strip()
        if not clean_text:
            raise HTTPException(status_code=400, detail="Segment text cannot be empty.")
        seg.text = clean_text

    new_start = float(request.start_time) if request.start_time is not None else seg.start_time
    new_end = float(request.end_time) if request.end_time is not None else seg.end_time

    if new_start is not None and new_start < 0:
        raise HTTPException(status_code=400, detail="Negative timestamps are rejected.")
    if new_start is not None and new_end is not None and new_end <= new_start:
        raise HTTPException(status_code=400, detail="End time must exceed start time.")

    seg.start_time = new_start
    seg.end_time = new_end

    if request.voice is not None:
        seg.voice = request.voice.strip() if request.voice.strip() else None
    if request.provider is not None:
        seg.provider = request.provider.strip().lower() if request.provider.strip() else None

    db.commit()
    db.refresh(task)
    return _serialize_task(task)


@router.post("/transcript-to-audio/tasks/{task_id}/segments/{segment_id}/regenerate", response_model=ToolkitTaskResponse)
def regenerate_transcript_segment(
    task_id: str,
    segment_id: str,
    request: TranscriptSegmentUpdateRequest,
    db: Session = Depends(get_db),
):
    """Regenerate speech for a single transcript segment and reassemble the narration timeline."""
    safe_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id, ToolkitTask.tool_type == "transcript_to_audio").first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Transcript-to-audio task '{task_id}' not found.")

    seg = db.query(ToolkitTTSSegment).filter(ToolkitTTSSegment.id == segment_id, ToolkitTTSSegment.task_id == safe_id).first()
    if not seg:
        raise HTTPException(status_code=404, detail=f"Segment '{segment_id}' not found.")

    if request.text is not None:
        clean_text = request.text.strip()
        if not clean_text:
            raise HTTPException(status_code=400, detail="Segment text cannot be empty.")
        seg.text = clean_text

    if request.start_time is not None:
        seg.start_time = max(0.0, float(request.start_time))
    if request.end_time is not None:
        seg.end_time = max(0.0, float(request.end_time))
    if seg.start_time is not None and seg.end_time is not None and seg.end_time <= seg.start_time:
        seg.end_time = seg.start_time + 1.0

    if request.voice is not None:
        seg.voice = request.voice.strip() if request.voice.strip() else None
    if request.provider is not None:
        seg.provider = request.provider.strip().lower() if request.provider.strip() else None

    db.commit()

    meta = {}
    if task.output_media_metadata:
        try:
            meta = json.loads(task.output_media_metadata)
        except Exception:
            pass

    mode = meta.get("mode", "narration")
    global_prov = meta.get("provider", "gtts")
    global_voice = meta.get("voice", "default")
    language = meta.get("language", "km")
    pause_dur = meta.get("pause_duration_seconds", 0.4)

    seg_prov = seg.provider or global_prov
    seg_voice = seg.voice or global_voice

    if seg_prov in ("voxcpm", "voxcpm2", "custom"):
        vox = VoxCPM2TTSProvider()
        if not vox.is_worker_online():
            raise HTTPException(
                status_code=503,
                detail="VoxCPM2 GPU inference worker is currently offline. Cannot regenerate segment.",
            )

    provider = get_tts_provider(seg_prov)
    output_dir = get_toolkit_task_output_dir(safe_id)
    seg_ext = "wav" if seg_prov in ("voxcpm", "voxcpm2", "custom") else "mp3"
    seg_file = output_dir / f"segment_{seg.segment_order:03d}.{seg_ext}"

    try:
        provider.synthesize(
            text=seg.text,
            output_path=seg_file,
            language=language,
            voice=seg_voice,
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

    # Reassemble timeline
    all_segs = db.query(ToolkitTTSSegment).filter(ToolkitTTSSegment.task_id == safe_id).order_by(ToolkitTTSSegment.segment_order).all()
    completed_segs = [s for s in all_segs if s.status == "completed"]
    if completed_segs:
        primary_out, wav_out, mp3_out, total_dur, conflicts = _assemble_transcript_audio(
            task_id=safe_id,
            mode=mode,
            segments=completed_segs,
            target_format=task.target_format,
            pause_duration_seconds=pause_dur,
        )
        task.output_file_path = str(primary_out)
        task.output_filename = primary_out.name
        task.output_duration_seconds = total_dur
        task.output_file_size_bytes = primary_out.stat().st_size
        meta["duration"] = total_dur
        meta["wav_path"] = str(wav_out)
        meta["mp3_path"] = str(mp3_out)
        meta["conflicts"] = conflicts
        task.output_media_metadata = json.dumps(meta)
        db.commit()

    db.refresh(task)
    return _serialize_task(task)


@router.delete("/transcript-to-audio/tasks/{task_id}/segments/{segment_id}", response_model=ToolkitTaskResponse)
def delete_transcript_segment(
    task_id: str,
    segment_id: str,
    db: Session = Depends(get_db),
):
    """Delete a segment from a transcript-to-audio task, resequence remaining segments, and rebuild the timeline."""
    safe_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id, ToolkitTask.tool_type == "transcript_to_audio").first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Transcript-to-audio task '{task_id}' not found.")

    seg = db.query(ToolkitTTSSegment).filter(ToolkitTTSSegment.id == segment_id, ToolkitTTSSegment.task_id == safe_id).first()
    if not seg:
        raise HTTPException(status_code=404, detail=f"Segment '{segment_id}' not found.")

    # Delete segment audio file if exists
    if seg.audio_file_path:
        p = Path(seg.audio_file_path)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

    db.delete(seg)
    db.commit()

    # Resequence remaining segments 1..N
    remaining = db.query(ToolkitTTSSegment).filter(ToolkitTTSSegment.task_id == safe_id).order_by(ToolkitTTSSegment.segment_order).all()
    for idx, s in enumerate(remaining, start=1):
        s.segment_order = idx
    db.commit()

    meta = {}
    if task.output_media_metadata:
        try:
            meta = json.loads(task.output_media_metadata)
        except Exception:
            pass

    mode = meta.get("mode", "narration")
    pause_dur = meta.get("pause_duration_seconds", 0.4)

    completed_segs = [s for s in remaining if s.status == "completed"]
    if completed_segs:
        primary_out, wav_out, mp3_out, total_dur, conflicts = _assemble_transcript_audio(
            task_id=safe_id,
            mode=mode,
            segments=completed_segs,
            target_format=task.target_format,
            pause_duration_seconds=pause_dur,
        )
        task.output_file_path = str(primary_out)
        task.output_filename = primary_out.name
        task.output_duration_seconds = total_dur
        task.output_file_size_bytes = primary_out.stat().st_size
        meta["duration"] = total_dur
        meta["wav_path"] = str(wav_out)
        meta["mp3_path"] = str(mp3_out)
        meta["conflicts"] = conflicts
        task.output_media_metadata = json.dumps(meta)
        db.commit()
    else:
        task.output_duration_seconds = 0.0
        task.output_file_size_bytes = 0
        meta["duration"] = 0.0
        meta["conflicts"] = []
        task.output_media_metadata = json.dumps(meta)
        db.commit()

    db.refresh(task)
    return _serialize_task(task)


# ==============================================================================
# Phase 13E.5: Translation Studio, Subtitle Converter & Connected Workflows
# ==============================================================================

SUPPORTED_LANGUAGE_PAIRS = [
    {"source_lang": "en", "target_lang": "km", "source_name": "English", "target_name": "Khmer", "verified": True},
    {"source_lang": "km", "target_lang": "en", "source_name": "Khmer", "target_name": "English", "verified": True},
]


@router.get("/translation/languages")
def get_translation_languages():
    """Return verified supported language pairs for translation."""
    return SUPPORTED_LANGUAGE_PAIRS


@router.get("/translation/providers")
def get_translation_providers():
    """Return available translation providers with configuration status."""
    return list_translation_providers()


@router.post("/translation/translate-text", response_model=ToolkitTaskResponse)
def translate_text(request: TranslateTextRequest, db: Session = Depends(get_db)):
    """Translate standalone text between English and Khmer using local NLLB or cloud neural models."""
    clean_text = (request.text or "").strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    provider_name = request.provider.strip().lower()
    validate_translation_provider(provider_name)

    if provider_name != "nllb" and not is_api_key_configured(provider_name):
        raise HTTPException(
            status_code=400,
            detail=f"Translation provider '{provider_name}' is unavailable because its API key is not configured. Please select Meta NLLB-200 (local) or configure credentials in Settings.",
        )

    if not any(p["source_lang"] == request.source_lang and p["target_lang"] == request.target_lang for p in SUPPORTED_LANGUAGE_PAIRS):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language pair {request.source_lang} -> {request.target_lang}. Verified pairs: en <-> km.",
        )

    task_id = str(uuid.uuid4())
    if request.source_task_id:
        validate_task_provenance(request.source_task_id, task_id, db)

    chunks = split_tts_text(clean_text, language=request.source_lang, max_chars=300)
    if not chunks:
        chunks = [clean_text]

    try:
        provider = get_translation_provider(provider_name)
        translated_chunks = provider.translate(
            texts=chunks,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
        )
    except Exception as e:
        logger.error("Text translation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Translation failed: {e}")

    task_dir = get_toolkit_task_dir(task_id)
    input_dir = get_toolkit_task_input_dir(task_id)
    output_dir = get_toolkit_task_output_dir(task_id)
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    src_file = input_dir / "source_text.txt"
    src_file.write_text(clean_text, encoding="utf-8")

    task = ToolkitTask(
        id=task_id,
        tool_type="text_translation",
        source_type="direct_text",
        source_task_id=request.source_task_id,
        is_outdated=False,
        source_filename=f"translation_{request.source_lang}_{request.target_lang}_{task_id[:8]}.txt",
        source_file_path=str(src_file),
        target_format="txt",
        status="completed",
        progress_percentage=100,
        source_media_metadata=json.dumps({
            "character_count": len(clean_text),
            "source_lang": request.source_lang,
            "target_lang": request.target_lang,
            "provider": provider_name,
            "segment_count": len(chunks),
        }),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    seg_models: List[ToolkitTranslationSegment] = []
    for idx, (orig, trans) in enumerate(zip(chunks, translated_chunks), start=1):
        seg = ToolkitTranslationSegment(
            id=str(uuid.uuid4()),
            task_id=task.id,
            segment_order=idx,
            start_time=None,
            end_time=None,
            source_text=orig,
            translated_text=trans,
            edited_text=None,
            status="completed",
        )
        db.add(seg)
        seg_models.append(seg)
    db.commit()

    stem = Path(task.source_filename).stem
    files_on_disk = _generate_translation_files_on_disk(task_id, stem, seg_models)
    task.output_file_path = str(files_on_disk["txt"])
    task.output_filename = files_on_disk["txt"].name
    task.output_file_size_bytes = files_on_disk["txt"].stat().st_size
    task.output_media_metadata = json.dumps({
        "translated_character_count": sum(len(s.translated_text) for s in seg_models),
        "segment_count": len(seg_models),
        "source_lang": request.source_lang,
        "target_lang": request.target_lang,
        "provider": provider_name,
    })
    db.commit()
    db.refresh(task)

    return _serialize_task(task)


@router.post("/translation/translate-transcript", response_model=ToolkitTaskResponse)
def translate_transcript(request: TranslateTranscriptRequest, db: Session = Depends(get_db)):
    """Translate timestamped transcript cues while strictly preserving start/end timing."""
    provider_name = request.provider.strip().lower()
    validate_translation_provider(provider_name)

    if provider_name != "nllb" and not is_api_key_configured(provider_name):
        raise HTTPException(
            status_code=400,
            detail=f"Translation provider '{provider_name}' is unavailable because its API key is not configured. Please select Meta NLLB-200 (local) or configure credentials in Settings.",
        )

    if not any(p["source_lang"] == request.source_lang and p["target_lang"] == request.target_lang for p in SUPPORTED_LANGUAGE_PAIRS):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language pair {request.source_lang} -> {request.target_lang}. Verified pairs: en <-> km.",
        )

    task_id = str(uuid.uuid4())
    if request.source_task_id:
        validate_task_provenance(request.source_task_id, task_id, db)

    raw_segments: List[Dict[str, Any]] = []
    if request.segments and len(request.segments) > 0:
        for s in request.segments:
            raw_segments.append({
                "segment_order": s.segment_order,
                "text": s.text.strip(),
                "start_time": s.start_time,
                "end_time": s.end_time,
            })
    elif request.source_task_id:
        source_task = db.query(ToolkitTask).filter(ToolkitTask.id == request.source_task_id.strip()).first()
        if not source_task:
            raise HTTPException(status_code=404, detail=f"Source task '{request.source_task_id}' not found.")
        src_segs = (
            db.query(ToolkitTranscriptSegment)
            .filter(ToolkitTranscriptSegment.task_id == source_task.id)
            .order_by(ToolkitTranscriptSegment.segment_order)
            .all()
        )
        for s in src_segs:
            raw_segments.append({
                "segment_order": s.segment_order,
                "text": (s.edited_text if s.edited_text is not None else s.raw_text).strip(),
                "start_time": s.start_time,
                "end_time": s.end_time,
            })
    else:
        raise HTTPException(status_code=400, detail="No transcript segments provided for translation.")

    if not raw_segments:
        raise HTTPException(status_code=400, detail="Transcript has 0 segments.")

    texts_to_translate = [s["text"] for s in raw_segments]
    try:
        provider = get_translation_provider(provider_name)
        translated_texts = provider.translate(
            texts=texts_to_translate,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
        )
    except Exception as e:
        logger.error("Transcript translation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Translation failed: {e}")

    task_dir = get_toolkit_task_dir(task_id)
    input_dir = get_toolkit_task_input_dir(task_id)
    output_dir = get_toolkit_task_output_dir(task_id)
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_fname = request.filename or f"transcript_{task_id[:8]}.srt"
    manifest_file = input_dir / "source_manifest.json"
    manifest_file.write_text(json.dumps(raw_segments, ensure_ascii=False, indent=2), encoding="utf-8")

    task = ToolkitTask(
        id=task_id,
        tool_type="transcript_translation",
        source_type="imported_transcript" if request.source_task_id else "transcript_input",
        source_task_id=request.source_task_id,
        is_outdated=False,
        source_filename=source_fname,
        source_file_path=str(manifest_file),
        target_format="srt",
        status="completed",
        progress_percentage=100,
        source_media_metadata=json.dumps({
            "segment_count": len(raw_segments),
            "source_lang": request.source_lang,
            "target_lang": request.target_lang,
            "provider": provider_name,
        }),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    seg_models: List[ToolkitTranslationSegment] = []
    for idx, (raw_seg, trans) in enumerate(zip(raw_segments, translated_texts), start=1):
        seg = ToolkitTranslationSegment(
            id=str(uuid.uuid4()),
            task_id=task.id,
            segment_order=raw_seg.get("segment_order", idx),
            start_time=raw_seg.get("start_time"),
            end_time=raw_seg.get("end_time"),
            source_text=raw_seg["text"],
            translated_text=trans,
            edited_text=None,
            status="completed",
        )
        db.add(seg)
        seg_models.append(seg)
    db.commit()

    stem = Path(source_fname).stem
    files_on_disk = _generate_translation_files_on_disk(task_id, stem, seg_models)
    task.output_file_path = str(files_on_disk["srt"])
    task.output_filename = files_on_disk["srt"].name
    task.output_file_size_bytes = files_on_disk["srt"].stat().st_size
    task.output_media_metadata = json.dumps({
        "segment_count": len(seg_models),
        "source_lang": request.source_lang,
        "target_lang": request.target_lang,
        "provider": provider_name,
        "has_timestamps": True,
    })
    db.commit()
    db.refresh(task)

    return _serialize_task(task)


@router.put("/translation/tasks/{task_id}/segments/{segment_id}", response_model=ToolkitTranslationSegmentResponse)
def update_translation_segment(
    task_id: str,
    segment_id: str,
    body: TranslationSegmentUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update edited text of a specific translation segment. Flags downstream tasks as outdated."""
    safe_task_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Toolkit task '{task_id}' not found.")

    seg = (
        db.query(ToolkitTranslationSegment)
        .filter(
            ToolkitTranslationSegment.id == segment_id.strip(),
            ToolkitTranslationSegment.task_id == safe_task_id,
        )
        .first()
    )
    if not seg:
        raise HTTPException(status_code=404, detail=f"Translation segment '{segment_id}' not found.")

    new_text = body.text.strip()
    seg.edited_text = new_text
    seg.updated_at = get_cambodia_now_naive()
    task.updated_at = get_cambodia_now_naive()
    db.commit()
    db.refresh(seg)

    all_segs = (
        db.query(ToolkitTranslationSegment)
        .filter(ToolkitTranslationSegment.task_id == safe_task_id)
        .order_by(ToolkitTranslationSegment.segment_order)
        .all()
    )
    stem = Path(task.source_filename).stem
    _generate_translation_files_on_disk(safe_task_id, stem, all_segs)

    # Mark downstream tasks outdated
    downstream = db.query(ToolkitTask).filter(ToolkitTask.source_task_id == safe_task_id).all()
    for dt in downstream:
        dt.is_outdated = True
    if downstream:
        db.commit()

    return _serialize_translation_segment(seg)


@router.post("/translation/tasks/{task_id}/segments/{segment_id}/retry", response_model=ToolkitTranslationSegmentResponse)
def retry_translation_segment(
    task_id: str,
    segment_id: str,
    db: Session = Depends(get_db),
):
    """Re-translate a single segment using its source text."""
    safe_task_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Toolkit task '{task_id}' not found.")

    seg = (
        db.query(ToolkitTranslationSegment)
        .filter(
            ToolkitTranslationSegment.id == segment_id.strip(),
            ToolkitTranslationSegment.task_id == safe_task_id,
        )
        .first()
    )
    if not seg:
        raise HTTPException(status_code=404, detail=f"Translation segment '{segment_id}' not found.")

    meta = {}
    if task.source_media_metadata:
        try:
            meta = json.loads(task.source_media_metadata)
        except Exception:
            pass

    provider_name = meta.get("provider", "nllb")
    source_lang = meta.get("source_lang", "en")
    target_lang = meta.get("target_lang", "km")

    try:
        provider = get_translation_provider(provider_name)
        new_trans = provider.translate(
            texts=[seg.source_text],
            source_lang=source_lang,
            target_lang=target_lang,
        )
        seg.translated_text = new_trans[0]
        seg.edited_text = None
        seg.status = "completed"
        seg.error_message = None
        seg.updated_at = get_cambodia_now_naive()
        task.updated_at = get_cambodia_now_naive()
        db.commit()
        db.refresh(seg)
    except Exception as e:
        logger.error("Segment re-translation failed: %s", e)
        seg.status = "failed"
        seg.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Segment re-translation failed: {e}")

    all_segs = (
        db.query(ToolkitTranslationSegment)
        .filter(ToolkitTranslationSegment.task_id == safe_task_id)
        .order_by(ToolkitTranslationSegment.segment_order)
        .all()
    )
    stem = Path(task.source_filename).stem
    _generate_translation_files_on_disk(safe_task_id, stem, all_segs)

    # Mark downstream tasks outdated
    downstream = db.query(ToolkitTask).filter(ToolkitTask.source_task_id == safe_task_id).all()
    for dt in downstream:
        dt.is_outdated = True
    if downstream:
        db.commit()

    return _serialize_translation_segment(seg)


@router.post("/subtitle/convert")
def convert_subtitles(request: SubtitleConvertRequest, db: Session = Depends(get_db)):
    """Convert subtitles between SRT, WebVTT, and plain text formats."""
    content = (request.content or "").strip()
    if not content and request.source_task_id:
        src_task = db.query(ToolkitTask).filter(ToolkitTask.id == request.source_task_id.strip()).first()
        if not src_task:
            raise HTTPException(status_code=404, detail=f"Source task '{request.source_task_id}' not found.")
        out_dir = get_toolkit_task_output_dir(src_task.id)
        candidates = list(out_dir.glob("*.srt")) + list(out_dir.glob("*.vtt")) + list(out_dir.glob("*.txt"))
        if candidates:
            content = candidates[0].read_text(encoding="utf-8")
        else:
            raise HTTPException(status_code=404, detail="No subtitle content found for source task.")

    if not content:
        raise HTTPException(status_code=400, detail="No subtitle content provided.")

    target_fmt = request.target_format.lower().strip().lstrip(".")
    if target_fmt not in ["srt", "vtt", "txt"]:
        raise HTTPException(status_code=400, detail=f"Unsupported target format '{request.target_format}'. Supported: srt, vtt, txt.")

    try:
        parsed = parse_transcript_content(content, filename=request.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse subtitle content: {e}")

    cues: List[SubtitleCue] = []
    for seg in parsed.segments:
        st = seg.start_time if seg.start_time is not None else 0.0
        et = seg.end_time if seg.end_time is not None else (st + 2.0)
        cues.append(SubtitleCue(sequence=seg.segment_order, start_time=st, end_time=et, text=seg.text))

    if target_fmt == "vtt":
        converted = generate_vtt(cues)
    elif target_fmt == "srt":
        converted = generate_srt(cues)
    else:
        converted = generate_txt(cues)

    stem = Path(request.filename or "converted_subtitles").stem
    out_filename = f"{stem}.{target_fmt}"

    return {
        "success": True,
        "source_format": parsed.format,
        "target_format": target_fmt,
        "segment_count": len(cues),
        "filename": out_filename,
        "content": converted,
    }


@router.get("/tasks/{task_id}/bundle")
def download_task_bundle(task_id: str, db: Session = Depends(get_db)):
    """Download consolidated ZIP archive containing related inputs, transcripts, translations, and audio."""
    safe_id = sanitize_toolkit_task_id(task_id)
    task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Toolkit task '{task_id}' not found.")

    zip_file = build_task_bundle_zip(task, db)
    if not zip_file.exists() or zip_file.stat().st_size == 0:
        raise HTTPException(status_code=500, detail="Failed to create bundle archive.")

    return FileResponse(
        path=str(zip_file),
        media_type="application/zip",
        filename=zip_file.name,
        content_disposition_type="attachment",
    )


# ---------------- Video Downloader Endpoints (Phase 13F) ----------------


@router.post("/downloader/info")
def inspect_downloader_url(req: DownloaderInfoRequest):
    """Inspect video/audio link metadata without downloading media."""
    return downloader_service.inspect_url(req.url)


@router.post("/downloader/start", response_model=ToolkitTaskResponse)
def start_downloader_task(
    req: DownloaderStartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Start an asynchronous media download and normalization task."""
    task = downloader_service.start_download(
        db=db,
        background_tasks=background_tasks,
        url=req.url,
        output_type=req.output_type,
        quality=req.quality,
        audio_format=req.audio_format,
        rights_confirmed=req.rights_confirmed,
    )
    return _serialize_task(task)


@router.post("/downloader/{task_id}/cancel")
def cancel_downloader_task(task_id: str, db: Session = Depends(get_db)):
    """Cancel an active or queued video download task."""
    safe_id = sanitize_toolkit_task_id(task_id)
    return downloader_service.cancel_task(db=db, task_id=safe_id)


@router.post("/downloader/{task_id}/import-dubbing")
def import_downloader_task_to_dubbing(
    task_id: str,
    req: DownloaderImportDubbingRequest,
    db: Session = Depends(get_db),
):
    """Import a completed downloaded video into a Video Dubbing project."""
    safe_id = sanitize_toolkit_task_id(task_id)
    project = downloader_service.import_to_dubbing(
        db=db,
        task_id=safe_id,
        title=req.title,
        original_lang=req.original_language,
        target_lang=req.target_language,
    )
    return {
        "success": True,
        "project_id": project.id,
        "title": project.title,
        "status": project.status.value if hasattr(project.status, "value") else str(project.status),
        "duration": project.video.duration_seconds if project.video else None,
    }


@router.post("/downloader/{task_id}/handoff", response_model=ToolkitTaskResponse)
def handoff_downloader_task_to_toolkit(
    task_id: str,
    req: DownloaderHandoffRequest,
    db: Session = Depends(get_db),
):
    """Transfer downloaded media directly into another Media Toolkit studio."""
    safe_id = sanitize_toolkit_task_id(task_id)
    source_task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_id).first()
    if not source_task:
        raise HTTPException(status_code=404, detail="Source download task not found")
    if source_task.status != "completed":
        raise HTTPException(status_code=400, detail="Only completed download tasks can be transferred.")
    if not source_task.output_file_path or not Path(source_task.output_file_path).exists():
        raise HTTPException(status_code=404, detail="Downloaded media file not found on disk.")

    valid_tools = {"video_to_audio", "video_to_transcript", "video_to_text"}
    if req.target_tool not in valid_tools:
        raise HTTPException(
            status_code=400,
            detail=f"Target tool '{req.target_tool}' is not supported for video downloader handoff.",
        )

    # Create new task workspace and link/copy media
    new_task_id = str(uuid.uuid4())
    new_input_dir = get_toolkit_task_input_dir(new_task_id)
    source_file = Path(source_task.output_file_path)
    dest_file = new_input_dir / source_file.name
    shutil.copy2(source_file, dest_file)

    target_fmt = "mp3" if req.target_tool == "video_to_audio" else ("srt" if req.target_tool == "video_to_transcript" else "txt")

    new_task = ToolkitTask(
        id=new_task_id,
        tool_type=req.target_tool,
        source_type="task_transfer",
        source_task_id=source_task.id,
        source_filename=source_task.output_filename or source_file.name,
        source_file_path=str(dest_file),
        source_media_metadata=source_task.output_media_metadata,
        target_format=target_fmt,
        status="pending",
        progress_percentage=0,
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    return _serialize_task(new_task)


