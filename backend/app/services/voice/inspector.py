import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from app.services.voice.exceptions import (
    AudioValidationError,
    AudioTooShortError,
    AudioTooLongError,
    AudioSilentError,
    AudioCorruptedError,
)

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg"}
MIN_AUDIO_DURATION_SECONDS = 3.0
MAX_AUDIO_DURATION_SECONDS = 120.0
TARGET_SAMPLE_RATE = 48000
SILENCE_THRESHOLD_DB = -55.0


class AudioQualityInspector:
    """Service to inspect, validate, and normalize reference voice recordings."""

    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe"):
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin

    def validate_file_extension(self, filename: str) -> str:
        """Validate that the file extension is supported."""
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise AudioValidationError(
                f"Unsupported audio format '{suffix}'. Supported formats: {supported}"
            )
        return suffix

    def inspect_audio(self, audio_path: Path) -> Dict[str, Any]:
        """Inspect audio stream properties using ffprobe."""
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file does not exist: {audio_path}")

        if audio_path.stat().st_size == 0:
            raise AudioCorruptedError("Audio file is empty (0 bytes).")

        cmd = [
            self.ffprobe_bin,
            "-v", "error",
            "-show_entries", "stream=codec_type,codec_name,sample_rate,channels,duration:format=duration,size",
            "-of", "json",
            str(audio_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except Exception as e:
            logger.error("Failed to execute ffprobe: %s", e)
            raise AudioCorruptedError(f"Error executing ffprobe: {e}") from e

        if result.returncode != 0:
            err = result.stderr.strip() or "Unknown audio decode error"
            logger.warning("ffprobe inspection failed: %s", err)
            raise AudioCorruptedError(f"Unable to decode audio: {err}")

        try:
            probe = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise AudioCorruptedError(f"ffprobe returned invalid JSON: {e}") from e

        streams = probe.get("streams", [])
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        if not audio_stream:
            raise AudioCorruptedError("No valid audio stream found in the uploaded file.")

        # Determine duration (format duration takes precedence or audio stream duration)
        raw_duration = (
            probe.get("format", {}).get("duration")
            or audio_stream.get("duration")
        )
        if not raw_duration:
            raise AudioCorruptedError("Could not determine audio duration.")

        try:
            duration = float(raw_duration)
        except (ValueError, TypeError) as e:
            raise AudioCorruptedError(f"Invalid duration value: {raw_duration}") from e

        # Check duration bounds
        if duration < MIN_AUDIO_DURATION_SECONDS:
            raise AudioTooShortError(
                f"Reference audio is too short ({duration:.1f}s). "
                f"Minimum required duration is {MIN_AUDIO_DURATION_SECONDS:.0f} seconds."
            )

        if duration > MAX_AUDIO_DURATION_SECONDS:
            raise AudioTooLongError(
                f"Reference audio exceeds maximum allowable duration ({duration:.1f}s). "
                f"Maximum allowed is {MAX_AUDIO_DURATION_SECONDS:.0f} seconds."
            )

        sample_rate = int(audio_stream.get("sample_rate", 0))
        channels = int(audio_stream.get("channels", 1))

        # Inspect volume / silence level
        volume_info = self._detect_volume_levels(audio_path)
        mean_volume = volume_info.get("mean_volume")
        max_volume = volume_info.get("max_volume")

        if mean_volume is not None and max_volume is not None:
            if mean_volume < SILENCE_THRESHOLD_DB and max_volume < -45.0:
                raise AudioSilentError(
                    "The uploaded audio recording appears to be silent or has virtually no speech signal. "
                    "Please upload a clear, audible reference recording."
                )

        return {
            "duration": round(duration, 3),
            "sample_rate": sample_rate,
            "channels": channels,
            "codec": audio_stream.get("codec_name"),
            "file_size": audio_path.stat().st_size,
            "mean_volume": mean_volume,
            "max_volume": max_volume,
        }

    def _detect_volume_levels(self, audio_path: Path) -> Dict[str, Optional[float]]:
        """Run ffmpeg volumedetect filter to determine mean and peak volume."""
        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-i", str(audio_path),
            "-af", "volumedetect",
            "-vn",
            "-sn",
            "-f", "null",
            "/dev/null",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            output = res.stderr
            mean_match = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", output)
            max_match = re.search(r"max_volume:\s*(-?[\d.]+)\s*dB", output)
            return {
                "mean_volume": float(mean_match.group(1)) if mean_match else None,
                "max_volume": float(max_match.group(1)) if max_match else None,
            }
        except Exception as e:
            logger.warning("Failed to run volume detection: %s", e)
            return {"mean_volume": None, "max_volume": None}

    def normalize_reference_audio(
        self,
        source_path: Path,
        target_path: Path,
        target_sample_rate: int = TARGET_SAMPLE_RATE,
    ) -> Dict[str, Any]:
        """
        Normalize audio into high-fidelity 48kHz Mono 16-bit PCM WAV.
        Also inspects the source audio beforehand to ensure duration and quality standards.
        """
        # Validate source properties first
        initial_meta = self.inspect_audio(source_path)

        target_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-i", str(source_path),
            "-vn",
            "-sn",
            "-ar", str(target_sample_rate),
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(target_path),
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except Exception as e:
            logger.error("Failed to run ffmpeg normalization: %s", e)
            raise AudioValidationError(f"FFmpeg normalization failed: {e}") from e

        if res.returncode != 0:
            err = res.stderr.strip() or "Unknown conversion error"
            logger.warning("FFmpeg audio conversion failed: %s", err)
            raise AudioValidationError(f"Failed to normalize audio to 48kHz WAV: {err}")

        if not target_path.exists() or target_path.stat().st_size == 0:
            raise AudioValidationError("Normalized audio file was not created or is empty.")

        # Re-inspect normalized output for final metadata
        final_meta = self.inspect_audio(target_path)
        final_meta["original_sample_rate"] = initial_meta["sample_rate"]
        final_meta["original_channels"] = initial_meta["channels"]

        return final_meta
