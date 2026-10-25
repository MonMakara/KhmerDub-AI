from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class VideoMetadata:
    duration_seconds: float
    width: int
    height: int
    has_audio: bool
    audio_codec: str | None = None
    video_codec: str | None = None
    audio_sample_rate: int | None = None
    audio_channels: int | None = None


@dataclass
class AudioStreamMetadata:
    duration_seconds: float
    codec_name: str
    sample_rate: int
    channels: int
    bit_rate: Optional[int] = None
    channel_layout: Optional[str] = None


class VideoProcessor(ABC):
    """Abstract interface for video/audio manipulation via FFmpeg."""

    @abstractmethod
    def get_metadata(self, video_path: Path) -> VideoMetadata:
        """Extract media metadata using ffprobe."""
        pass

    @abstractmethod
    def extract_audio(self, video_path: Path, output_audio_path: Path) -> Path:
        """Extract audio track from video as standard 16kHz mono WAV."""
        pass

    @abstractmethod
    def extract_audio_format(
        self, video_path: Path, output_audio_path: Path, target_format: str = "mp3"
    ) -> Path:
        """Extract audio track from video in specified format (mp3, wav, m4a) with optimal remuxing/transcoding."""
        pass

    @abstractmethod
    def get_audio_metadata(self, audio_or_video_path: Path) -> AudioStreamMetadata:
        """Extract detailed audio stream metadata using ffprobe."""
        pass

    @abstractmethod
    def get_audio_duration(self, audio_path: Path) -> float:
        """Measure audio duration in seconds using ffprobe."""
        pass

    @abstractmethod
    def merge_audio_video(
        self, video_path: Path, audio_path: Path, output_video_path: Path
    ) -> Path:
        """Replace original audio track with synchronized dubbed audio."""
        pass

    @abstractmethod
    def prepare_audio_for_transcription(
        self, input_media_path: Path, output_wav_path: Path
    ) -> Path:
        """Extract or convert any audio or video file to 16kHz mono 16-bit PCM WAV for Whisper."""
        pass

