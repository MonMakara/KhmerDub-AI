import logging
import time
from pathlib import Path
from typing import Optional, Dict

from gtts import gTTS, gTTSError
from gtts.lang import tts_langs

from app.core.config import settings
from app.services.tts.base import TTSProvider, TTSAudioResult
from app.services.tts.exceptions import (
    LanguageNotSupportedError,
    EmptyTextError,
    TTSNetworkError,
    TTSGenerationError,
)
from app.services.video.ffmpeg import FFmpegVideoProcessor

logger = logging.getLogger(__name__)


class GoogleTTSProvider(TTSProvider):
    """Concrete implementation of TTSProvider using Google Text-to-Speech (gTTS).

    NOTE: gTTS calls Google Translate's online text-to-speech HTTP endpoint.
    It requires internet connectivity and does not run as a local offline model.
    It supports the standard Khmer voice ('km') with normal or slow speed.
    """

    def __init__(
        self,
        default_language: Optional[str] = None,
        max_retries: Optional[int] = None,
        slow: Optional[bool] = None,
        video_processor: Optional[FFmpegVideoProcessor] = None,
    ):
        self.default_language = default_language or settings.TTS_LANGUAGE
        self.max_retries = max_retries if max_retries is not None else settings.TTS_MAX_RETRIES
        self.slow = slow if slow is not None else settings.TTS_SLOW
        self.video_processor = video_processor or FFmpegVideoProcessor()
        self._supported_languages: Optional[Dict[str, str]] = None

    def get_supported_languages(self) -> Dict[str, str]:
        """Fetch dictionary of supported language codes and their display names."""
        if self._supported_languages is None:
            try:
                self._supported_languages = tts_langs()
            except Exception as e:
                logger.warning("Failed to fetch gTTS language dictionary: %s. Using default 'km'.", e)
                return {"km": "Khmer", "en": "English"}
        return self._supported_languages

    def is_language_supported(self, language: str) -> bool:
        """Check if language code is supported by gTTS."""
        supported = self.get_supported_languages()
        return language.lower() in supported

    def synthesize(
        self,
        text: str,
        output_path: Path,
        language: str = "km",
        voice: Optional[str] = None,
        slow: bool = False,
    ) -> TTSAudioResult:
        """Convert text into speech MP3 using Google gTTS with exponential backoff retry.

        Args:
            text: Text to synthesize.
            output_path: Destination path where MP3 will be saved.
            language: Language code (default 'km').
            voice: Voice identifier (for gTTS, always 'default').
            slow: Whether to read at slow speed.

        Returns:
            TTSAudioResult containing path, duration, and provider details.

        Raises:
            EmptyTextError: If text is empty or only whitespace.
            LanguageNotSupportedError: If language code is not recognized by gTTS.
            TTSNetworkError: If network connectivity or Google endpoint fails after retries.
            TTSGenerationError: If file cannot be saved or probed.
        """
        clean_text = text.strip() if text else ""
        if not clean_text:
            raise EmptyTextError("Cannot synthesize speech from empty text.")

        target_lang = (language or self.default_language).strip().lower()
        if not self.is_language_supported(target_lang):
            raise LanguageNotSupportedError(f"Language '{target_lang}' is not supported by Google TTS.")

        use_slow = slow or self.slow
        voice_label = voice or "default"

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    "Attempt %d/%d to synthesize speech for text: '%.40s...' (lang=%s)",
                    attempt,
                    self.max_retries,
                    clean_text,
                    target_lang,
                )
                tts = gTTS(text=clean_text, lang=target_lang, slow=use_slow)
                tts.save(str(output_path))

                if not output_path.exists() or output_path.stat().st_size == 0:
                    raise TTSGenerationError(f"Generated audio file is missing or empty at {output_path}")

                # Measure actual duration via ffprobe
                duration = self.video_processor.get_audio_duration(output_path)
                logger.info(
                    "Synthesized %s (%.2fs) using gTTS [lang=%s, voice=%s]",
                    output_path.name,
                    duration,
                    target_lang,
                    voice_label,
                )

                return TTSAudioResult(
                    audio_path=output_path,
                    duration_seconds=duration,
                    provider_name="gtts",
                    voice=voice_label,
                    language=target_lang,
                )

            except (gTTSError, ConnectionError, TimeoutError, OSError) as e:
                last_exception = e
                logger.warning(
                    "gTTS attempt %d/%d failed with error: %s",
                    attempt,
                    self.max_retries,
                    e,
                )
                if attempt < self.max_retries:
                    backoff_delay = 1.0 * (2 ** (attempt - 1))
                    logger.info("Retrying gTTS in %.1f seconds...", backoff_delay)
                    time.sleep(backoff_delay)
            except Exception as e:
                logger.error("Unexpected error during speech synthesis: %s", e)
                raise TTSGenerationError(f"Speech synthesis failed: {e}") from e

        # If exhausted all retries
        logger.error(
            "Failed to synthesize speech after %d attempts: %s",
            self.max_retries,
            last_exception,
        )
        raise TTSNetworkError(
            f"Failed to synthesize speech via Google gTTS after {self.max_retries} attempts: {last_exception}"
        ) from last_exception
