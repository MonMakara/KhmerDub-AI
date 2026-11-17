import logging
import hashlib
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.core.ai_guard import acquire_ai_inference_slot
from app.core.config import settings
from app.services.transcription.base import (
    TranscriptionProvider,
    TranscriptionSegment,
    WordTiming,
    identify_source_words,
)
from app.services.transcription.exceptions import (
    ModelLoadError,
    AudioTranscriptionError,
)

logger = logging.getLogger(__name__)

# Class/Module-level model cache to reuse loaded model instances across requests
_model_cache: Dict[str, any] = {}
_cache_lock = threading.Lock()


def _get_audio_duration_seconds(path: Path) -> float:
    """Retrieve audio duration in seconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        out = subprocess.check_output(cmd).decode().strip()
        return max(0.01, float(out))
    except Exception:
        return 0.0


def clean_whisper_text(text: str) -> str:
    """Clean hallucinated non-speech cues and artifacts from Whisper output."""
    if not text:
        return ""
    # Strip bracketed/parenthesized non-speech annotations like [Music], (Music), [Applause], ♪
    cleaned = re.sub(
        r"\[(music|applause|laughter|cheering|cough|throat clearing|silence|snort|sigh|gasp|groan|screaming|bell|alarm|chime|singing|instrumental)\]",
        "",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\((music|applause|laughter|cheering|cough|throat clearing|silence|snort|sigh|gasp|groan|screaming|bell|alarm|chime|singing|instrumental)\)",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[♪♫♬♩]+", "", cleaned)
    # Collapse multiple whitespaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # If the text was only a stray residual punctuation mark, treat as empty
    if cleaned in (".", "..", "...", ",", "!", "?", "-", "--", "—", ";", ":"):
        return ""
    return cleaned


def _detect_speech_intervals(
    audio_path: Path,
    min_silence_dur: float = 0.45,
    silence_threshold_db: float = -32.0,
    min_speech_dur: float = 0.3,
    max_merge_gap: float = 0.5,
    max_interval_duration: float = 22.0,
) -> List[Tuple[float, float]]:
    """Detect natural speech activity intervals using silence detection.
    
    Prevents Whisper from collapsing unpunctuated Khmer speech into a single
    massive run-on segment or cutting off audio after pauses.
    """
    total_dur = _get_audio_duration_seconds(audio_path)
    if total_dur <= 0.0:
        return [(0.0, 1.0)]

    cmd = [
        "ffmpeg", "-i", str(audio_path),
        "-af", f"silencedetect=noise={silence_threshold_db}dB:d={min_silence_dur}",
        "-f", "null", "-"
    ]
    try:
        res = subprocess.run(cmd, stderr=subprocess.PIPE, text=True, check=False)
    except Exception as e:
        logger.warning("silencedetect failed for %s: %s", audio_path, e)
        return [(0.0, total_dur)]

    silences: List[Tuple[float, float]] = []
    current_start = None
    for line in res.stderr.splitlines():
        if "silence_start:" in line:
            m = re.search(r"silence_start:\s*([0-9.]+)", line)
            if m:
                current_start = float(m.group(1))
        elif "silence_end:" in line and current_start is not None:
            m = re.search(r"silence_end:\s*([0-9.]+)", line)
            if m:
                silences.append((current_start, float(m.group(1))))
                current_start = None
    if current_start is not None and current_start < total_dur:
        silences.append((current_start, total_dur))

    raw_speech: List[Tuple[float, float]] = []
    cursor = 0.0
    for s_start, s_end in silences:
        if s_start > cursor + min_speech_dur:
            raw_speech.append((cursor, s_start))
        cursor = s_end
    if cursor + min_speech_dur < total_dur:
        raw_speech.append((cursor, total_dur))

    if not raw_speech:
        if total_dur > max_interval_duration:
            slices: List[Tuple[float, float]] = []
            cur = 0.0
            while cur < total_dur:
                nxt = min(total_dur, cur + max_interval_duration)
                slices.append((cur, nxt))
                cur = nxt
            return slices
        return [(0.0, total_dur)]

    # Merge speech intervals separated by small pause gaps (< max_merge_gap)
    merged: List[Tuple[float, float]] = [raw_speech[0]]
    for next_st, next_en in raw_speech[1:]:
        prev_st, prev_en = merged[-1]
        gap = next_st - prev_en
        if gap <= max_merge_gap and (next_en - prev_st) <= max_interval_duration:
            merged[-1] = (prev_st, next_en)
        else:
            merged.append((next_st, next_en))

    return merged


class FasterWhisperTranscriptionProvider(TranscriptionProvider):
    """Concrete speech-to-text provider using faster-whisper."""

    def __init__(
        self,
        model_size: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
        download_root: Optional[Path] = None,
        vad_filter: Optional[bool] = None,
        khmer_model_name: Optional[str] = None,
    ):
        self.model_size = model_size or settings.WHISPER_MODEL or settings.WHISPER_MODEL_SIZE or "base"
        self.khmer_model_name = (
            khmer_model_name
            or getattr(settings, "WHISPER_KHMER_MODEL", "PhanithLIM/whisper-small-khmer-ct2")
        )
        self.device = device or settings.WHISPER_DEVICE or "cpu"
        self.compute_type = compute_type or settings.WHISPER_COMPUTE_TYPE or "int8"
        self.download_root = download_root or settings.MODEL_CACHE_DIR
        self.vad_filter = vad_filter if vad_filter is not None else settings.WHISPER_VAD_FILTER

    def _get_cache_key(self, model_name: Optional[str] = None) -> str:
        name = model_name or self.model_size
        return f"{name}_{self.device}_{self.compute_type}"

    def get_model(self, model_name: Optional[str] = None):
        """Lazily load or retrieve the cached WhisperModel instance thread-safely."""
        target_model = model_name or self.model_size
        cache_key = self._get_cache_key(target_model)

        with _cache_lock:
            if cache_key in _model_cache:
                return _model_cache[cache_key]

            logger.info(
                "Loading faster-whisper model (model=%s, device=%s, compute_type=%s)...",
                target_model,
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
                    target_model,
                    device=self.device,
                    compute_type=self.compute_type,
                    download_root=str(self.download_root),
                )
                _model_cache[cache_key] = model
                logger.info("Successfully loaded faster-whisper model '%s'", cache_key)
                return model
            except Exception as e:
                logger.error("Failed to load faster-whisper model: %s", e)
                raise ModelLoadError(f"Failed to load Whisper model '{target_model}': {e}") from e

    def _transcribe_khmer(self, model, audio_path: Path) -> List[TranscriptionSegment]:
        """Transcribe Khmer audio using speech interval detection and chunking.
        
        Because fine-tuned Khmer Whisper lacks punctuation tokens in training data,
        processing full files directly without interval chunking leads to attention
        collapse, single run-on sentences, and truncation at long pauses.
        Speech interval chunking guarantees honest timestamps and preserves all phrases.
        """
        total_dur = _get_audio_duration_seconds(audio_path)
        intervals = _detect_speech_intervals(audio_path)

        results: List[TranscriptionSegment] = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            order = 1
            for st, en in intervals:
                # Discard transient sub-second noise blips that trigger hallucination
                if (en - st) < 0.45:
                    continue

                chunk_wav = tmp_dir_path / f"chunk_{order}.wav"
                pad_st = max(0.0, st - 0.08)
                pad_en = min(total_dur, en + 0.08)

                cmd = [
                    "ffmpeg", "-y",
                    "-ss", f"{pad_st:.3f}",
                    "-to", f"{pad_en:.3f}",
                    "-i", str(audio_path),
                    "-ar", "16000",
                    "-ac", "1",
                    str(chunk_wav),
                ]
                try:
                    subprocess.run(cmd, capture_output=True, check=True)
                except Exception as e:
                    logger.warning("Failed to extract chunk %s: %s", chunk_wav, e)
                    continue

                if not chunk_wav.exists() or chunk_wav.stat().st_size == 0:
                    continue

                try:
                    chunk_segs, _ = model.transcribe(
                        str(chunk_wav),
                        language="km",
                        beam_size=5,
                        vad_filter=False,
                        word_timestamps=False,
                        condition_on_previous_text=False,
                        repetition_penalty=1.15,
                        no_repeat_ngram_size=3,
                        no_speech_threshold=0.6,
                        compression_ratio_threshold=2.4,
                    )
                    text_parts = [
                        clean_whisper_text(s.text.strip())
                        for s in chunk_segs
                        if s.text and s.text.strip()
                    ]
                    full_text = " ".join([p for p in text_parts if p]).strip()
                except Exception as e:
                    logger.error("Error transcribing chunk [%.2f-%.2f]: %s", st, en, e)
                    continue

                if full_text:
                    try:
                        from app.services.translation.formatter import KhmerTextFormatter
                        formatted_text = KhmerTextFormatter.format(full_text)
                    except Exception:
                        formatted_text = full_text

                    results.append(
                        TranscriptionSegment(
                            segment_order=len(results) + 1,
                            start_time=round(st, 2),
                            end_time=round(en, 2),
                            text=formatted_text,
                            words=None,
                        )
                    )

        # Fallback if interval extraction produced nothing
        if not results:
            logger.info("Speech interval transcription returned 0 segments for %s; falling back to direct decode", audio_path)
            segments_generator, _ = model.transcribe(
                str(audio_path),
                language="km",
                vad_filter=False,
                word_timestamps=False,
                beam_size=5,
                condition_on_previous_text=False,
                repetition_penalty=1.15,
                no_repeat_ngram_size=3,
                no_speech_threshold=0.6,
                compression_ratio_threshold=2.4,
            )
            for segment in segments_generator:
                raw_text = segment.text.strip() if segment.text else ""
                clean_text = clean_whisper_text(raw_text)
                if clean_text:
                    try:
                        from app.services.translation.formatter import KhmerTextFormatter
                        clean_text = KhmerTextFormatter.format(clean_text)
                    except Exception:
                        pass
                    results.append(
                        TranscriptionSegment(
                            segment_order=len(results) + 1,
                            start_time=float(segment.start),
                            end_time=float(segment.end),
                            text=clean_text,
                            words=None,
                        )
                    )

        return results

    def transcribe(
        self,
        audio_path: Path,
        language: str = "en",
        word_timestamps: bool = True,
        initial_prompt: Optional[str] = None,
    ) -> List[TranscriptionSegment]:
        """Transcribe an audio file into timestamped segments with word timings."""
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file does not exist: {audio_path}")

        if audio_path.stat().st_size == 0:
            logger.warning("Audio file %s is empty (0 bytes). Returning empty transcript.", audio_path)
            return []

        clean_lang = (language or settings.WHISPER_LANGUAGE or "en").strip().lower()
        is_khmer = clean_lang in ("km", "khmer")

        if is_khmer:
            target_model_name = self.khmer_model_name
            actual_language = "km"
        else:
            target_model_name = self.model_size
            actual_language = clean_lang
            beam_size = 5 if clean_lang == "en" else 1

        model = self.get_model(model_name=target_model_name)

        try:
            with acquire_ai_inference_slot(f"Whisper_{target_model_name}"):
                if is_khmer:
                    results = self._transcribe_khmer(model, audio_path)
                else:
                    segments_generator, info = model.transcribe(
                        str(audio_path),
                        language=actual_language,
                        vad_filter=self.vad_filter,
                        vad_parameters=dict(
                            min_silence_duration_ms=280,
                            speech_pad_ms=160,
                        ) if self.vad_filter else None,
                        word_timestamps=word_timestamps,
                        beam_size=beam_size,
                        condition_on_previous_text=False,
                        no_speech_threshold=0.6,
                        compression_ratio_threshold=2.4,
                        hallucination_silence_threshold=2.0,
                        initial_prompt=initial_prompt,
                    )

                    results: List[TranscriptionSegment] = []
                    # Fully consume the generator inside the guard
                    for segment in segments_generator:
                        raw_text = segment.text.strip() if segment.text else ""
                        clean_text = clean_whisper_text(raw_text)
                        if clean_text:
                            word_list: List[WordTiming] = []
                            if hasattr(segment, "words") and segment.words:
                                for w in segment.words:
                                    if w.word and w.word.strip():
                                        word_clean = clean_whisper_text(w.word.strip())
                                        if word_clean:
                                            word_list.append(
                                                WordTiming(
                                                    word=word_clean,
                                                    start=float(w.start),
                                                    end=float(w.end),
                                                    probability=float(getattr(w, "probability", 1.0)),
                                                    is_uncertain=(
                                                        w.end <= w.start
                                                        or float(getattr(w, "probability", 1.0)) < 0.35
                                                    ),
                                                )
                                            )
                            results.append(
                                TranscriptionSegment(
                                    segment_order=len(results) + 1,
                                    start_time=float(segment.start),
                                    end_time=float(segment.end),
                                    text=clean_text,
                                    words=word_list if word_list else None,
                                )
                            )

            logger.info(
                "Transcribed audio %s: generated %d segments (model=%s, language=%s)",
                audio_path,
                len(results),
                target_model_name,
                actual_language,
            )
            with audio_path.open("rb") as source:
                source_key = hashlib.file_digest(source, "sha256").hexdigest()
            return identify_source_words(results, source_key, str(audio_path))

        except Exception as e:
            logger.error("Error during Whisper transcription of %s: %s", audio_path, e)
            raise AudioTranscriptionError(f"Transcription failed: {e}") from e
