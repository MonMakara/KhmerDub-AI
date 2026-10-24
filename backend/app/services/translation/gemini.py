import json
import logging
import re
import time
from typing import List, Optional, Tuple

from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.core.config import settings
from app.core.credentials import get_api_key
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

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
SUPPORTED_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]


class GeminiTranslationProvider(TranslationProvider):
    """Google Gemini AI translation provider using the official google-genai SDK.

    Provides high-quality English-to-Khmer translation, contextual improvements,
    natural conversational rewriting, and alternatives tailored for video dubbing.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self._explicit_key = api_key
        self.model = model or getattr(settings, "GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self.timeout = timeout
        self.max_retries = max_retries

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
        return genai.Client(api_key=key)

    def test_connection(self, api_key: Optional[str] = None) -> Tuple[bool, str]:
        """Test API key authentication and network connectivity to Google Gemini."""
        key = api_key or self.api_key
        if not key:
            return False, "Google Gemini API key is missing. Please enter a valid API key."

        try:
            client = genai.Client(api_key=key)
            # Lightweight prompt to verify credentials and model accessibility
            response = client.models.generate_content(
                model=self.model,
                contents="Ping. Respond with 'OK'.",
                config=types.GenerateContentConfig(
                    max_output_tokens=10,
                    temperature=0.0,
                ),
            )
            if response and response.text:
                return True, f"Successfully connected to Google Gemini API using model '{self.model}'."
            return False, "Gemini endpoint responded but output was empty."

        except APIError as e:
            code = getattr(e, "code", None)
            msg = str(e)
            if code in (401, 403) or "API_KEY_INVALID" in msg or "PERMISSION_DENIED" in msg:
                return False, "Authentication failed: Provided Gemini API key is invalid or unauthorized."
            elif code == 429 or "RESOURCE_EXHAUSTED" in msg:
                return False, "Gemini API rate limit or quota exceeded. Please check your account quota."
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
        )

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
                    if attempt < self.max_retries:
                        delay = 2.0 * attempt
                        logger.warning("Gemini rate limit encountered. Retrying in %.1fs...", delay)
                        time.sleep(delay)
                        continue
                    raise RateLimitError(f"Gemini API quota or rate limit exceeded: {msg}") from e
                elif code in (500, 503) or "UNAVAILABLE" in msg:
                    if attempt < self.max_retries:
                        delay = 1.5 * attempt
                        time.sleep(delay)
                        continue
                    raise ProviderUnavailableError(f"Gemini service unavailable: {msg}") from e
                else:
                    raise TextTranslationError(f"Gemini API error ({code}): {msg}") from e

            except (TimeoutError, ConnectionError) as e:
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(1.5 * attempt)
                    continue
                raise ProviderTimeoutError(f"Network timeout contacting Gemini API: {e}") from e
            except Exception as e:
                raise TextTranslationError(f"Unexpected error calling Gemini API: {e}") from e

        raise TextTranslationError(f"Gemini request failed after {self.max_retries} attempts: {last_error}")

    def translate(
        self,
        texts: List[str],
        source_lang: str = "en",
        target_lang: str = "km",
        style: str = "natural",
    ) -> List[str]:
        """Translate a list of English sentences into Khmer using Gemini with chosen style."""
        if not texts:
            return []

        clean_texts = [t.strip() for t in texts]
        results = []

        # If translating a single segment
        if len(clean_texts) == 1:
            raw_text = clean_texts[0]
            if not raw_text:
                return [""]
            prompt = build_single_translation_prompt(raw_text, style=style)
            cfg = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.3,
            )
            raw_out = self._call_gemini_with_retry(prompt, config=cfg)
            formatted = KhmerGlossary.align_terminology(raw_text, raw_out)
            formatted = KhmerTextFormatter.format(formatted)
            return [formatted]

        # For multiple segments, translate with structured batch prompt
        prompt = build_batch_translation_prompt(clean_texts, style=style)
        cfg = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.3,
            response_mime_type="application/json",
        )
        raw_json = self._call_gemini_with_retry(prompt, config=cfg)

        try:
            # Strip markdown if present
            cleaned_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json.strip())
            data = json.loads(cleaned_json)
            if isinstance(data, list):
                lookup = {item.get("id"): item.get("khmer", "") for item in data}
                for i, eng in enumerate(clean_texts):
                    km = lookup.get(i + 1, "")
                    km = KhmerGlossary.align_terminology(eng, km)
                    km = KhmerTextFormatter.format(km)
                    results.append(km)
                return results
        except Exception as e:
            logger.warning("Batch JSON parsing failed (%s). Falling back to per-segment translation.", e)

        # Fallback to per-segment translation
        for t in clean_texts:
            if not t:
                results.append("")
                continue
            p = build_single_translation_prompt(t, style=style)
            out = self._call_gemini_with_retry(p)
            out = KhmerGlossary.align_terminology(t, out)
            out = KhmerTextFormatter.format(out)
            results.append(out)

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
