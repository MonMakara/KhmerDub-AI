import wave
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

from app.services.video.base import VideoProcessor, VideoMetadata, AudioStreamMetadata
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
            "-show_entries", "stream=index,codec_type,codec_name,width,height,duration,sample_rate,channels,bit_rate,channel_layout:format=duration,size,format_name",
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

        # Validate MP4 / QuickTime / MKV / WebM format compatibility
        supported_formats = [
            "mp4", "mov", "m4a", "3gp", "3g2", "mj2", "isom", "iso2", "mp41", "mp42",
            "matroska", "webm", "mkv", "avi"
        ]
        if not any(fmt in format_name for fmt in supported_formats):
            raise InvalidVideoFormatError(
                f"Unsupported format: '{format_name}'. Supported formats: MP4, MOV, MKV, WebM."
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
        audio_sr: Optional[int] = None
        audio_ch: Optional[int] = None
        if audio_stream:
            try:
                audio_sr = int(audio_stream.get("sample_rate")) if audio_stream.get("sample_rate") else None
            except (ValueError, TypeError):
                pass
            try:
                audio_ch = int(audio_stream.get("channels")) if audio_stream.get("channels") else None
            except (ValueError, TypeError):
                pass

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
            audio_sample_rate=audio_sr,
            audio_channels=audio_ch,
        )

    def get_audio_metadata(self, audio_or_video_path: Path) -> AudioStreamMetadata:
        """Extract detailed audio stream metadata using ffprobe."""
        if not audio_or_video_path.exists():
            raise FileNotFoundError(f"Media file does not exist: {audio_or_video_path}")
        if audio_or_video_path.stat().st_size == 0:
            raise CorruptedVideoError("Media file is empty (0 bytes)")

        cmd = [
            self.ffprobe_bin,
            "-v", "error",
            "-show_entries", "stream=codec_type,codec_name,duration,sample_rate,channels,bit_rate,channel_layout:format=duration,size,bit_rate",
            "-of", "json",
            str(audio_or_video_path),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except Exception as e:
            raise VideoProcessingError(f"Error executing ffprobe: {e}") from e

        if res.returncode != 0:
            err = res.stderr.strip() or "Unknown error"
            raise CorruptedVideoError(f"Unable to parse media file or file is corrupted: {err}")

        try:
            data = json.loads(res.stdout)
        except json.JSONDecodeError as e:
            raise CorruptedVideoError(f"ffprobe returned invalid JSON: {e}") from e

        audio_stream = None
        for s in data.get("streams", []):
            if s.get("codec_type") == "audio":
                audio_stream = s
                break

        if not audio_stream:
            raise NoAudioTrackError("Media file does not contain an audio track.")

        fmt_info = data.get("format", {})

        # Resolve duration
        duration_s = 0.0
        for dur_val in [fmt_info.get("duration"), audio_stream.get("duration")]:
            if dur_val is not None:
                try:
                    duration_s = float(dur_val)
                    if duration_s > 0.0:
                        break
                except (ValueError, TypeError):
                    pass

        # Resolve sample rate and channels
        sr = 44100
        ch = 2
        try:
            if audio_stream.get("sample_rate"):
                sr = int(audio_stream["sample_rate"])
        except (ValueError, TypeError):
            pass

        try:
            if audio_stream.get("channels"):
                ch = int(audio_stream["channels"])
        except (ValueError, TypeError):
            pass

        # Resolve bit rate
        bit_rate = None
        for br_val in [audio_stream.get("bit_rate"), fmt_info.get("bit_rate")]:
            if br_val is not None:
                try:
                    bit_rate = int(br_val)
                    if bit_rate > 0:
                        break
                except (ValueError, TypeError):
                    pass

        codec_name = audio_stream.get("codec_name", "unknown")
        channel_layout = audio_stream.get("channel_layout")

        return AudioStreamMetadata(
            duration_seconds=round(duration_s, 2),
            codec_name=codec_name,
            sample_rate=sr,
            channels=ch,
            bit_rate=bit_rate,
            channel_layout=channel_layout,
        )

    def extract_audio_format(
        self, video_path: Path, output_audio_path: Path, target_format: str = "mp3"
    ) -> Path:
        """Extract audio track from video in specified format (mp3, wav, m4a) with optimal remuxing/transcoding.

        - Preserves full audio duration.
        - If source audio format matches requested format without transcoding need (e.g. AAC in MP4 -> M4A),
          remuxes via stream copy (-c:a copy) to preserve original fidelity and ensure instantaneous execution.
        - Otherwise, applies high-quality encoding defaults:
          - MP3: libmp3lame 192k CBR/VBR high fidelity
          - WAV: 16-bit PCM uncompressed studio WAV
          - M4A: AAC 192k standard MP4 audio
        """
        metadata = self.get_metadata(video_path)
        if not metadata.has_audio:
            raise NoAudioTrackError("Uploaded video does not contain an audio track.")

        clean_format = target_format.lower().lstrip(".")
        if clean_format not in ["mp3", "wav", "m4a"]:
            raise ValueError(f"Unsupported target format: '{target_format}'. Supported formats are: mp3, wav, m4a.")

        output_audio_path.parent.mkdir(parents=True, exist_ok=True)

        src_codec = (metadata.audio_codec or "").lower()

        # Build optimal FFmpeg command
        if clean_format == "m4a":
            if src_codec in ["aac", "mp4a"]:
                # Stream copy: direct lossless container remuxing
                logger.info("Source audio is already AAC (%s). Remuxing to M4A without lossy re-encoding.", src_codec)
                cmd = [
                    self.ffmpeg_bin,
                    "-y",
                    "-i", str(video_path),
                    "-vn",
                    "-c:a", "copy",
                    str(output_audio_path),
                ]
            else:
                cmd = [
                    self.ffmpeg_bin,
                    "-y",
                    "-i", str(video_path),
                    "-vn",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    str(output_audio_path),
                ]
        elif clean_format == "mp3":
            if src_codec == "mp3":
                # Stream copy: direct lossless copy
                logger.info("Source audio is already MP3. Copying without re-encoding.")
                cmd = [
                    self.ffmpeg_bin,
                    "-y",
                    "-i", str(video_path),
                    "-vn",
                    "-c:a", "copy",
                    str(output_audio_path),
                ]
            else:
                cmd = [
                    self.ffmpeg_bin,
                    "-y",
                    "-i", str(video_path),
                    "-vn",
                    "-c:a", "libmp3lame",
                    "-b:a", "192k",
                    str(output_audio_path),
                ]
        elif clean_format == "wav":
            if src_codec in ["pcm_s16le", "pcm_s24le", "pcm_s32le"]:
                cmd = [
                    self.ffmpeg_bin,
                    "-y",
                    "-i", str(video_path),
                    "-vn",
                    "-c:a", "copy",
                    str(output_audio_path),
                ]
            else:
                cmd = [
                    self.ffmpeg_bin,
                    "-y",
                    "-i", str(video_path),
                    "-vn",
                    "-c:a", "pcm_s16le",
                    str(output_audio_path),
                ]
        else:
            raise ValueError(f"Unsupported format: {clean_format}")

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except Exception as e:
            logger.error("Failed to execute ffmpeg audio extraction: %s", e)
            raise VideoProcessingError(f"Error executing ffmpeg: {e}") from e

        if res.returncode != 0:
            err = res.stderr.strip() or "Unknown error"
            logger.error("FFmpeg audio extraction failed (returncode %d): %s", res.returncode, err)
            raise VideoProcessingError(f"FFmpeg audio extraction failed: {err}")

        if not output_audio_path.exists() or output_audio_path.stat().st_size == 0:
            raise VideoProcessingError("Extracted audio file is missing or zero bytes.")

        try:
            output_audio_path.chmod(0o666)
        except OSError:
            pass

        logger.info(
            "Successfully extracted %s audio from %s -> %s (%d bytes)",
            clean_format.upper(),
            video_path.name,
            output_audio_path.name,
            output_audio_path.stat().st_size,
        )
        return output_audio_path

    def get_audio_duration(self, audio_path: Path) -> float:
        """Measure audio duration in seconds using ffprobe."""
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            return 0.0

        if audio_path.suffix.lower() == ".wav":
            try:
                with wave.open(str(audio_path), "rb") as audio:
                    return audio.getnframes() / audio.getframerate()
            except (wave.Error, EOFError):
                pass
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
                return float(res.stdout.strip())
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

    def prepare_audio_for_transcription(
        self, input_media_path: Path, output_wav_path: Path
    ) -> Path:
        """Extract or convert any audio or video file to 16kHz mono 16-bit PCM WAV for Whisper.

        - Handles MP4, MOV, MKV, WebM videos by extracting and resampling the audio track.
        - Handles WAV, MP3, M4A, FLAC, OGG, AAC standalone audio files by converting to standard 16kHz mono WAV.
        - Verifies that audio track is present and non-empty.
        """
        if not input_media_path.exists():
            raise FileNotFoundError(f"Media file does not exist: {input_media_path}")

        if input_media_path.stat().st_size == 0:
            raise CorruptedVideoError("Media file is empty (0 bytes)")

        # Verify that file has a valid audio stream
        audio_meta = self.get_audio_metadata(input_media_path)
        if not audio_meta:
            raise NoAudioTrackError("Media file does not contain an audio track.")

        output_wav_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-i", str(input_media_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ac", "1",
            "-ar", "16000",
            str(output_wav_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as e:
            logger.error("Failed to run ffmpeg audio preparation: %s", e)
            raise VideoProcessingError(f"Error executing ffmpeg audio preparation: {e}") from e

        if result.returncode != 0:
            err = result.stderr.strip() or "Unknown error"
            logger.error("FFmpeg audio preparation failed: %s", err)
            raise VideoProcessingError(f"FFmpeg audio preparation failed: {err}")

        if not output_wav_path.exists() or output_wav_path.stat().st_size == 0:
            raise VideoProcessingError("Prepared WAV audio file is missing or zero bytes.")

        try:
            output_wav_path.chmod(0o666)
        except OSError:
            pass

        return output_wav_path

