import json
import logging
import re
import time
from typing import List, Optional, Tuple

from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.core import credentials
from app.core.config import settings

def get_api_key(provider: str = "gemini") -> Optional[str]:
    """Helper wrapper resolving API key through app.core.credentials."""
    return credentials.get_api_key(provider)
from app.services.translation.base import (
    TranslationProvider,
    TranslationAlternative,
    AIImprovementResult,
)
from app.services.translation.formatter import KhmerTextFormatter
from app.services.translation.glossary import KhmerGlossary
from app.services.translation.prompts import (
    SYSTEM_INSTRUCTION,
    build_single_translation_prompt,
    build_batch_translation_prompt,
    build_ai_improve_prompt,
    build_alternatives_prompt,
    TRANSLATION_STYLES,
)
from app.services.translation.exceptions import (
    ProviderAuthenticationError,
    RateLimitError,
    ProviderTimeoutError,
    TextTranslationError,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
SUPPORTED_GEMINI_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-flash-lite-latest",
]
FALLBACK_GEMINI_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
]
DEPRECATED_GEMINI_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
}


class GeminiTranslationProvider(TranslationProvider):
    """Google Gemini AI translation provider using the official google-genai SDK.

    Provides high-quality English-to-Khmer translation, contextual improvements,
    natural conversational rewriting, and alternatives tailored for video dubbing.
    """

    BATCH_CHUNK_SIZE: int = 15

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
    ):
        self._explicit_key = api_key
        raw_model = model or getattr(settings, "GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        if raw_model in DEPRECATED_GEMINI_MODELS:
            logger.warning(
                "Configured Gemini model '%s' is deprecated by Google. Automatically migrating to '%s'.",
                raw_model,
                DEFAULT_GEMINI_MODEL,
            )
            self.model = DEFAULT_GEMINI_MODEL
        else:
            self.model = raw_model
        self.timeout = timeout
        self.max_retries = max_retries
        self._exhausted_models = set()

    @property
    def api_key(self) -> Optional[str]:
        """Resolve API key from explicit init parameter, env var, or encrypted credentials."""
        return self._explicit_key or get_api_key("gemini")

    def _get_client(self) -> genai.Client:
        """Instantiate official Gemini API client with active credentials."""
        key = self.api_key
        if not key:
            raise ProviderAuthenticationError(
                "Google Gemini API key is missing. Please configure GEMINI_API_KEY in Settings or your environment."
            )
        timeout_ms = int(max(self.timeout, 10.0) * 1000)
        return genai.Client(api_key=key, http_options={"timeout": timeout_ms})

    def test_connection(self, api_key: Optional[str] = None) -> Tuple[bool, str]:
        """Test API key authentication and network connectivity to Google Gemini."""
        key = api_key or self.api_key
        if not key:
            return False, "Google Gemini API key is missing. Please enter a valid API key."

        target_model = self.model
        if target_model in DEPRECATED_GEMINI_MODELS:
            target_model = DEFAULT_GEMINI_MODEL

        try:
            timeout_ms = int(max(self.timeout, 15.0) * 1000)
            client = genai.Client(api_key=key, http_options={"timeout": timeout_ms})
            # Lightweight prompt to verify credentials and model accessibility
            response = client.models.generate_content(
                model=target_model,
                contents="Ping. Respond with 'OK'.",
                config=types.GenerateContentConfig(
                    max_output_tokens=50,
                    temperature=0.0,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            if response and response.text:
                return True, f"Successfully connected to Google Gemini API using model '{target_model}'."
            return False, "Gemini endpoint responded but output was empty."

        except APIError as e:
            code = getattr(e, "code", None)
            msg = str(e)
            if "is no longer available to new users" in msg or (code == 404 and target_model in DEPRECATED_GEMINI_MODELS):
                return False, (
                    f"Gemini model '{target_model}' is no longer available. "
                    f"Please switch to '{DEFAULT_GEMINI_MODEL}' or 'gemini-3.8-flash' in Settings."
                )
            elif code in (401, 403) or "API_KEY_INVALID" in msg or "PERMISSION_DENIED" in msg:
                return False, "Authentication failed: Provided Gemini API key is invalid or unauthorized."
            elif code == 429 or "RESOURCE_EXHAUSTED" in msg:
                return False, "Gemini API rate limit or quota exceeded. Please check your account quota."
            elif code in (503, 504) or "UNAVAILABLE" in msg or "DEADLINE_EXCEEDED" in msg:
                return False, (
                    f"Google Gemini model '{target_model}' is currently experiencing temporary high demand ({code}). "
                    f"Please try again or select '{DEFAULT_GEMINI_MODEL}'."
                )
            return False, f"Gemini API error ({code}): {msg}"
        except Exception as e:
            logger.error("Gemini connection test failed: %s", e)
            return False, f"Connection failed: {e}"

    def _call_gemini_with_retry(
        self,
        contents: str,
        config: Optional[types.GenerateContentConfig] = None,
    ) -> str:
        """Execute a text generation call with exponential backoff on transient errors."""
        client = self._get_client()
        cfg = config or types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.3,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        if getattr(cfg, "thinking_config", None) is None:
            cfg.thinking_config = types.ThinkingConfig(thinking_budget=0)

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=cfg,
                )
                if not response or not response.text:
                    raise TextTranslationError("Gemini generated an empty response.")
                return response.text.strip()

            except APIError as e:
                last_error = e
                code = getattr(e, "code", None)
                msg = str(e)

                if code in (401, 403) or "API_KEY_INVALID" in msg:
                    raise ProviderAuthenticationError(f"Gemini API authentication failed: {msg}") from e
                elif code == 429 or "RESOURCE_EXHAUSTED" in msg:
                    is_daily_quota = any(
                        k in msg
                        for k in (
                            "per day limit exceeded",
                            "PerDay",
                            "quotaValue",
                            "retryDelay",
                            "retry in ",
                            "PerProjectPerModel",
                        )
                    )

                    # If model hit per-model daily quota, attempt automatic fallback to next available model
                    if is_daily_quota or attempt == self.max_retries:
                        self._exhausted_models.add(self.model)
                        fallback_found = False
                        for fb_model in FALLBACK_GEMINI_MODELS:
                            if fb_model != self.model and fb_model not in self._exhausted_models:
                                logger.warning(
                                    "Gemini model '%s' quota exhausted (429). Attempting automatic fallback to '%s'...",
                                    self.model,
                                    fb_model,
                                )
                                self.model = fb_model
                                fallback_found = True
                                break
                        if fallback_found:
                            # Retry immediately with the alternate model
                            continue

                    if attempt < self.max_retries:
                        delay = 2.5 * attempt
                        logger.warning(
                            "Gemini rate limit encountered on '%s'. Retrying in %.1fs (attempt %d/%d)...",
                            self.model,
                            delay,
                            attempt,
                            self.max_retries,
                        )
                        time.sleep(delay)
                        continue

                    # Extract retry delay if available from Google error
                    m_delay = re.search(r"retry in ([0-9a-zA-Z\.\s]+)", msg, re.IGNORECASE)
                    delay_str = f" (please retry in {m_delay.group(1).strip()})" if m_delay else ""
                    clean_msg = (
                        f"Google Gemini Free Tier daily quota or rate limit exceeded on model '{self.model}'{delay_str}. "
                        f"To continue translating immediately without quota limits, select the offline 'NLLB' provider in project settings."
                    )
                    raise RateLimitError(clean_msg) from e
                elif code in (500, 502, 503, 504) or "UNAVAILABLE" in msg or "DEADLINE_EXCEEDED" in msg:
                    if attempt < self.max_retries:
                        delay = 1.5 * attempt
                        logger.warning(
                            "Gemini transient error (%s: %s). Retrying in %.1fs (attempt %d/%d)...",
                            code, msg, delay, attempt, self.max_retries,
                        )
                        time.sleep(delay)
                        continue
                    if code == 504 or "DEADLINE_EXCEEDED" in msg:
                        raise ProviderTimeoutError(f"Gemini deadline exceeded (504): {msg}") from e
                    raise ProviderUnavailableError(f"Gemini service unavailable ({code}): {msg}") from e
                else:
                    raise TextTranslationError(f"Gemini API error ({code}): {msg}") from e

            except (TimeoutError, ConnectionError) as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = 1.5 * attempt
                    logger.warning("Gemini network timeout/connection error: %s. Retrying in %.1fs (attempt %d/%d)...", e, delay, attempt, self.max_retries)
                    time.sleep(delay)
                    continue
                raise ProviderTimeoutError(f"Network timeout contacting Gemini API: {e}") from e
            except Exception as e:
                raise TextTranslationError(f"Unexpected error calling Gemini API: {e}") from e

        raise TextTranslationError(f"Gemini request failed after {self.max_retries} attempts: {last_error}")

    def _translate_single_segment(
        self,
        text: str,
        style: str = "natural",
        context: Optional[str] = None,
        duration: Optional[float] = None,
    ) -> str:
        """Translate a single segment with retry and duration fitting."""
        raw_text = (text or "").strip()
        if not raw_text:
            return ""

        prompt = build_single_translation_prompt(raw_text, style=style, context=context, duration=duration)
        cfg = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.3,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        raw_out = self._call_gemini_with_retry(prompt, config=cfg)
        formatted = KhmerGlossary.align_terminology(raw_text, raw_out)
        formatted = KhmerTextFormatter.format(formatted)
        if duration and duration > 0.0:
            from app.services.dubbing.auto_fit import shorten_khmer_text
            c_lim = max(18, int(duration * 12.0))
            if len(formatted) > c_lim:
                formatted = shorten_khmer_text(formatted, target_char_count=c_lim)
        return formatted

    def _translate_chunk(
        self,
        chunk_texts: List[str],
        style: str = "natural",
        contexts: Optional[List[str]] = None,
        durations: Optional[List[float]] = None,
    ) -> List[str]:
        """Translate a small batch chunk (up to BATCH_CHUNK_SIZE) with structured JSON, falling back to per-segment on error."""
        if not chunk_texts:
            return []

        if len(chunk_texts) == 1:
            dur = durations[0] if (durations and len(durations) > 0) else None
            ctx = contexts[0] if (contexts and len(contexts) > 0) else None
            return [self._translate_single_segment(chunk_texts[0], style=style, context=ctx, duration=dur)]

        # Attempt batch translation with structured JSON output
        try:
            prompt = build_batch_translation_prompt(
                chunk_texts,
                style=style,
                durations=durations,
                contexts=contexts,
            )
            cfg = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.3,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )
            raw_json = self._call_gemini_with_retry(prompt, config=cfg)

            cleaned_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json.strip())
            data = json.loads(cleaned_json)

            if isinstance(data, dict) and "segments" in data:
                data = data["segments"]

            if isinstance(data, list):
                lookup = {item.get("id"): item.get("khmer", "") for item in data if isinstance(item, dict)}
                chunk_results = []
                for idx, eng in enumerate(chunk_texts):
                    if not eng:
                        chunk_results.append("")
                        continue
                    km = lookup.get(idx + 1, "")
                    if not km:
                        dur = durations[idx] if (durations and idx < len(durations)) else None
                        ctx = contexts[idx] if (contexts and idx < len(contexts)) else None
                        km = self._translate_single_segment(eng, style=style, context=ctx, duration=dur)
                    else:
                        km = KhmerGlossary.align_terminology(eng, km)
                        km = KhmerTextFormatter.format(km)
                        if durations and idx < len(durations) and durations[idx] and durations[idx] > 0.0:
                            from app.services.dubbing.auto_fit import shorten_khmer_text
                            c_lim = max(18, int(durations[idx] * 12.0))
                            if len(km) > c_lim:
                                km = shorten_khmer_text(km, target_char_count=c_lim)
                    chunk_results.append(km)
                return chunk_results

            logger.warning("Batch translation JSON output was not a list: %s", raw_json[:100])

        except Exception as e:
            logger.warning(
                "Batch translation failed for chunk of %d segments (%s). Falling back to per-segment translation.",
                len(chunk_texts),
                e,
            )

        # Fallback to per-segment translation for this chunk
        chunk_results = []
        for idx, eng in enumerate(chunk_texts):
            dur = durations[idx] if (durations and idx < len(durations)) else None
            ctx = contexts[idx] if (contexts and idx < len(contexts)) else None
            km = self._translate_single_segment(eng, style=style, context=ctx, duration=dur)
            chunk_results.append(km)

        return chunk_results

    def translate(
        self,
        texts: List[str],
        source_lang: str = "en",
        target_lang: str = "km",
        style: str = "natural",
        contexts: Optional[List[str]] = None,
        durations: Optional[List[float]] = None,
        **kwargs,
    ) -> List[str]:
        """Translate a list of English sentences into Khmer using Gemini with chosen style.

        Segments are chunked into small sub-batches (BATCH_CHUNK_SIZE) with thinking budget=0
        and a 60s timeout to prevent 504 DEADLINE_EXCEEDED errors.
        """
        if not texts:
            return []

        clean_texts = [t.strip() if t else "" for t in texts]
        non_empty = [t for t in clean_texts if t]
        if not non_empty:
            return [""] * len(texts)

        # If translating a single segment
        if len(clean_texts) == 1:
            raw_text = clean_texts[0]
            if not raw_text:
                return [""]
            seg_dur = durations[0] if (durations and len(durations) > 0) else None
            seg_ctx = contexts[0] if (contexts and len(contexts) > 0) else None
            return [self._translate_single_segment(raw_text, style=style, context=seg_ctx, duration=seg_dur)]

        # Multiple segments: chunk into sub-batches of BATCH_CHUNK_SIZE
        results: List[str] = []
        chunk_size = self.BATCH_CHUNK_SIZE

        for i in range(0, len(clean_texts), chunk_size):
            if i > 0:
                # Brief pacing pause between chunks to respect free-tier RPM limits
                time.sleep(0.5)
            chunk_texts = clean_texts[i : i + chunk_size]
            chunk_durations = durations[i : i + chunk_size] if durations else None
            chunk_contexts = contexts[i : i + chunk_size] if contexts else None

            chunk_results = self._translate_chunk(
                chunk_texts=chunk_texts,
                style=style,
                contexts=chunk_contexts,
                durations=chunk_durations,
            )
            results.extend(chunk_results)

        return results

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
        """Improve an existing Khmer translation segment using context, style, and duration constraints."""
        khmer_src = current_khmer if current_khmer is not None else (current_khmer_text or "")
        p_text = prev_text or context
        prompt = build_ai_improve_prompt(
            english_text=english_text,
            current_khmer=khmer_src,
            style=style,
            prev_text=p_text,
            next_text=next_text,
            target_duration=target_duration,
            custom_prompt=custom_prompt,
            context=context,
        )

        cfg = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.3,
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        raw_json = self._call_gemini_with_retry(prompt, config=cfg)

        try:
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json.strip())
            parsed = json.loads(cleaned)
            improved = parsed.get("improved_khmer", "").strip()
            explanation = parsed.get("explanation", "Improved Khmer translation phrasing.").strip()
        except Exception as e:
            logger.warning("Could not parse AI improve JSON response (%s): %s", e, raw_json)
            improved = raw_json
            explanation = "Revised for natural Khmer phrasing."

        improved = KhmerGlossary.align_terminology(english_text, improved)
        improved = KhmerTextFormatter.format(improved)

        return AIImprovementResult(
            original_text=english_text,
            current_khmer_text=khmer_src,
            improved_khmer_text=improved,
            explanation=explanation,
            style=style,
            provider="gemini",
            model=self.model,
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
        khmer_src = current_khmer if current_khmer is not None else (current_khmer_text or "")
        p_text = prev_text or context
        prompt = build_alternatives_prompt(
            english_text=english_text,
            current_khmer=khmer_src,
            prev_text=p_text,
            next_text=next_text,
            target_duration=target_duration,
            context=context,
        )

        cfg = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.4,
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        raw_json = self._call_gemini_with_retry(prompt, config=cfg)

        alternatives: List[TranslationAlternative] = []
        try:
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json.strip())
            data = json.loads(cleaned)
            items = data.get("alternatives", [])
            for item in items:
                style_key = item.get("style", "natural")
                label = item.get("label", TRANSLATION_STYLES.get(style_key, {}).get("label", "Alternative"))
                raw_km = item.get("khmer_text", "")
                km = KhmerGlossary.align_terminology(english_text, raw_km)
                km = KhmerTextFormatter.format(km)
                expl = item.get("explanation")
                alternatives.append(
                    TranslationAlternative(
                        style=style_key,
                        label=label,
                        khmer_text=km,
                        explanation=expl,
                    )
                )
        except Exception as e:
            logger.warning("Could not parse alternatives JSON response (%s): %s", e, raw_json)

        # Fallback if structure was not returned
        if not alternatives:
            alt_styles = [("natural", "Natural Spoken"), ("simple", "Simple & Clear"), ("short", "Short for Dubbing")]
            for s_key, s_lbl in alt_styles:
                res = self.improve_translation(
                    english_text=english_text,
                    current_khmer=current_khmer,
                    style=s_key,
                    prev_text=prev_text,
                    next_text=next_text,
                    target_duration=target_duration,
                )
                alternatives.append(
                    TranslationAlternative(
                        style=s_key,
                        label=s_lbl,
                        khmer_text=res.improved_khmer_text,
                        explanation=res.explanation,
                    )
                )

        return alternatives
