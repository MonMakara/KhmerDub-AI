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

DEFAULT_CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
SUPPORTED_CLAUDE_MODELS = [
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
]
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class ClaudeTranslationProvider(TranslationProvider):
    """Translation provider for Anthropic Claude models."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 45.0,
        max_retries: int = 3,
    ):
        self.timeout = timeout
        self.max_retries = max(1, max_retries)

        stored = get_provider_credentials("claude")
        self.api_key = api_key or stored.get("api_key")
        self.model = (model or stored.get("model") or DEFAULT_CLAUDE_MODEL).strip()

    @property
    def name(self) -> str:
        return "Anthropic Claude"

    def _get_headers(self, key_override: Optional[str] = None) -> Dict[str, str]:
        key = key_override or self.api_key or get_api_key("claude")
        if not key:
            raise ProviderAuthenticationError(
                "Anthropic Claude API key is missing. Please configure credentials in Settings."
            )
        return {
            "x-api-key": key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
            "User-Agent": "KhmerDub-AI/1.0",
        }

    def test_connection(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Verify Claude API key and model connectivity."""
        effective_key = api_key or self.api_key or get_api_key("claude")
        if not effective_key:
            return False, "Anthropic Claude API key is required. Please provide an API key."

        effective_model = (model or self.model).strip()
        headers = {
            "x-api-key": effective_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        payload = {
            "model": effective_model,
            "max_tokens": 10,
            "messages": [
                {"role": "user", "content": "Respond strictly with the single word 'OK'."}
            ],
            "temperature": 0.0,
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(CLAUDE_API_URL, headers=headers, json=payload)

            if resp.status_code == 200:
                data = resp.json()
                content = ""
                for part in data.get("content", []):
                    if part.get("type") == "text":
                        content += part.get("text", "")
                if content:
                    return (
                        True,
                        f"Successfully connected to Anthropic Claude ({effective_model}).",
                    )
                return False, "Claude endpoint responded with empty content."

            elif resp.status_code in (401, 403):
                return False, f"Authentication failed (HTTP {resp.status_code}): API key is invalid or unauthorized."
            elif resp.status_code in (429, 529):
                return False, "Rate limit or Claude capacity reached. Please check your Anthropic account quota."
            elif resp.status_code == 404:
                return False, f"Model '{effective_model}' not found on Anthropic API."
            else:
                err_msg = resp.text[:200]
                return False, f"Claude API test returned HTTP {resp.status_code}: {err_msg}"

        except httpx.TimeoutException:
            return False, "Connection to Anthropic Claude timed out."
        except httpx.ConnectError as e:
            return False, f"Could not connect to Anthropic API: {e}"
        except Exception as e:
            logger.error("Claude connection test failed: %s", e)
            return False, f"Connection test failed: {e}"

    def _call_claude_with_retry(
        self,
        user_prompt: str,
        system_instruction: str = SYSTEM_INSTRUCTION,
    ) -> str:
        """Call Claude Messages API with exponential backoff on transient errors."""
        headers = self._get_headers()
        payload = {
            "model": self.model,
            "max_tokens": 1500,
            "system": system_instruction,
            "messages": [
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,
        }

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(CLAUDE_API_URL, headers=headers, json=payload)

                if resp.status_code == 200:
                    data = resp.json()
                    content = ""
                    for part in data.get("content", []):
                        if part.get("type") == "text":
                            content += part.get("text", "")
                    if not content or not content.strip():
                        raise TranslationError("Claude generated an empty response.")
                    return content.strip()

                elif resp.status_code in (401, 403):
                    raise ProviderAuthenticationError(
                        "Anthropic Claude authentication failed: API key is invalid."
                    )
                elif resp.status_code in (429, 529):
                    raise RateLimitError(
                        "Anthropic Claude rate limit or capacity reached. Please wait or check your account."
                    )
                elif resp.status_code >= 500:
                    last_error = ProviderUnavailableError(
                        f"Claude server error (HTTP {resp.status_code}): {resp.text[:200]}"
                    )
                else:
                    raise TranslationError(
                        f"Claude request failed (HTTP {resp.status_code}): {resp.text[:200]}"
                    )

            except httpx.TimeoutException as e:
                last_error = ProviderTimeoutError(
                    f"Claude request timed out after {self.timeout}s: {e}"
                )
            except httpx.ConnectError as e:
                last_error = ProviderUnavailableError(f"Cannot reach Anthropic API: {e}")
            except (ProviderAuthenticationError, RateLimitError):
                raise
            except Exception as e:
                last_error = e

            if attempt < self.max_retries:
                backoff = 1.5 ** attempt
                logger.warning(
                    "Claude attempt %d/%d failed (%s). Retrying in %.1fs...",
                    attempt,
                    self.max_retries,
                    last_error,
                    backoff,
                )
                time.sleep(backoff)

        raise last_error or TranslationError(f"Claude translation failed after {self.max_retries} attempts.")

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

        if len(clean_texts) == 1:
            raw_text = clean_texts[0]
            if not raw_text:
                return [""]
            prompt = build_single_translation_prompt(raw_text, style=style)
            raw_out = self._call_claude_with_retry(prompt)
            formatted = KhmerGlossary.align_terminology(raw_text, raw_out)
            formatted = KhmerTextFormatter.format(formatted)
            return [formatted]

        # Batch translation
        prompt = build_batch_translation_prompt(clean_texts, style=style)
        raw_json = self._call_claude_with_retry(prompt)

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
            logger.warning("Claude batch JSON parsing failed (%s). Falling back to per-segment translation.", e)

        # Fallback to per-segment
        for t in clean_texts:
            if not t:
                results.append("")
                continue
            p = build_single_translation_prompt(t, style=style)
            out = self._call_claude_with_retry(p)
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

        raw_json = self._call_claude_with_retry(prompt)

        try:
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json.strip())
            parsed = json.loads(cleaned)
            improved = parsed.get("improved_khmer", "").strip()
            explanation = parsed.get("explanation", "Improved Khmer translation phrasing.").strip()
        except Exception as e:
            logger.warning("Could not parse Claude AI improve JSON response (%s): %s", e, raw_json)
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
            provider="claude",
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

        raw_json = self._call_claude_with_retry(prompt)

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
