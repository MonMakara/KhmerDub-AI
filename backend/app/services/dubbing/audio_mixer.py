import json
import logging
import math
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any

from app.services.video.exceptions import VideoProcessingError

logger = logging.getLogger(__name__)


class DuckingPreset(str, Enum):
    LIGHT = "light"        # ~6 dB ducking (ratio 4, gentle background music)
    BALANCED = "balanced"  # ~12 dB ducking (ratio 8, standard broadcast dialogue)
    STRONG = "strong"      # ~18 dB ducking (ratio 14, loud soundtracks / action)
    MUTE = "mute"          # ~25+ dB ducking (ratio 30, cuts background during speech)


PRESET_SETTINGS: Dict[str, Dict[str, Any]] = {
    DuckingPreset.LIGHT: {
        "threshold": 0.04,
        "ratio": 4.0,
        "attack_ms": 25,
        "release_ms": 200,
    },
    DuckingPreset.BALANCED: {
        "threshold": 0.03,
        "ratio": 8.0,
        "attack_ms": 20,
        "release_ms": 250,
    },
    DuckingPreset.STRONG: {
        "threshold": 0.02,
        "ratio": 14.0,
        "attack_ms": 15,
        "release_ms": 300,
    },
    DuckingPreset.MUTE: {
        "threshold": 0.01,
        "ratio": 30.0,
        "attack_ms": 10,
        "release_ms": 300,
    },
}


@dataclass
class DuckingConfig:
    preset: str = DuckingPreset.BALANCED
    bgm_volume: float = 0.35              # 0.0 to 1.5
    speech_volume: float = 1.20           # 0.5 to 2.0
    attenuate_center_vocals: bool = True  # Suppress center-channel dialogue on stereo tracks
    attack_ms: Optional[int] = None      # Custom override
    release_ms: Optional[int] = None     # Custom override
    threshold: Optional[float] = None    # Custom override
    ratio: Optional[float] = None        # Custom override


class AudioDuckingMixer:
    """Combines background video audio/music with a synchronized speech timeline track
    using studio-grade FFmpeg sidechain compression and optional mid-channel vocal attenuation.
    """

    def __init__(
        self,
        ffmpeg_bin: str = "ffmpeg",
        ffprobe_bin: str = "ffprobe",
    ):
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin

    def probe_audio(self, audio_path: Path) -> Dict[str, Any]:
        """Probe audio file format, stream count, channel layout, and duration."""
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        cmd = [
            self.ffprobe_bin,
            "-v", "error",
            "-show_entries", "stream=codec_type,channels,sample_rate,duration:format=duration",
            "-of", "json",
            str(audio_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise VideoProcessingError(f"FFprobe failed to inspect {audio_path.name}: {res.stderr}")

        try:
            data = json.loads(res.stdout)
        except json.JSONDecodeError as exc:
            raise VideoProcessingError(f"Invalid JSON from ffprobe: {exc}") from exc

        streams = data.get("streams", [])
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        format_info = data.get("format", {})

        duration = 0.0
        if audio_stream and audio_stream.get("duration"):
            try:
                duration = float(audio_stream["duration"])
            except (ValueError, TypeError):
                duration = 0.0
        if duration <= 0.0 and format_info.get("duration"):
            try:
                duration = float(format_info["duration"])
            except (ValueError, TypeError):
                duration = 0.0

        channels = 1
        if audio_stream and audio_stream.get("channels"):
            try:
                channels = int(audio_stream["channels"])
            except (ValueError, TypeError):
                channels = 1

        sample_rate = 48000
        if audio_stream and audio_stream.get("sample_rate"):
            try:
                sample_rate = int(audio_stream["sample_rate"])
            except (ValueError, TypeError):
                sample_rate = 48000

        return {
            "duration": round(duration, 3),
            "channels": channels,
            "sample_rate": sample_rate,
        }

    def mix_and_duck(
        self,
        background_audio_path: Path,
        speech_audio_path: Path,
        output_path: Path,
        expected_duration: Optional[float] = None,
        config: Optional[DuckingConfig] = None,
        tolerance_seconds: float = 0.20,
    ) -> Path:
        """Mix background audio and speech timeline with sidechain ducking.

        When speech is active on speech_audio_path, the background volume is dynamically
        ducked. When speech pauses, background audio swells back up smoothly.
        """
        if not background_audio_path.exists():
            raise FileNotFoundError(f"Background audio file not found: {background_audio_path}")
        if not speech_audio_path.exists():
            raise FileNotFoundError(f"Speech audio timeline not found: {speech_audio_path}")

        cfg = config or DuckingConfig()
        preset_key = cfg.preset if cfg.preset in PRESET_SETTINGS else DuckingPreset.BALANCED
        params = PRESET_SETTINGS[preset_key]

        threshold = cfg.threshold if cfg.threshold is not None else params["threshold"]
        ratio = cfg.ratio if cfg.ratio is not None else params["ratio"]
        attack = cfg.attack_ms if cfg.attack_ms is not None else params["attack_ms"]
        release = cfg.release_ms if cfg.release_ms is not None else params["release_ms"]
        bgm_vol = max(0.0, min(2.0, float(cfg.bgm_volume)))
        speech_vol = max(0.1, min(2.0, float(cfg.speech_volume)))

        bg_info = self.probe_audio(background_audio_path)
        speech_info = self.probe_audio(speech_audio_path)

        target_duration = expected_duration
        if target_duration is None or target_duration <= 0.0:
            target_duration = max(bg_info["duration"], speech_info["duration"])

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_output = output_path.with_suffix(".tmp.wav")

        # Build FFmpeg audio filter complex
        # 1. Background branch
        if cfg.attenuate_center_vocals and bg_info["channels"] >= 2:
            # Attenuate center channel (mid) by 85% to suppress original vocals, keeping stereo music/SFX
            bg_filter = (
                f"[0:a]aformat=channel_layouts=stereo,stereotools=mlev=0.15:slev=1.1,"
                f"volume={bgm_vol:.3f}[bg_prep];"
            )
        else:
            bg_filter = (
                f"[0:a]aformat=channel_layouts=stereo,volume={bgm_vol:.3f}[bg_prep];"
            )

        # 2. Speech branch (ensure stereo format to match background for sidechain & mix)
        speech_filter = (
            f"[1:a]aformat=channel_layouts=stereo,volume={speech_vol:.3f}[speech_prep];"
        )

        # 3. Sidechain compression ducking
        sc_filter = (
            f"[bg_prep][speech_prep]sidechaincompress="
            f"threshold={threshold:.3f}:ratio={ratio:.1f}:attack={attack}:release={release}:"
            f"makeup=1:link=average[ducked];"
        )

        # 4. Padding to ensure exact timeline duration
        pad_filter = f"[ducked]apad=whole_dur={target_duration:.3f}[ducked_pad];"

        # 5. Final mix with broadcast-grade peak limiter to prevent clipping
        mix_filter = (
            f"[ducked_pad][speech_prep]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[raw_mixed];"
            f"[raw_mixed]alimiter=limit=0.95:attack=5:release=50:asc=1[mixed]"
        )

        filter_complex = f"{bg_filter}{speech_filter}{sc_filter}{pad_filter}{mix_filter}"

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-i", str(background_audio_path),
            "-i", str(speech_audio_path),
            "-filter_complex", filter_complex,
            "-map", "[mixed]",
            "-ar", "48000",
            "-c:a", "pcm_s16le",
            str(temp_output),
        ]

        logger.info(
            "Executing audio ducking mix (preset=%s, bgm_vol=%.2f, target_dur=%.2fs)...",
            preset_key,
            bgm_vol,
            target_duration,
        )
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            if temp_output.exists():
                temp_output.unlink()
            raise VideoProcessingError(f"FFmpeg failed during audio ducking mix: {res.stderr}")

        # Verify output duration and integrity
        out_info = self.probe_audio(temp_output)
        actual_dur = out_info["duration"]
        if target_duration > 0.0 and abs(actual_dur - target_duration) > tolerance_seconds:
            if temp_output.exists():
                temp_output.unlink()
            raise VideoProcessingError(
                f"Mixed audio duration mismatch: produced {actual_dur:.3f}s, expected {target_duration:.3f}s "
                f"(difference exceeds {tolerance_seconds:.2f}s tolerance)."
            )

        # Move to destination atomically
        temp_output.replace(output_path)
        logger.info(
            "Successfully mixed & ducked audio: %s (duration=%.2fs, channels=%d)",
            output_path.name,
            actual_dur,
            out_info["channels"],
        )
        return output_path
