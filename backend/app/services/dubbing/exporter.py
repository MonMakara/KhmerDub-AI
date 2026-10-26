import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.services.video.ffmpeg import FFmpegVideoProcessor
from app.services.video.exceptions import VideoProcessingError

logger = logging.getLogger(__name__)


@dataclass
class ExportResult:
    video_path: Path
    duration_seconds: float
    file_size_bytes: int
    video_codec: str
    audio_codec: str


class VideoExportService:
    """Combines original video stream with the synchronized Khmer audio timeline into a final MP4."""

    def __init__(
        self,
        ffmpeg_bin: str = "ffmpeg",
        ffprobe_bin: str = "ffprobe",
        video_processor: Optional[FFmpegVideoProcessor] = None,
    ):
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin
        self.video_processor = video_processor or FFmpegVideoProcessor()

    def verify_exported_video(
        self,
        video_path: Path,
        expected_duration: Optional[float] = None,
        tolerance_seconds: float = 0.15,
        original_video_path: Optional[Path] = None,
    ) -> ExportResult:
        """Inspect and verify that exported MP4 contains valid video and audio streams,
        and optionally verify duration against expected duration within tolerance.
        """
        if not video_path.exists() or video_path.stat().st_size == 0:
            raise VideoProcessingError(f"Exported video missing or empty at {video_path}")

        cmd = [
            self.ffprobe_bin,
            "-v", "error",
            "-show_entries", "stream=index,codec_type,codec_name,duration:format=duration,size",
            "-of", "json",
            str(video_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise VideoProcessingError(f"FFprobe failed to inspect exported video: {res.stderr}")

        try:
            data = json.loads(res.stdout)
        except json.JSONDecodeError as e:
            raise VideoProcessingError(f"Invalid JSON from ffprobe: {e}") from e

        streams = data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        if not video_stream:
            raise VideoProcessingError("Exported MP4 is missing a video stream.")
        if not audio_stream:
            raise VideoProcessingError("Exported MP4 is missing an audio stream.")

        format_info = data.get("format", {})
        try:
            duration = float(format_info.get("duration", 0.0))
        except (ValueError, TypeError):
            duration = 0.0

        try:
            video_dur = float(video_stream.get("duration", 0.0))
        except (ValueError, TypeError):
            video_dur = 0.0

        try:
            audio_dur = float(audio_stream.get("duration", 0.0))
        except (ValueError, TypeError):
            audio_dur = 0.0

        if duration <= 0.0:
            duration = video_dur if video_dur > 0.0 else audio_dur

        # Strict duration validation against expected target video duration
        if expected_duration is not None and expected_duration > 0.0:
            diff_audio = abs(audio_dur - expected_duration) if audio_dur > 0.0 else 0.0
            diff_video = abs(video_dur - expected_duration) if video_dur > 0.0 else 0.0

            if diff_audio > tolerance_seconds:
                raise VideoProcessingError(
                    f"Exported audio duration mismatch: audio stream is {audio_dur:.3f}s, expected {expected_duration:.3f}s "
                    f"(difference: {diff_audio:.3f}s exceeds {tolerance_seconds:.2f}s tolerance)."
                )

            video_matches = (diff_video <= tolerance_seconds)
            # If video track length differs slightly from container expected duration,
            # verify against source video's actual video track duration to ensure 100% fidelity
            if not video_matches and original_video_path and original_video_path.exists():
                try:
                    cmd_orig = [
                        self.ffprobe_bin,
                        "-v", "error",
                        "-show_entries", "stream=codec_type,duration",
                        "-of", "json",
                        str(original_video_path),
                    ]
                    res_orig = subprocess.run(cmd_orig, capture_output=True, text=True, check=False)
                    if res_orig.returncode == 0:
                        data_orig = json.loads(res_orig.stdout)
                        for s in data_orig.get("streams", []):
                            if s.get("codec_type") == "video":
                                orig_vdur = float(s.get("duration", 0.0))
                                if orig_vdur > 0.0 and abs(video_dur - orig_vdur) <= tolerance_seconds:
                                    video_matches = True
                                    break
                except Exception:
                    pass

            if not video_matches:
                raise VideoProcessingError(
                    f"Exported video duration mismatch: video stream is {video_dur:.3f}s, expected {expected_duration:.3f}s "
                    f"(difference: {diff_video:.3f}s exceeds {tolerance_seconds:.2f}s tolerance)."
                )

        file_size = video_path.stat().st_size

        return ExportResult(
            video_path=video_path,
            duration_seconds=round(duration, 2),
            file_size_bytes=file_size,
            video_codec=video_stream.get("codec_name", "unknown"),
            audio_codec=audio_stream.get("codec_name", "unknown"),
        )

    def export(
        self,
        video_path: Path,
        audio_timeline_path: Path,
        output_video_path: Path,
        expected_duration: Optional[float] = None,
        tolerance_seconds: float = 0.15,
    ) -> ExportResult:
        """Remux original video and new Khmer audio timeline into MP4 with atomic publishing."""
        if not video_path.exists():
            raise FileNotFoundError(f"Original video not found: {video_path}")
        if not audio_timeline_path.exists() or audio_timeline_path.stat().st_size == 0:
            raise FileNotFoundError(f"Audio timeline missing or empty: {audio_timeline_path}")

        output_video_path.parent.mkdir(parents=True, exist_ok=True)
        temp_output_path = output_video_path.with_suffix(".tmp.mp4")

        # Attempt fast remux first with stream copy (-c:v copy)
        cmd_copy = [
            self.ffmpeg_bin,
            "-y",
            "-i", str(video_path),
            "-i", str(audio_timeline_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(temp_output_path),
        ]

        logger.info("Executing video remux via stream copy...")
        res = subprocess.run(cmd_copy, capture_output=True, text=True, check=False)

        # Fallback to H.264 encode if stream copy fails
        if res.returncode != 0:
            logger.warning("Stream copy failed (%s). Retrying with H.264 transcode fallback...", res.stderr.strip())
            cmd_transcode = [
                self.ffmpeg_bin,
                "-y",
                "-i", str(video_path),
                "-i", str(audio_timeline_path),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                str(temp_output_path),
            ]
            res_tc = subprocess.run(cmd_transcode, capture_output=True, text=True, check=False)
            if res_tc.returncode != 0:
                if temp_output_path.exists():
                    temp_output_path.unlink()
                raise VideoProcessingError(f"Video export failed in transcode fallback: {res_tc.stderr}")

        # Verify exported video before publishing
        try:
            result = self.verify_exported_video(
                temp_output_path,
                expected_duration=expected_duration,
                tolerance_seconds=tolerance_seconds,
                original_video_path=video_path,
            )
            # Atomically publish to final destination
            shutil.move(str(temp_output_path), str(output_video_path))
            result.video_path = output_video_path
            logger.info("Successfully exported dubbed MP4: %s (%.2fs)", output_video_path.name, result.duration_seconds)
            return result
        except Exception as e:
            if temp_output_path.exists():
                temp_output_path.unlink()
            raise
