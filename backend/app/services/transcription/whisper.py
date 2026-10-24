import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional

from app.core.ai_guard import acquire_ai_inference_slot
from app.core.config import settings
from app.services.transcription.base import TranscriptionProvider, TranscriptionSegment
from app.services.transcription.exceptions import (
    TranscriptionError,
    ModelLoadError,
    AudioTranscriptionError,
)

logger = logging.getLogger(__name__)

# Class/Module-level model cache to reuse loaded model instances across requests
_model_cache: Dict[str, any] = {}
_cache_lock = threading.Lock()


class FasterWhisperTranscriptionProvider(TranscriptionProvider):
    """Concrete speech-to-text provider using faster-whisper."""

    def __init__(
        self,
        model_size: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
        download_root: Optional[Path] = None,
        vad_filter: Optional[bool] = None,
    ):
        self.model_size = model_size or settings.WHISPER_MODEL or settings.WHISPER_MODEL_SIZE or "base"
        self.device = device or settings.WHISPER_DEVICE or "cpu"
        self.compute_type = compute_type or settings.WHISPER_COMPUTE_TYPE or "int8"
        self.download_root = download_root or settings.MODEL_CACHE_DIR
        self.vad_filter = vad_filter if vad_filter is not None else settings.WHISPER_VAD_FILTER

    def _get_cache_key(self) -> str:
        return f"{self.model_size}_{self.device}_{self.compute_type}"

    def get_model(self):
        """Lazily load or retrieve the cached WhisperModel instance thread-safely."""
        cache_key = self._get_cache_key()

        with _cache_lock:
            if cache_key in _model_cache:
                return _model_cache[cache_key]

            logger.info(
                "Loading faster-whisper model (size=%s, device=%s, compute_type=%s)...",
                self.model_size,
                self.device,
                self.compute_type,
            )

            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise ModelLoadError("faster-whisper is not installed.") from e

            # Validate device and compute type combination
            if self.device.lower() == "cpu" and self.compute_type.lower() in ("float16", "fp16"):
                raise ModelLoadError(
                    "Compute type 'float16' is not supported on CPU. Use 'int8' or 'float32' for CPU execution."
                )

            try:
                self.download_root.mkdir(parents=True, exist_ok=True)
                model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type,
                    download_root=str(self.download_root),
                )
                _model_cache[cache_key] = model
                logger.info("Successfully loaded faster-whisper model '%s'", cache_key)
                return model
            except Exception as e:
                logger.error("Failed to load faster-whisper model: %s", e)
                raise ModelLoadError(f"Failed to load Whisper model '{self.model_size}': {e}") from e

    def transcribe(
        self, audio_path: Path, language: str = "en"
    ) -> List[TranscriptionSegment]:
        """Transcribe an audio file into timestamped segments."""
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file does not exist: {audio_path}")

        if audio_path.stat().st_size == 0:
            logger.warning("Audio file %s is empty (0 bytes). Returning empty transcript.", audio_path)
            return []

        model = self.get_model()

        try:
            with acquire_ai_inference_slot(f"Whisper_{self.model_size}"):
                segments_generator, info = model.transcribe(
                    str(audio_path),
                    language=language or settings.WHISPER_LANGUAGE or "en",
                    vad_filter=self.vad_filter,
                )

                results: List[TranscriptionSegment] = []
                # Fully consume the generator inside the guard
                for order, segment in enumerate(segments_generator, start=1):
                    clean_text = segment.text.strip()
                    if clean_text:
                        results.append(
                            TranscriptionSegment(
                                segment_order=order,
                                start_time=round(float(segment.start), 2),
                                end_time=round(float(segment.end), 2),
                                text=clean_text,
                            )
                        )

            logger.info(
                "Transcribed audio %s: generated %d segments (detected language=%s, prob=%.2f)",
                audio_path,
                len(results),
                getattr(info, "language", language),
                getattr(info, "language_probability", 1.0),
            )
            return results

        except Exception as e:
            logger.error("Error during Whisper transcription of %s: %s", audio_path, e)
            raise AudioTranscriptionError(f"Transcription failed: {e}") from e
