import asyncio
import concurrent.futures
import logging
import time
from pathlib import Path
from typing import Optional, Dict

import edge_tts

from app.core.config import settings
from app.services.tts.base import TTSProvider, TTSAudioResult
from app.services.tts.exceptions import (
    EmptyTextError,
    VoiceNotSupportedError,
    TTSNetworkError,
    TTSGenerationError,
)
from app.services.video.ffmpeg import FFmpegVideoProcessor

logger = logging.getLogger(__name__)

SUPPORTED_EDGE_VOICES: Dict[str, Dict[str, str]] = {
    "km-KH-PisethNeural": {
        "name": "Piseth",
        "gender": "male",
        "language": "km-KH",
        "label": "Microsoft Piseth (Male)",
        "description": "Microsoft Edge Neural Voice (Male, friendly & positive)",
    },
    "km-KH-SreymomNeural": {
        "name": "Sreymom",
        "gender": "female",
        "language": "km-KH",
        "label": "Microsoft Sreymom (Female)",
        "description": "Microsoft Edge Neural Voice (Female, friendly & positive)",
    },
}

DEFAULT_EDGE_VOICE = "km-KH-PisethNeural"


class EdgeTTSProvider(TTSProvider):
    """Concrete implementation of TTSProvider using Microsoft Edge TTS (edge-tts).

    NOTE: edge-tts communicates with Microsoft Speech Services endpoints online.
    It requires network connectivity, does not run locally offline, and produces
    high-quality natural neural Khmer speech (Piseth and Sreymom).
    """

    def __init__(
        self,
        default_voice: Optional[str] = None,
        max_retries: Optional[int] = None,
        video_processor: Optional[FFmpegVideoProcessor] = None,
    ):
        self.default_voice = default_voice or DEFAULT_EDGE_VOICE
        self.max_retries = max_retries if max_retries is not None else settings.TTS_MAX_RETRIES
        self.video_processor = video_processor or FFmpegVideoProcessor()

    @classmethod
    def get_supported_voices(cls) -> Dict[str, Dict[str, str]]:
        """Return dictionary of supported Microsoft Khmer voices."""
        return SUPPORTED_EDGE_VOICES

    @classmethod
    def is_voice_supported(cls, voice: str) -> bool:
        """Check if voice identifier is supported by Edge TTS."""
        return voice in SUPPORTED_EDGE_VOICES

    def _run_async_safely(self, coro):
        """Execute an async coroutine safely, regardless of whether an event loop is already running."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return asyncio.run(coro)

    def synthesize(
        self,
        text: str,
        output_path: Path,
        language: str = "km",
        voice: Optional[str] = None,
        slow: bool = False,
        **kwargs,
    ) -> TTSAudioResult:
        """Convert text into speech MP3 using Microsoft Edge TTS with exponential backoff retry.

        Args:
            text: Text to synthesize.
            output_path: Destination path where MP3 will be saved.
            language: Language code (default 'km').
            voice: Voice identifier ('km-KH-PisethNeural' or 'km-KH-SreymomNeural').
            slow: Whether to slow down playback (not currently used directly by edge-tts).

        Returns:
            TTSAudioResult containing path, duration, and provider details.

        Raises:
            EmptyTextError: If text is empty or only whitespace.
            VoiceNotSupportedError: If voice identifier is not recognized.
            TTSNetworkError: If network connectivity or Edge endpoint fails after retries.
            TTSGenerationError: If file cannot be saved or probed.
        """
        clean_text = text.strip() if text else ""
        if not clean_text:
            raise EmptyTextError("Cannot synthesize speech from empty text.")

        target_voice = voice or self.default_voice
        if target_voice == "default":
            target_voice = DEFAULT_EDGE_VOICE

        if not self.is_voice_supported(target_voice):
            raise VoiceNotSupportedError(
                f"Voice '{target_voice}' is not supported by Edge TTS. "
                f"Supported voices: {list(SUPPORTED_EDGE_VOICES.keys())}"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        async def _synthesize():
            communicate = edge_tts.Communicate(clean_text, target_voice)
            await communicate.save(str(output_path))

        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    "Attempt %d/%d to synthesize speech via Edge TTS: '%.40s...' (voice=%s)",
                    attempt,
                    self.max_retries,
                    clean_text,
                    target_voice,
                )
                self._run_async_safely(_synthesize())

                if not output_path.exists() or output_path.stat().st_size == 0:
                    raise TTSGenerationError(f"Generated Edge audio file is missing or empty at {output_path}")

                # Measure actual duration via ffprobe
                duration = self.video_processor.get_audio_duration(output_path)
                logger.info(
                    "Synthesized %s (%.2fs) using Edge TTS [voice=%s]",
                    output_path.name,
                    duration,
                    target_voice,
                )

                return TTSAudioResult(
                    audio_path=output_path,
                    duration_seconds=duration,
                    provider_name="edge",
                    voice=target_voice,
                    language="km",
                )

            except (ConnectionError, TimeoutError, OSError) as e:
                last_exception = e
                logger.warning("Edge TTS attempt %d/%d failed with error: %s", attempt, self.max_retries, e)
                if attempt < self.max_retries:
                    backoff_delay = 1.0 * (2 ** (attempt - 1))
                    logger.info("Retrying Edge TTS in %.1f seconds...", backoff_delay)
                    time.sleep(backoff_delay)
            except Exception as e:
                if isinstance(e, (EmptyTextError, VoiceNotSupportedError)):
                    raise
                logger.error("Unexpected error during Edge TTS speech synthesis: %s", e)
                raise TTSGenerationError(f"Edge TTS speech synthesis failed: {e}") from e

        logger.error("Failed to synthesize speech via Edge TTS after %d attempts: %s", self.max_retries, last_exception)
        raise TTSNetworkError(
            f"Failed to synthesize speech via Edge TTS after {self.max_retries} attempts: {last_exception}"
        ) from last_exception
