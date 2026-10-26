from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class WordTiming:
    """Represents a single word with timestamp and model confidence."""
    word: str
    start: float
    end: float
    probability: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word,
            "start": round(float(self.start), 3),
            "end": round(float(self.end), 3),
            "probability": round(float(self.probability), 3),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WordTiming":
        return cls(
            word=data["word"],
            start=float(data["start"]),
            end=float(data["end"]),
            probability=float(data.get("probability", 1.0)),
        )


@dataclass
class TranscriptionSegment:
    segment_order: int
    start_time: float
    end_time: float
    text: str
    words: Optional[List[WordTiming]] = None
    is_approximate: bool = False
    is_manually_edited: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_order": self.segment_order,
            "start_time": round(float(self.start_time), 3),
            "end_time": round(float(self.end_time), 3),
            "text": self.text,
            "words": [w.to_dict() for w in self.words] if self.words else None,
            "is_approximate": self.is_approximate,
            "is_manually_edited": self.is_manually_edited,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TranscriptionSegment":
        words_data = data.get("words")
        words = [WordTiming.from_dict(w) for w in words_data] if words_data else None
        return cls(
            segment_order=int(data["segment_order"]),
            start_time=float(data["start_time"]),
            end_time=float(data["end_time"]),
            text=str(data["text"]),
            words=words,
            is_approximate=bool(data.get("is_approximate", False)),
            is_manually_edited=bool(data.get("is_manually_edited", False)),
        )


class TranscriptionProvider(ABC):
    """Abstract interface for speech-to-text providers (e.g. faster-whisper)."""

    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        language: str = "en",
        word_timestamps: bool = True,
    ) -> List[TranscriptionSegment]:
        """Transcribe an audio file into timed segments."""
        pass
