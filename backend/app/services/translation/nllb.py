import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import psutil
from app.core.ai_guard import acquire_ai_inference_slot
from app.core.config import settings
from app.services.translation.base import TranslationProvider
from app.services.translation.formatter import KhmerTextFormatter
from app.services.translation.glossary import KhmerGlossary
from app.services.translation.exceptions import (
    ModelLoadError,
    TextTranslationError,
)

logger = logging.getLogger(__name__)

# Class/Module-level model cache to reuse loaded model and tokenizer instances
_model_cache: Dict[str, Tuple[Any, Any]] = {}
_cache_lock = threading.Lock()

# Standard language code normalization mapping for NLLB FLORES-200
LANGUAGE_CODE_MAP = {
    "en": "eng_Latn",
    "eng": "eng_Latn",
    "eng_Latn": "eng_Latn",
    "km": "khm_Khmr",
    "khm": "khm_Khmr",
    "khm_Khmr": "khm_Khmr",
}


def get_current_process_ram_mb() -> float:
    """Return the current resident set size (RSS) memory in megabytes."""
    try:
        process = psutil.Process()
        return round(process.memory_info().rss / (1024 * 1024), 2)
    except Exception:
        return 0.0


def normalize_language_code(code: str) -> str:
    """Normalize common language codes to FLORES-200 NLLB format."""
    clean = (code or "").strip()
    return LANGUAGE_CODE_MAP.get(clean, clean)


class NLLBTranslationProvider(TranslationProvider):
    """Concrete translation provider using Meta's NLLB-200 Seq2Seq model."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        batch_size: Optional[int] = None,
        max_input_tokens: Optional[int] = None,
        num_beams: Optional[int] = None,
    ):
        self.model_name = model_name or settings.TRANSLATION_MODEL or "facebook/nllb-200-distilled-600M"
        self.device = device or settings.TRANSLATION_DEVICE or "cpu"
        self.cache_dir = cache_dir or settings.MODEL_CACHE_DIR
        self.batch_size = batch_size or settings.TRANSLATION_BATCH_SIZE or 1
        self.max_input_tokens = max_input_tokens or settings.TRANSLATION_MAX_INPUT_TOKENS or 512
        self.num_beams = num_beams or settings.TRANSLATION_NUM_BEAMS or 2

    def _get_cache_key(self) -> str:
        return f"{self.model_name}_{self.device}"

    def get_model_and_tokenizer(self) -> Tuple[Any, Any]:
        """Lazily load or retrieve the cached model and tokenizer thread-safely."""
        cache_key = self._get_cache_key()

        with _cache_lock:
            if cache_key in _model_cache:
                return _model_cache[cache_key]

            ram_before = get_current_process_ram_mb()
            logger.info(
                "Loading NLLB model '%s' on %s (Current RAM: %.2f MB)...",
                self.model_name,
                self.device,
                ram_before,
            )

            try:
                import torch
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            except ImportError as e:
                raise ModelLoadError("transformers or torch is not installed.") from e

            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)

                tokenizer = AutoTokenizer.from_pretrained(
                    self.model_name,
                    cache_dir=str(self.cache_dir),
                )

                model = AutoModelForSeq2SeqLM.from_pretrained(
                    self.model_name,
                    cache_dir=str(self.cache_dir),
                )
                model.to(self.device)
                model.eval()

                _model_cache[cache_key] = (model, tokenizer)

                ram_after = get_current_process_ram_mb()
                ram_delta = max(0.0, ram_after - ram_before)
                logger.info(
                    "Successfully loaded NLLB model '%s' (RAM: %.2f MB, Delta: +%.2f MB)",
                    cache_key,
                    ram_after,
                    ram_delta,
                )
                return model, tokenizer

            except Exception as e:
                logger.error("Failed to load NLLB model '%s': %s", self.model_name, e)
                raise ModelLoadError(f"Failed to load NLLB model '{self.model_name}': {e}") from e

    def translate(
        self,
        texts: List[str],
        source_lang: str = "eng_Latn",
        target_lang: str = "khm_Khmr",
        contexts: Optional[List[str]] = None,
        style: str = "standard",
        durations: Optional[List[float]] = None,
        **kwargs,
    ) -> List[str]:
        """Translate a list of English texts into natural Khmer Unicode text."""
        if not texts:
            return []

        src_flores = normalize_language_code(source_lang or settings.TRANSLATION_SOURCE_LANG)
        tgt_flores = normalize_language_code(target_lang or settings.TRANSLATION_TARGET_LANG)

        # Quick check for texts
        all_empty = all(not (t or "").strip() for t in texts)
        if all_empty:
            return ["" for _ in texts]

        model, tokenizer = self.get_model_and_tokenizer()

        try:
            import torch
        except ImportError as e:
            raise ModelLoadError("torch is not installed.") from e

        # Ensure tokenizer source language is set
        tokenizer.src_lang = src_flores

        # Resolve target language forced BOS token id
        try:
            forced_bos_token_id = tokenizer.convert_tokens_to_ids(tgt_flores)
            if forced_bos_token_id is None or forced_bos_token_id == tokenizer.unk_token_id:
                # Try lang_code_to_id mapping if available
                if hasattr(tokenizer, "lang_code_to_id") and tgt_flores in tokenizer.lang_code_to_id:
                    forced_bos_token_id = tokenizer.lang_code_to_id[tgt_flores]
                else:
                    raise ValueError(f"Unknown target language code for NLLB: '{tgt_flores}'")
        except Exception as e:
            raise TextTranslationError(f"Invalid target language code '{tgt_flores}': {e}") from e

        results: List[str] = []
        batch_size = max(1, self.batch_size)

        try:
            with acquire_ai_inference_slot("NLLB_600M"):
                with torch.inference_mode():
                    for i in range(0, len(texts), batch_size):
                        batch_raw = texts[i : i + batch_size]
                        batch_cleaned = [t.strip() for t in batch_raw]

                        # Filter out indices that are purely empty
                        non_empty_indices = [idx for idx, t in enumerate(batch_cleaned) if t]

                        if not non_empty_indices:
                            results.extend(["" for _ in batch_raw])
                            continue

                        sub_batch = [batch_cleaned[idx] for idx in non_empty_indices]

                        inputs = tokenizer(
                            sub_batch,
                            return_tensors="pt",
                            padding=True,
                            truncation=True,
                            max_length=self.max_input_tokens,
                        ).to(self.device)

                        generated_tokens = model.generate(
                            **inputs,
                            forced_bos_token_id=forced_bos_token_id,
                            max_length=self.max_input_tokens,
                            num_beams=self.num_beams,
                            early_stopping=True,
                        )

                        decoded_batch = tokenizer.batch_decode(
                            generated_tokens,
                            skip_special_tokens=True,
                        )

                        # Reassemble original batch ordering, apply terminology alignment & natural Khmer formatting
                        sub_idx = 0
                        for rel_idx in range(len(batch_raw)):
                            global_idx = i + rel_idx
                            if rel_idx in non_empty_indices:
                                raw_khmer = decoded_batch[sub_idx].strip()
                                source_en = batch_raw[rel_idx]
                                context_en = (
                                    contexts[global_idx]
                                    if contexts and global_idx < len(contexts) and contexts[global_idx]
                                    else source_en
                                )
                                aligned_khmer = KhmerGlossary.align_terminology(context_en, raw_khmer)
                                formatted_khmer = KhmerTextFormatter.format(aligned_khmer)
                                if durations and global_idx < len(durations) and durations[global_idx] and durations[global_idx] > 0.0:
                                    from app.services.dubbing.auto_fit import shorten_khmer_text
                                    dur_budget = float(durations[global_idx])
                                    char_limit = max(18, int(dur_budget * 12.0))
                                    if len(formatted_khmer) > char_limit:
                                        formatted_khmer = shorten_khmer_text(formatted_khmer, target_char_count=char_limit)
                                results.append(formatted_khmer)
                                sub_idx += 1
                            else:
                                results.append("")

            logger.info(
                "Translated %d text segment(s) (%s -> %s) successfully.",
                len(texts),
                src_flores,
                tgt_flores,
            )
            return results

        except Exception as e:
            logger.error("Error during NLLB translation inference: %s", e)
            raise TextTranslationError(f"Translation inference failed: {e}") from e
