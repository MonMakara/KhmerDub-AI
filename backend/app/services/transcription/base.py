from abc import ABC, abstractmethod
import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class WordTiming:
    """Represents a single word with timestamp and model confidence."""
    word: str
    start: float
    end: float
    probability: float = 1.0
    word_id: Optional[str] = None
    is_uncertain: bool = False

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "word": self.word,
            "start": float(self.start),
            "end": float(self.end),
            "probability": float(self.probability),
        }
        if self.word_id is not None:
            result["word_id"] = self.word_id
        if self.is_uncertain:
            result["is_uncertain"] = True
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WordTiming":
        return cls(
            word=data["word"],
            start=float(data["start"]),
            end=float(data["end"]),
            probability=float(data.get("probability", 1.0)),
            word_id=data.get("word_id"),
            is_uncertain=bool(data.get("is_uncertain", False)),
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
    id: Optional[str] = None
    source_audio_reference: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_order": self.segment_order,
            "start_time": float(self.start_time),
            "end_time": float(self.end_time),
            "id": self.id,
            "source_audio_reference": self.source_audio_reference,
            "source_word_ids": [w.word_id for w in self.words or []],
            "duration_seconds": self.end_time - self.start_time,
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
            id=data.get("id"),
            source_audio_reference=data.get("source_audio_reference"),
        )


def identify_source_words(
    segments: List[TranscriptionSegment], source_key: Optional[str] = None,
    source_audio_reference: Optional[str] = None,
) -> List[TranscriptionSegment]:
    """Attach deterministic provenance to copies; never alter ASR intervals."""
    if source_key is None:
        payload = [(w.word, w.start, w.end) for s in segments for w in s.words or []]
        source_key = hashlib.sha256(json.dumps(payload).encode()).hexdigest()
    result = []
    index = 0
    for segment in segments:
        words = []
        for word in segment.words or []:
            word_id = word.word_id or str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"khmerdub:{source_key}:{index}:{word.word}:{word.start!r}:{word.end!r}",
            ))
            words.append(replace(word, word_id=word_id))
            index += 1
        identity = ":".join(w.word_id for w in words) if words else (
            f"{source_key}:{segment.segment_order}:{segment.text}:"
            f"{segment.start_time!r}:{segment.end_time!r}"
        )
        result.append(replace(
            segment, words=words or None,
            is_approximate=segment.is_approximate or any(
                w.is_uncertain or w.end <= w.start for w in words
            ),
            id=segment.id or str(uuid.uuid5(uuid.NAMESPACE_URL, identity)),
            source_audio_reference=source_audio_reference or segment.source_audio_reference,
        ))
    return result


def project_segment_id(project_id: str, source_segment_id: str) -> str:
    """Namespace stable boundaries per project to avoid cross-project ID collisions."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{project_id}:{source_segment_id}"))


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
