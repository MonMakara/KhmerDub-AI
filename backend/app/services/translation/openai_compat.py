import json
import logging
import os
import re
import time
from typing import List, Optional, Tuple, Dict, Any

import httpx

from app.core.credentials import get_api_key, get_provider_credentials
from app.services.translation.base import (
    TranslationProvider,
    TranslationAlternative,
    AIImprovementResult,
)
from app.services.translation.exceptions import (
    TranslationError,
    ProviderAuthenticationError,
    RateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.services.translation.formatter import KhmerTextFormatter
from app.services.translation.glossary import KhmerGlossary
from app.services.translation.prompts import (
    SYSTEM_INSTRUCTION,
    TRANSLATION_STYLES,
    build_single_translation_prompt,
    build_batch_translation_prompt,
    build_ai_improve_prompt,
    build_alternatives_prompt,
)

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
SUPPORTED_OPENAI_MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"]
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"

DEFAULT_CUSTOM_MODEL = "deepseek-chat"
SUPPORTED_CUSTOM_MODELS = [
    "deepseek-chat",
    "deepseek-reasoner",
    "llama-3.3-70b-versatile",
    "qwen2.5-72b-instruct",
    "mistral-large-latest",
]


class OpenAITranslationProvider(TranslationProvider):
    """Translation provider for OpenAI and any OpenAI-compatible API endpoint.

    Supports:
    - Official OpenAI (gpt-4o-mini, gpt-4o, etc.)
    - Custom OpenAI-compatible endpoints (DeepSeek, Groq, OpenRouter, Together AI, Ollama, vLLM)
    """

    def __init__(
        self,
        provider_id: str = "openai",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 45.0,
        max_retries: int = 3,
    ):
        self.provider_id = (provider_id or "openai").strip().lower()
        self.timeout = timeout
        self.max_retries = max(1, max_retries)

        # Retrieve stored or env credentials
        stored = get_provider_credentials(self.provider_id)
        self.api_key = api_key or stored.get("api_key")

        # Base URL resolution
        if base_url:
            self.base_url = base_url.strip().rstrip("/")
        elif stored.get("base_url"):
            self.base_url = stored["base_url"].strip().rstrip("/")
        else:
            self.base_url = DEFAULT_OPENAI_BASE_URL

        # Model resolution
        if model:
            self.model = model.strip()
        elif stored.get("model"):
            self.model = stored["model"].strip()
        elif self.provider_id == "custom":
            self.model = DEFAULT_CUSTOM_MODEL
        else:
            self.model = DEFAULT_OPENAI_MODEL

    @property
    def name(self) -> str:
        return "OpenAI" if self.provider_id == "openai" else "Custom AI"

    def _get_headers(self, key_override: Optional[str] = None) -> Dict[str, str]:
        key = key_override or self.api_key or get_api_key(self.provider_id)
        if not key:
            raise ProviderAuthenticationError(
                f"{self.name} API key is missing. Please configure credentials in Settings."
            )
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "KhmerDub-AI/1.0",
        }

    def test_connection(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Verify API key, base URL, and model connectivity."""
        effective_key = api_key or self.api_key or get_api_key(self.provider_id)
        if not effective_key:
            return False, f"{self.name} API key is required. Please provide an API key."

        effective_base_url = (base_url or self.base_url).strip().rstrip("/")
        effective_model = (model or self.model).strip()
        url = f"{effective_base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {effective_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": effective_model,
            "messages": [
                {"role": "user", "content": "Respond strictly with the single word 'OK'."}
            ],
            "max_tokens": 10,
            "temperature": 0.0,
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, headers=headers, json=payload)

            if resp.status_code == 200:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return (
                        True,
                        f"Successfully connected to {self.name} ({effective_model}) at '{effective_base_url}'.",
                    )
                return False, f"{self.name} endpoint responded with empty content."

            elif resp.status_code in (401, 403):
                return False, f"Authentication failed (HTTP {resp.status_code}): API key is invalid or unauthorized."
            elif resp.status_code == 429:
                return False, "Rate limit or quota exceeded. Please check your API credits/quota."
            elif resp.status_code == 404:
                return (
                    False,
                    f"Endpoint not found (HTTP 404). Please verify model '{effective_model}' and base URL '{effective_base_url}'.",
                )
            else:
                err_msg = resp.text[:200]
                return False, f"API test returned HTTP {resp.status_code}: {err_msg}"

        except httpx.TimeoutException:
            return False, f"Connection timed out while contacting '{effective_base_url}'."
        except httpx.ConnectError as e:
            return False, f"Could not connect to server at '{effective_base_url}'. Error: {e}"
        except Exception as e:
            logger.error("Connection test failed: %s", e)
            return False, f"Connection test failed: {e}"

    def _call_api_with_retry(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = False,
    ) -> str:
        """Execute chat completion request with exponential backoff on transient errors."""
        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, headers=headers, json=payload)

                if resp.status_code == 200:
                    data = resp.json()
                    content = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    if not content or not content.strip():
                        raise TranslationError("API generated an empty response.")
                    return content.strip()

                elif resp.status_code in (401, 403):
                    raise ProviderAuthenticationError(
                        f"{self.name} authentication failed: API key is invalid or expired."
                    )
                elif resp.status_code == 429:
                    raise RateLimitError(
                        f"{self.name} rate limit or quota exceeded. Please wait or check your account."
                    )
                elif resp.status_code >= 500:
                    last_error = ProviderUnavailableError(
                        f"{self.name} server error (HTTP {resp.status_code}): {resp.text[:200]}"
                    )
                else:
                    # If json_mode was rejected, retry once without response_format
                    if json_mode and "response_format" in payload and resp.status_code == 400:
                        del payload["response_format"]
                        continue
                    raise TranslationError(
                        f"{self.name} request failed (HTTP {resp.status_code}): {resp.text[:200]}"
                    )

            except httpx.TimeoutException as e:
                last_error = ProviderTimeoutError(
                    f"{self.name} request timed out after {self.timeout}s: {e}"
                )
            except httpx.ConnectError as e:
                last_error = ProviderUnavailableError(
                    f"Cannot reach {self.name} at '{self.base_url}': {e}"
                )
            except (ProviderAuthenticationError, RateLimitError):
                raise
            except Exception as e:
                last_error = e

            if attempt < self.max_retries:
                backoff = 1.5 ** attempt
                logger.warning(
                    "%s attempt %d/%d failed (%s). Retrying in %.1fs...",
                    self.name,
                    attempt,
                    self.max_retries,
                    last_error,
                    backoff,
                )
                time.sleep(backoff)

        raise last_error or TranslationError(f"{self.name} translation failed after {self.max_retries} attempts.")

    def translate(
        self,
        texts: List[str],
        source_lang: str = "en",
        target_lang: str = "km",
        style: str = "standard",
        contexts: Optional[List[str]] = None,
        **kwargs,
    ) -> List[str]:
        """Translate a batch or single list of English texts into Khmer."""
        if not texts:
            return []

        clean_texts = [t.strip() if t else "" for t in texts]
        non_empty = [t for t in clean_texts if t]
        if not non_empty:
            return [""] * len(texts)

        results = []

        # Single segment fast path
        if len(clean_texts) == 1:
            raw_text = clean_texts[0]
            if not raw_text:
                return [""]
            prompt = build_single_translation_prompt(raw_text, style=style)
            messages = [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ]
            raw_out = self._call_api_with_retry(messages, json_mode=False)
            formatted = KhmerGlossary.align_terminology(raw_text, raw_out)
            formatted = KhmerTextFormatter.format(formatted)
            return [formatted]

        # Batch translation
        prompt = build_batch_translation_prompt(clean_texts, style=style)
        messages = [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": prompt},
        ]
        raw_json = self._call_api_with_retry(messages, json_mode=True)

        try:
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json.strip())
            data = json.loads(cleaned)
            if isinstance(data, list):
                lookup = {item.get("id"): item.get("khmer", "") for item in data}
                for i, eng in enumerate(clean_texts):
                    km = lookup.get(i + 1, "")
                    km = KhmerGlossary.align_terminology(eng, km)
                    km = KhmerTextFormatter.format(km)
                    results.append(km)
                return results
            elif isinstance(data, dict) and "segments" in data:
                lookup = {item.get("id"): item.get("khmer", "") for item in data["segments"]}
                for i, eng in enumerate(clean_texts):
                    km = lookup.get(i + 1, "")
                    km = KhmerGlossary.align_terminology(eng, km)
                    km = KhmerTextFormatter.format(km)
                    results.append(km)
                return results
        except Exception as e:
            logger.warning("Batch JSON parsing failed (%s). Falling back to per-segment translation.", e)

        # Fallback to per-segment
        for t in clean_texts:
            if not t:
                results.append("")
                continue
            p = build_single_translation_prompt(t, style=style)
            msgs = [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": p},
            ]
            out = self._call_api_with_retry(msgs, json_mode=False)
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
        """Improve an existing Khmer translation segment using context and duration constraints."""
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

        messages = [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": prompt},
        ]
        raw_json = self._call_api_with_retry(messages, json_mode=True)

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
            provider=self.provider_id,
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

        messages = [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": prompt},
        ]
        raw_json = self._call_api_with_retry(messages, json_mode=True)

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

        # Fallback if structure was missing
        if not alternatives:
            alt_styles = [("natural", "Natural Spoken"), ("simple", "Simple & Clear"), ("short", "Short for Dubbing")]
            for s_key, s_lbl in alt_styles:
                res = self.improve_translation(
                    english_text=english_text,
                    current_khmer=khmer_src,
                    style=s_key,
                    prev_text=p_text,
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
