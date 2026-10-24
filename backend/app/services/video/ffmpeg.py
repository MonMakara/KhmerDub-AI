import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

from app.services.video.base import VideoProcessor, VideoMetadata
from app.services.video.exceptions import (
    VideoProcessingError,
    CorruptedVideoError,
    InvalidVideoFormatError,
    NoAudioTrackError,
)

logger = logging.getLogger(__name__)


class FFmpegVideoProcessor(VideoProcessor):
    """Concrete implementation of VideoProcessor using system FFmpeg and FFprobe."""

    def __init__(self, ffprobe_bin: str = "ffprobe", ffmpeg_bin: str = "ffmpeg"):
        self.ffprobe_bin = ffprobe_bin
        self.ffmpeg_bin = ffmpeg_bin

    def get_metadata(self, video_path: Path) -> VideoMetadata:
        """Extract media metadata using ffprobe and validate container format."""
        if not video_path.exists():
            raise FileNotFoundError(f"Video file does not exist: {video_path}")

        if video_path.stat().st_size == 0:
            raise CorruptedVideoError("Video file is empty (0 bytes)")

        cmd = [
            self.ffprobe_bin,
            "-v", "error",
            "-show_entries", "stream=index,codec_type,codec_name,width,height,duration:format=duration,size,format_name",
            "-of", "json",
            str(video_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as e:
            logger.error("Failed to run ffprobe subprocess: %s", e)
            raise VideoProcessingError(f"Error executing ffprobe: {e}") from e

        if result.returncode != 0:
            err = result.stderr.strip() or "Unknown error"
            logger.warning("ffprobe failed with exit code %s: %s", result.returncode, err)
            raise CorruptedVideoError(f"Unable to parse video format or file is corrupted: {err}")

        try:
            probe_data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise CorruptedVideoError(f"ffprobe returned invalid JSON: {e}") from e

        format_info = probe_data.get("format", {})
        format_name = format_info.get("format_name", "").lower()

        # Validate MP4 / QuickTime format compatibility
        supported_formats = ["mp4", "mov", "m4a", "3gp", "3g2", "mj2", "isom", "iso2", "mp41", "mp42"]
        if not any(fmt in format_name for fmt in supported_formats):
            raise InvalidVideoFormatError(
                f"Unsupported format: '{format_name}'. Only MP4 videos are supported."
            )

        streams = probe_data.get("streams", [])

        video_stream: Optional[dict] = None
        audio_stream: Optional[dict] = None

        for stream in streams:
            codec_type = stream.get("codec_type")
            if codec_type == "video" and video_stream is None:
                video_stream = stream
            elif codec_type == "audio" and audio_stream is None:
                audio_stream = stream

        if not video_stream:
            raise CorruptedVideoError("No valid video stream found in the uploaded file.")

        width = video_stream.get("width")
        height = video_stream.get("height")
        video_codec = video_stream.get("codec_name")

        has_audio = audio_stream is not None
        audio_codec = audio_stream.get("codec_name") if audio_stream else None

        # Resolve duration
        duration_seconds = 0.0
        if "duration" in format_info:
            try:
                duration_seconds = float(format_info["duration"])
            except (ValueError, TypeError):
                pass

        if duration_seconds <= 0.0 and video_stream.get("duration"):
            try:
                duration_seconds = float(video_stream["duration"])
            except (ValueError, TypeError):
                pass

        return VideoMetadata(
            duration_seconds=round(duration_seconds, 2),
            width=int(width) if width else 0,
            height=int(height) if height else 0,
            has_audio=has_audio,
            video_codec=video_codec,
            audio_codec=audio_codec,
        )

    def get_audio_duration(self, audio_path: Path) -> float:
        """Measure audio duration in seconds using ffprobe."""
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            return 0.0

        cmd = [
            self.ffprobe_bin,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode == 0 and res.stdout.strip():
                return round(float(res.stdout.strip()), 2)
        except Exception as e:
            logger.warning("Failed to probe audio duration for %s: %s", audio_path, e)
        return 0.0

    def extract_audio(self, video_path: Path, output_audio_path: Path) -> Path:
        """Extract audio track from video as 16kHz mono 16-bit PCM WAV."""
        metadata = self.get_metadata(video_path)
        if not metadata.has_audio:
            raise NoAudioTrackError("Uploaded video does not contain an audio track.")

        output_audio_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ac", "1",
            "-ar", "16000",
            str(output_audio_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as e:
            logger.error("Failed to run ffmpeg subprocess: %s", e)
            raise VideoProcessingError(f"Error executing ffmpeg: {e}") from e

        if result.returncode != 0:
            err = result.stderr.strip() or "Unknown error"
            logger.error("FFmpeg audio extraction failed: %s", err)
            raise VideoProcessingError(f"FFmpeg extraction failed: {err}")

        if not output_audio_path.exists() or output_audio_path.stat().st_size == 0:
            raise VideoProcessingError("Extracted audio file is missing or zero bytes.")

        return output_audio_path

    def merge_audio_video(
        self, video_path: Path, audio_path: Path, output_video_path: Path
    ) -> Path:
        """Replace original audio track with synchronized dubbed audio."""
        output_video_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            str(output_video_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as e:
            raise VideoProcessingError(f"Error executing ffmpeg remux: {e}") from e

        if result.returncode != 0:
            err = result.stderr.strip() or "Unknown error"
            raise VideoProcessingError(f"FFmpeg video merge failed: {err}")

        return output_video_path
