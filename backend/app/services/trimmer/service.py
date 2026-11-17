"""Video and Audio Trimmer Service for KhmerDub AI Media Toolkit.

Provides frame-accurate or fast stream-copy media trimming, waveform peak extraction,
and thumbnail generation with robust path-traversal safeguards.
"""

import base64
import json
import logging
import re
import shutil
import struct
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import (
    sanitize_toolkit_task_id,
    get_project_original_dir,
    get_project_extracted_dir,
)
from app.core.timezone import get_cambodia_now_naive
from app.models.project import Project, Video, ProjectStatus
from app.models.toolkit import ToolkitTask
from app.services.trimmer.exceptions import (
    InvalidTimestampError,
    MediaTrimmingError,
)
from app.services.video.ffmpeg import FFmpegVideoProcessor

logger = logging.getLogger(__name__)

_video_processor = FFmpegVideoProcessor()
_cancellation_flags: Dict[str, bool] = {}
_cancellation_lock = threading.Lock()


def request_trim_cancellation(task_id: str) -> None:
    with _cancellation_lock:
        _cancellation_flags[task_id] = True


def is_trim_cancelled(task_id: str) -> bool:
    with _cancellation_lock:
        return _cancellation_flags.get(task_id, False)


def clear_trim_cancellation(task_id: str) -> None:
    with _cancellation_lock:
        _cancellation_flags.pop(task_id, None)


def parse_timestamp(val: Union[str, int, float, None]) -> float:
    """Parse HH:MM:SS.mmm, MM:SS.mmm, SS.mmm, or numeric seconds into float seconds.

    Raises:
        InvalidTimestampError: If syntax is invalid, negative, or unparseable.
    """
    if val is None:
        raise InvalidTimestampError("Timestamp cannot be null.")
    if isinstance(val, (int, float)):
        if val < 0:
            raise InvalidTimestampError(f"Timestamp cannot be negative: {val}")
        return round(float(val), 3)

    s = str(val).strip()
    if not s:
        raise InvalidTimestampError("Timestamp string cannot be empty.")
    if s.startswith("-"):
        raise InvalidTimestampError(f"Timestamp cannot be negative: '{s}'")

    parts = s.split(":")
    try:
        if len(parts) == 3:
            h, m, sec = parts
            seconds = int(h) * 3600 + int(m) * 60 + float(sec)
        elif len(parts) == 2:
            m, sec = parts
            seconds = int(m) * 60 + float(sec)
        elif len(parts) == 1:
            seconds = float(parts[0])
        else:
            raise InvalidTimestampError(f"Invalid timestamp syntax: '{s}'")
    except ValueError as e:
        raise InvalidTimestampError(f"Could not parse timestamp '{s}': {e}") from e

    if seconds < 0:
        raise InvalidTimestampError(f"Timestamp cannot be negative: '{s}'")
    return round(seconds, 3)


def format_timestamp(seconds: float) -> str:
    """Format seconds into standardized HH:MM:SS.mmm representation."""
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


class TrimmerService:
    """Service handling audio and video trimming workflows in Media Toolkit."""

    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe"):
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin

    def get_media_info(self, media_path: Path) -> Dict[str, Any]:
        """Probe media format, duration, audio/video streams, and waveform peaks."""
        if not media_path.exists():
            raise FileNotFoundError(f"Media file not found: {media_path}")
        if media_path.stat().st_size == 0:
            raise MediaTrimmingError("Media file is empty (0 bytes).")

        cmd = [
            self.ffprobe_bin,
            "-v", "error",
            "-show_entries", "stream=index,codec_type,codec_name,width,height,duration:format=duration,size,format_name",
            "-of", "json",
            str(media_path),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except Exception as e:
            raise MediaTrimmingError(f"Failed to execute ffprobe: {e}") from e

        if res.returncode != 0:
            raise MediaTrimmingError(f"Failed to probe media: {res.stderr.strip()}")

        try:
            data = json.loads(res.stdout)
        except json.JSONDecodeError as e:
            raise MediaTrimmingError(f"Invalid ffprobe JSON: {e}") from e

        fmt = data.get("format", {})
        streams = data.get("streams", [])

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        duration = 0.0
        for dur_val in [fmt.get("duration"), video_stream.get("duration") if video_stream else None, audio_stream.get("duration") if audio_stream else None]:
            if dur_val is not None:
                try:
                    duration = float(dur_val)
                    if duration > 0:
                        break
                except (ValueError, TypeError):
                    pass

        has_audio = audio_stream is not None
        has_video = video_stream is not None

        # Extract waveform peaks if audio is present
        peaks: List[float] = []
        if has_audio:
            try:
                peaks = self.extract_waveform_peaks(media_path, num_peaks=150, duration=duration)
            except Exception as e:
                logger.warning("Failed to extract waveform peaks: %s", e)

        return {
            "duration_seconds": round(duration, 3),
            "formatted_duration": format_timestamp(duration),
            "file_size_bytes": media_path.stat().st_size,
            "size_bytes": media_path.stat().st_size,
            "has_video": has_video,
            "has_audio": has_audio,
            "width": int(video_stream["width"]) if video_stream and video_stream.get("width") else None,
            "height": int(video_stream["height"]) if video_stream and video_stream.get("height") else None,
            "video_codec": video_stream.get("codec_name") if video_stream else None,
            "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
            "filename": media_path.name,
            "peaks": peaks,
            "waveform_peaks": peaks,
        }

    def extract_waveform_peaks(self, media_path: Path, num_peaks: int = 150, duration: float = 0.0) -> List[float]:
        """Extract normalized audio waveform peaks (0.0 to 1.0) using fast downsampled PCM,
        aligned to media presentation duration."""
        if not media_path.exists() or media_path.stat().st_size == 0:
            return [0.0] * num_peaks

        cmd = [
            self.ffmpeg_bin,
            "-v", "error",
            "-i", str(media_path),
            "-vn",
            "-af", "aresample=async=1:first_pts=0",
            "-ac", "1",
            "-ar", "8000",
            "-f", "s16le",
            "-",
        ]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            raw, _ = proc.communicate(timeout=15)
        except Exception as e:
            logger.warning("Error running FFmpeg for waveform peaks: %s", e)
            return [0.0] * num_peaks

        if not raw:
            return [0.0] * num_peaks

        # Align with presentation duration if provided
        # 8000 Hz, 16-bit mono = 16,000 bytes per second
        if duration > 0.0:
            expected_bytes = int(duration * 8000) * 2
            if len(raw) < expected_bytes:
                # Pad remaining duration with silence
                raw = raw + b"\x00" * (expected_bytes - len(raw))
            elif len(raw) > expected_bytes:
                # Truncate audio extending past video presentation duration
                raw = raw[:expected_bytes]

        total_samples = len(raw) // 2
        if total_samples == 0:
            return [0.0] * num_peaks

        chunk_size = max(1, total_samples // num_peaks)
        peaks: List[float] = []
        for i in range(num_peaks):
            start = i * chunk_size * 2
            end = min(len(raw), (i + 1) * chunk_size * 2)
            if start >= len(raw):
                peaks.append(0.0)
                continue
            chunk = raw[start:end]
            count = len(chunk) // 2
            if count == 0:
                peaks.append(0.0)
                continue
            samples = struct.unpack(f"<{count}h", chunk)
            max_val = max(abs(s) for s in samples)
            peaks.append(round(max_val / 32768.0, 4))

        # Normalize relative to overall peak so quiet recordings still visualize nicely
        overall_max = max(peaks) if peaks else 0.0
        if 0.0 < overall_max < 0.8:
            scale = 0.85 / overall_max
            peaks = [round(min(1.0, p * scale), 4) for p in peaks]

        return peaks

    def extract_video_thumbnails(self, video_path: Path, count: int = 6) -> List[str]:
        """Generate thumbnail frames as base64 JPEG data URLs across the timeline."""
        if not video_path.exists():
            return []

        info = self.get_media_info(video_path)
        dur = info.get("duration_seconds", 0.0)
        if dur <= 0:
            return []

        count = max(2, min(count, 12))
        interval = max(0.2, dur / (count + 1))
        timestamps = [round(interval * (i + 1), 2) for i in range(count)]

        thumbnails: List[str] = []
        temp_dir = settings.TEMP_DIR / f"thumbs_{uuid.uuid4()}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            for idx, ts in enumerate(timestamps):
                out_img = temp_dir / f"frame_{idx:02d}.jpg"
                cmd = [
                    self.ffmpeg_bin,
                    "-y",
                    "-v", "error",
                    "-ss", str(ts),
                    "-i", str(video_path),
                    "-vframes", "1",
                    "-vf", "scale=160:-1",
                    "-q:v", "4",
                    str(out_img),
                ]
                subprocess.run(cmd, capture_output=True, timeout=5)
                if out_img.exists() and out_img.stat().st_size > 0:
                    b64 = base64.b64encode(out_img.read_bytes()).decode("utf-8")
                    thumbnails.append(f"data:image/jpeg;base64,{b64}")
        except Exception as e:
            logger.warning("Failed thumbnail extraction: %s", e)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        return thumbnails

    def trim_media(
        self,
        task_id: str,
        source_path: Path,
        output_dir: Path,
        tool_type: str,
        start_time_raw: Union[str, float],
        end_time_raw: Union[str, float],
        trim_mode: str = "precise",
        target_format: Optional[str] = None,
        timeout_seconds: int = 120,
    ) -> Dict[str, Any]:
        """Execute video or audio trimming using fast stream copying or precise re-encoding."""
        safe_task_id = sanitize_toolkit_task_id(task_id)
        clear_trim_cancellation(safe_task_id)

        # 1. Parse and validate timestamps
        start_sec = parse_timestamp(start_time_raw)
        end_sec = parse_timestamp(end_time_raw)

        if end_sec <= start_sec:
            raise InvalidTimestampError(
                f"End time ({format_timestamp(end_sec)}) must be greater than start time ({format_timestamp(start_sec)})."
            )

        trim_duration = end_sec - start_sec
        if trim_duration < 0.05:
            raise InvalidTimestampError("Selected trim duration is too short (minimum 0.05 seconds).")

        # 2. Probe source media
        meta = self.get_media_info(source_path)
        source_duration = meta.get("duration_seconds", 0.0)

        if source_duration > 0 and start_sec >= source_duration:
            raise InvalidTimestampError(
                f"Start time ({format_timestamp(start_sec)}) exceeds media duration ({format_timestamp(source_duration)})."
            )

        # Allow small tolerance for container rounding
        if source_duration > 0 and end_sec > source_duration + 0.5:
            raise InvalidTimestampError(
                f"End time ({format_timestamp(end_sec)}) exceeds media duration ({format_timestamp(source_duration)})."
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        trim_mode = trim_mode.lower() if trim_mode in {"fast", "precise"} else "precise"

        # Determine target extension and filename
        source_stem = source_path.stem
        if tool_type == "video_trimmer":
            ext = "mp4"
            target_fmt = "mp4"
        else:
            target_fmt = (target_format or "mp3").lower().lstrip(".")
            if target_fmt not in {"mp3", "wav", "m4a"}:
                target_fmt = "mp3"
            ext = target_fmt

        output_filename = f"trimmed_{source_stem}_{safe_task_id[:8]}.{ext}"
        output_file_path = output_dir / output_filename

        # Build FFmpeg command
        if tool_type == "video_trimmer":
            if trim_mode == "fast":
                # Fast stream copy
                cmd = [
                    self.ffmpeg_bin,
                    "-y",
                    "-v", "error",
                    "-ss", str(start_sec),
                    "-to", str(end_sec),
                    "-i", str(source_path),
                    "-c", "copy",
                    "-avoid_negative_ts", "make_zero",
                    "-map", "0",
                    str(output_file_path),
                ]
            else:
                # Precise re-encode
                has_audio = meta.get("has_audio", False)
                cmd = [
                    self.ffmpeg_bin,
                    "-y",
                    "-v", "error",
                    "-ss", str(start_sec),
                    "-to", str(end_sec),
                    "-i", str(source_path),
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "22",
                    "-pix_fmt", "yuv420p",
                ]
                if has_audio:
                    cmd.extend(["-c:a", "aac", "-b:a", "192k"])
                else:
                    cmd.append("-an")
                cmd.extend(["-movflags", "+faststart", str(output_file_path)])

        else:  # audio_trimmer
            if trim_mode == "fast" and source_path.suffix.lower().lstrip(".") == ext:
                cmd = [
                    self.ffmpeg_bin,
                    "-y",
                    "-v", "error",
                    "-ss", str(start_sec),
                    "-to", str(end_sec),
                    "-i", str(source_path),
                    "-vn",
                    "-c", "copy",
                    "-avoid_negative_ts", "make_zero",
                    str(output_file_path),
                ]
            else:
                # Precise audio encode
                codec_args: List[str]
                if ext == "mp3":
                    codec_args = ["-c:a", "libmp3lame", "-b:a", "192k"]
                elif ext == "wav":
                    codec_args = ["-c:a", "pcm_s16le"]
                elif ext == "m4a":
                    codec_args = ["-c:a", "aac", "-b:a", "192k"]
                else:
                    codec_args = ["-c:a", "libmp3lame", "-b:a", "192k"]

                cmd = [
                    self.ffmpeg_bin,
                    "-y",
                    "-v", "error",
                    "-ss", str(start_sec),
                    "-to", str(end_sec),
                    "-i", str(source_path),
                    "-vn",
                ] + codec_args + [str(output_file_path)]

        # Execute FFmpeg subprocess with timeout and cancellation check
        if is_trim_cancelled(safe_task_id):
            raise MediaTrimmingError("Trimming operation was cancelled before execution.")

        logger.info(
            "Executing %s (%s mode) from %s to %s -> %s",
            tool_type,
            trim_mode,
            format_timestamp(start_sec),
            format_timestamp(end_sec),
            output_filename,
        )

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            output_file_path.unlink(missing_ok=True)
            raise MediaTrimmingError(f"Trimming timed out after {timeout_seconds} seconds.")
        except Exception as e:
            output_file_path.unlink(missing_ok=True)
            raise MediaTrimmingError(f"Subprocess execution error: {e}") from e

        if is_trim_cancelled(safe_task_id):
            output_file_path.unlink(missing_ok=True)
            raise MediaTrimmingError("Trimming operation was cancelled by user.")

        if proc.returncode != 0:
            output_file_path.unlink(missing_ok=True)
            err = stderr.strip() if stderr else "Unknown FFmpeg error"
            raise MediaTrimmingError(f"FFmpeg trimming failed (code {proc.returncode}): {err}")

        if not output_file_path.exists() or output_file_path.stat().st_size == 0:
            output_file_path.unlink(missing_ok=True)
            raise MediaTrimmingError("Output trimmed file was not generated or is empty.")

        try:
            output_file_path.chmod(0o666)
        except OSError:
            pass

        # Probe output media to record exact verified metadata
        out_info = self.get_media_info(output_file_path)
        actual_dur = out_info.get("duration_seconds", round(trim_duration, 3))

        return {
            "output_file_path": str(output_file_path),
            "output_filename": output_filename,
            "output_duration_seconds": actual_dur,
            "output_file_size_bytes": output_file_path.stat().st_size,
            "requested_start_seconds": start_sec,
            "requested_end_seconds": end_sec,
            "requested_duration_seconds": round(trim_duration, 3),
            "formatted_start": format_timestamp(start_sec),
            "formatted_end": format_timestamp(end_sec),
            "formatted_duration": format_timestamp(actual_dur),
            "trim_mode": trim_mode,
            "target_format": ext,
            "output_metadata": out_info,
        }

    def import_to_dubbing(
        self,
        db: Session,
        task_id: str,
        title: Optional[str] = None,
    ) -> Project:
        """Import a completed trimmed video into a new Video Dubbing Studio project."""
        safe_task_id = sanitize_toolkit_task_id(task_id)
        task = db.query(ToolkitTask).filter(ToolkitTask.id == safe_task_id).first()
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Toolkit task '{task_id}' not found.",
            )

        if task.status != "completed" or not task.output_file_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot import task into dubbing studio until trimming is completed.",
            )

        source_video = Path(task.output_file_path)
        if not source_video.exists() or source_video.stat().st_size == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trimmed output file missing from disk.",
            )

        project_title = (title or "").strip()
        if not project_title:
            stem = Path(task.source_filename).stem.replace("trimmed_", "")
            project_title = f"{stem} (Trimmed Dubbing)"

        new_project = Project(
            id=str(uuid.uuid4()),
            title=project_title[:200],
            original_language="en",
            target_language="km",
            pipeline_version="v2.1",
            status=ProjectStatus.CREATED,
        )
        db.add(new_project)
        db.commit()
        db.refresh(new_project)

        try:
            # Copy media to project directory (independent byte copy)
            project_orig_dir = get_project_original_dir(new_project.id)
            project_orig_dir.mkdir(parents=True, exist_ok=True)
            dest_video_path = project_orig_dir / f"original_{new_project.id}.mp4"
            shutil.copy2(source_video, dest_video_path)

            uploads_dir = settings.UPLOADS_DIR
            uploads_dir.mkdir(parents=True, exist_ok=True)
            legacy_upload_path = uploads_dir / f"{new_project.id}.mp4"
            shutil.copy2(source_video, legacy_upload_path)

            probe = _video_processor.get_metadata(dest_video_path)

            temp_dir = settings.TEMP_DIR
            temp_dir.mkdir(parents=True, exist_ok=True)
            audio_temp_path = temp_dir / f"{new_project.id}_audio.wav"

            extracted_dir = get_project_extracted_dir(new_project.id)
            persistent_audio_path = extracted_dir / "extracted_audio.wav"

            if probe.has_audio:
                _video_processor.extract_audio(dest_video_path, audio_temp_path)
                if audio_temp_path.exists():
                    shutil.copy2(audio_temp_path, persistent_audio_path)
                new_project.status = ProjectStatus.AUDIO_EXTRACTED
            else:
                new_project.status = ProjectStatus.UPLOADED

            video = Video(
                project_id=new_project.id,
                filename=f"trimmed_{new_project.id[:8]}.mp4",
                file_path=str(dest_video_path),
                file_size_bytes=dest_video_path.stat().st_size,
                duration_seconds=float(probe.duration_seconds) if getattr(probe, "duration_seconds", None) else None,
                width=int(probe.width) if getattr(probe, "width", None) else None,
                height=int(probe.height) if getattr(probe, "height", None) else None,
                video_codec=str(probe.video_codec) if getattr(probe, "video_codec", None) else None,
                audio_codec=str(probe.audio_codec) if getattr(probe, "audio_codec", None) else None,
                extracted_audio_path=str(persistent_audio_path) if getattr(probe, "has_audio", False) else None,
            )
            db.add(video)
            new_project.original_video_path = str(dest_video_path)
            new_project.updated_at = get_cambodia_now_naive()
            db.commit()
            db.refresh(new_project)

            logger.info("Successfully imported trimmed task %s into Project %s", task_id, new_project.id)
            return new_project

        except Exception as e:
            logger.error("Failed to import trimmed task %s into dubbing: %s", task_id, e)
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to import trimmed media into dubbing project: {e}",
            )


trimmer_service = TrimmerService()
