from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VideoMetadata:
    duration_seconds: float
    width: int
    height: int
    has_audio: bool
    audio_codec: str | None = None
    video_codec: str | None = None


class VideoProcessor(ABC):
    """Abstract interface for video/audio manipulation via FFmpeg."""

    @abstractmethod
    def get_metadata(self, video_path: Path) -> VideoMetadata:
        """Extract media metadata using ffprobe."""
        pass

    @abstractmethod
    def extract_audio(self, video_path: Path, output_audio_path: Path) -> Path:
        """Extract audio track from video as WAV/MP3."""
        pass

    @abstractmethod
    def merge_audio_video(
        self, video_path: Path, audio_path: Path, output_video_path: Path
    ) -> Path:
        """Replace original audio track with synchronized dubbed audio."""
        pass
