from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class TTSAudioResult:
    audio_path: Path
    duration_seconds: float
    provider_name: str
    voice: str = "default"
    language: str = "km"


class TTSProvider(ABC):
    """Abstract interface for text-to-speech providers (gTTS, Edge TTS, local models, etc.)."""

    @abstractmethod
    def synthesize(
        self,
        text: str,
        output_path: Path,
        language: str = "km",
        voice: Optional[str] = None,
        slow: bool = False,
    ) -> TTSAudioResult:
        """Convert text into an audio file."""
        pass
