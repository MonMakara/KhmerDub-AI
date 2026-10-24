from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List


@dataclass
class TranslationSegmentResult:
    segment_order: int
    original_text: str
    translated_text: str


class TranslationProvider(ABC):
    """Abstract interface for text translation providers."""

    @abstractmethod
    def translate(
        self, texts: List[str], source_lang: str = "en", target_lang: str = "km"
    ) -> List[str]:
        """Translate a list of text segments from source to target language."""
        pass
