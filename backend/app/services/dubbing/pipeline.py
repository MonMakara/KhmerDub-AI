from dataclasses import dataclass
from typing import Optional
from app.services.transcription.base import TranscriptionProvider
from app.services.translation.base import TranslationProvider
from app.services.tts.base import TTSProvider
from app.services.video.base import VideoProcessor


@dataclass
class DubbingPipeline:
    """Orchestrates video extraction, transcription, translation, TTS, sync, and export."""

    video_processor: Optional[VideoProcessor] = None
    transcription_provider: Optional[TranscriptionProvider] = None
    translation_provider: Optional[TranslationProvider] = None
    tts_provider: Optional[TTSProvider] = None
