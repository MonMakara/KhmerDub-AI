from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TranslationSegmentResult:
    segment_order: int
    original_text: str
    translated_text: str


@dataclass
class TranslationAlternative:
    style: str
    label: str
    khmer_text: str
    explanation: Optional[str] = None


@dataclass
class AIImprovementResult:
    original_text: str
    current_khmer_text: str
    improved_khmer_text: str
    explanation: str
    style: str
    provider: str
    model: str
    alternatives: List[TranslationAlternative] = field(default_factory=list)


class TranslationProvider(ABC):
    """Abstract interface for text translation providers."""

    @abstractmethod
    def translate(
        self,
        texts: List[str],
        source_lang: str = "en",
        target_lang: str = "km",
        style: str = "standard",
        contexts: Optional[List[str]] = None,
        durations: Optional[List[float]] = None,
        **kwargs,
    ) -> List[str]:
        """Translate a list of text segments from source to target language."""
        pass

    def improve_translation(
        self,
        english_text: str,
        current_khmer: Optional[str] = None,
        style: str = "natural",
        prev_text: Optional[str] = None,
        next_text: Optional[str] = None,
        target_duration: Optional[float] = None,
        context: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        current_khmer_text: Optional[str] = None,
        **kwargs,
    ) -> AIImprovementResult:
        """Improve an existing translation using AI models with context and style awareness."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support AI translation improvement."
        )

    def generate_alternatives(
        self,
        english_text: str,
        current_khmer: Optional[str] = None,
        prev_text: Optional[str] = None,
        next_text: Optional[str] = None,
        target_duration: Optional[float] = None,
        context: Optional[str] = None,
        current_khmer_text: Optional[str] = None,
        **kwargs,
    ) -> List[TranslationAlternative]:
        """Generate structured Khmer translation alternatives (natural, simple, short)."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support alternative translation generation."
        )
