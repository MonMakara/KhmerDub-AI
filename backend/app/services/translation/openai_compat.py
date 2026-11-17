import json
import logging
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

DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
SUPPORTED_GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]
DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"

DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
SUPPORTED_DEEPSEEK_MODELS = [
    "deepseek-chat",
    "deepseek-reasoner",
]
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

DEFAULT_CUSTOM_MODEL = "deepseek-chat"
SUPPORTED_CUSTOM_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
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

    BATCH_CHUNK_SIZE: int = 12

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
        elif self.provider_id == "groq":
            self.base_url = DEFAULT_GROQ_BASE_URL
        elif self.provider_id == "deepseek":
            self.base_url = DEFAULT_DEEPSEEK_BASE_URL
        else:
            self.base_url = DEFAULT_OPENAI_BASE_URL

        # Model resolution
        if model:
            self.model = model.strip()
        elif stored.get("model"):
            self.model = stored["model"].strip()
        elif self.provider_id == "groq":
            self.model = DEFAULT_GROQ_MODEL
        elif self.provider_id == "deepseek":
            self.model = DEFAULT_DEEPSEEK_MODEL
        elif self.provider_id == "custom":
            self.model = DEFAULT_CUSTOM_MODEL
        else:
            self.model = DEFAULT_OPENAI_MODEL

    @property
    def name(self) -> str:
        if self.provider_id == "openai":
            return "OpenAI"
        if self.provider_id == "groq":
            return "Groq"
        if self.provider_id == "deepseek":
            return "DeepSeek"
        return "Custom AI"

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
            "max_tokens": 80,
            "temperature": 0.0,
        }

        try:
            with httpx.Client(timeout=45.0) as client:
                resp = client.post(url, headers=headers, json=payload)

            if resp.status_code == 200:
                data = resp.json()
                msg = data.get("choices", [{}])[0].get("message", {})
                content = (msg.get("content") or "").strip()
                reasoning = (msg.get("reasoning") or "").strip()
                if content or reasoning:
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
                    # If json_mode was rejected by custom endpoint, retry without response_format
                    if json_mode and "response_format" in payload and resp.status_code in (400, 422):
                        logger.info("%s does not support response_format json_object. Retrying without it.", self.name)
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

    def _translate_single_segment(
        self,
        raw_text: str,
        style: str = "natural",
        context: Optional[str] = None,
        duration: Optional[float] = None,
    ) -> str:
        """Translate a single segment with optional surrounding context and duration constraints."""
        if not raw_text or not raw_text.strip():
            return ""

        prompt = build_single_translation_prompt(
            raw_text.strip(),
            style=style,
            context=context,
            duration=duration,
        )
        messages = [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": prompt},
        ]
        raw_out = self._call_api_with_retry(messages, json_mode=False)

        # Handle LLMs that wrap single responses in JSON or markdown blocks
        clean_out = raw_out.strip()
        clean_out = re.sub(r"^```(?:json|[a-z]+)?\s*|\s*```$", "", clean_out).strip()
        if clean_out.startswith(("{", "[", '"')):
            try:
                parsed = json.loads(clean_out)
                if isinstance(parsed, list) and len(parsed) > 0:
                    if isinstance(parsed[0], dict):
                        clean_out = parsed[0].get("khmer") or parsed[0].get("text") or clean_out
                    elif isinstance(parsed[0], str):
                        clean_out = parsed[0]
                elif isinstance(parsed, dict):
                    clean_out = parsed.get("khmer") or parsed.get("text") or clean_out
                elif isinstance(parsed, str):
                    clean_out = parsed
            except Exception:
                pass
        clean_out = clean_out.strip('"\'')

        formatted = KhmerGlossary.align_terminology(raw_text, clean_out)
        formatted = KhmerTextFormatter.format(formatted)
        if duration and duration > 0.0:
            from app.services.dubbing.auto_fit import shorten_khmer_text
            c_lim = max(18, int(duration * 12.0))
            if len(formatted) > c_lim:
                formatted = shorten_khmer_text(formatted, target_char_count=c_lim)
        return formatted

    def translate(
        self,
        texts: List[str],
        source_lang: str = "en",
        target_lang: str = "km",
        style: str = "standard",
        contexts: Optional[List[str]] = None,
        durations: Optional[List[float]] = None,
        **kwargs,
    ) -> List[str]:
        """Translate a batch or single list of English texts into Khmer with transcript context and chunking."""
        if not texts:
            return []

        clean_texts = [t.strip() if t else "" for t in texts]
        non_empty = [t for t in clean_texts if t]
        if not non_empty:
            return [""] * len(texts)

        # Single segment fast path
        if len(clean_texts) == 1:
            raw_text = clean_texts[0]
            seg_dur = durations[0] if (durations and len(durations) > 0) else None
            seg_ctx = contexts[0] if (contexts and len(contexts) > 0) else None
            return [self._translate_single_segment(raw_text, style=style, context=seg_ctx, duration=seg_dur)]

        results: List[str] = []
        chunk_size = self.BATCH_CHUNK_SIZE

        # Process in chunks of BATCH_CHUNK_SIZE to maintain reliability across custom endpoints
        for i in range(0, len(clean_texts), chunk_size):
            chunk_texts = clean_texts[i : i + chunk_size]
            chunk_durations = durations[i : i + chunk_size] if durations else None
            chunk_contexts = contexts[i : i + chunk_size] if contexts else None

            # Skip translation if all items in chunk are empty
            if not any(chunk_texts):
                results.extend([""] * len(chunk_texts))
                continue

            prompt = build_batch_translation_prompt(
                chunk_texts,
                style=style,
                durations=chunk_durations,
                contexts=chunk_contexts,
            )
            messages = [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ]

            chunk_parsed = False
            try:
                raw_json = self._call_api_with_retry(messages, json_mode=True)
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json.strip())
                data = json.loads(cleaned)

                items = None
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict) and "segments" in data and isinstance(data["segments"], list):
                    items = data["segments"]

                if items is not None:
                    lookup = {item.get("id"): item.get("khmer", "") for item in items if isinstance(item, dict)}
                    for idx, eng in enumerate(chunk_texts):
                        if not eng:
                            results.append("")
                            continue
                        km = lookup.get(idx + 1, "")
                        if not km:
                            # Fallback for single missing item in JSON
                            ctx = chunk_contexts[idx] if (chunk_contexts and idx < len(chunk_contexts)) else None
                            dur = chunk_durations[idx] if (chunk_durations and idx < len(chunk_durations)) else None
                            km = self._translate_single_segment(eng, style=style, context=ctx, duration=dur)
                        else:
                            km = KhmerGlossary.align_terminology(eng, km)
                            km = KhmerTextFormatter.format(km)
                            if chunk_durations and idx < len(chunk_durations) and chunk_durations[idx] and chunk_durations[idx] > 0.0:
                                from app.services.dubbing.auto_fit import shorten_khmer_text
                                c_lim = max(18, int(chunk_durations[idx] * 12.0))
                                if len(km) > c_lim:
                                    km = shorten_khmer_text(km, target_char_count=c_lim)
                        results.append(km)
                    chunk_parsed = True
            except Exception as e:
                logger.warning(
                    "%s batch chunk translation failed (%s). Falling back to per-segment for this chunk.",
                    self.name,
                    e,
                )

            # Per-segment fallback if batch parsing failed for this chunk
            if not chunk_parsed:
                for idx, eng in enumerate(chunk_texts):
                    if not eng:
                        results.append("")
                        continue
                    dur = chunk_durations[idx] if (chunk_durations and idx < len(chunk_durations)) else None
                    ctx = chunk_contexts[idx] if (chunk_contexts and idx < len(chunk_contexts)) else None
                    km = self._translate_single_segment(eng, style=style, context=ctx, duration=dur)
                    results.append(km)

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
