from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class TranscriptionSegment:
    segment_order: int
    start_time: float
    end_time: float
    text: str


class TranscriptionProvider(ABC):
    """Abstract interface for speech-to-text providers (e.g. faster-whisper)."""

    @abstractmethod
    def transcribe(self, audio_path: Path, language: str = "en") -> List[TranscriptionSegment]:
        """Transcribe an audio file into timed segments."""
        pass
