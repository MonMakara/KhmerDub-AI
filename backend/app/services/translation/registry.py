import logging
from typing import Dict, List, Optional, Any, Tuple

from app.core.credentials import is_api_key_configured, get_masked_api_key
from app.services.translation.base import TranslationProvider
from app.services.translation.nllb import NLLBTranslationProvider
from app.services.translation.gemini import (
    GeminiTranslationProvider,
    DEFAULT_GEMINI_MODEL,
    SUPPORTED_GEMINI_MODELS,
)

logger = logging.getLogger(__name__)

SUPPORTED_TRANSLATION_PROVIDERS: List[Dict[str, Any]] = [
    {
        "id": "nllb",
        "name": "Meta NLLB-200",
        "type": "local",
        "description": "Free, locally runnable neural machine translation model on CPU. No API key required, zero usage charges.",
        "requires_api_key": False,
        "supports_styles": False,
        "supports_alternatives": False,
        "default_model": "facebook/nllb-200-distilled-600M",
        "available_models": ["facebook/nllb-200-distilled-600M"],
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "type": "cloud_llm",
        "description": "Google's advanced multimodal AI. Delivers natural spoken Khmer, style adaptation, and video dubbing time-fitting.",
        "requires_api_key": True,
        "supports_styles": True,
        "supports_alternatives": True,
        "default_model": DEFAULT_GEMINI_MODEL,
        "available_models": SUPPORTED_GEMINI_MODELS,
    },
]

DEFAULT_TRANSLATION_PROVIDER = "nllb"
DEFAULT_TRANSLATION_STYLE = "natural"


def list_translation_providers() -> List[Dict[str, Any]]:
    """Return all translation providers enriched with credential configuration status."""
    providers = []
    for p in SUPPORTED_TRANSLATION_PROVIDERS:
        item = dict(p)
        if p["requires_api_key"]:
            item["is_configured"] = is_api_key_configured(p["id"])
            item["masked_key"] = get_masked_api_key(p["id"])
        else:
            item["is_configured"] = True
            item["masked_key"] = None
        providers.append(item)
    return providers


def validate_translation_provider(provider_name: str) -> bool:
    """Validate if the given provider ID is recognized and supported."""
    p_norm = (provider_name or "").strip().lower()
    return any(p["id"] == p_norm for p in SUPPORTED_TRANSLATION_PROVIDERS)


def get_translation_provider(
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs,
) -> TranslationProvider:
    """Factory to retrieve a configured TranslationProvider instance by name."""
    norm = (provider_name or DEFAULT_TRANSLATION_PROVIDER).strip().lower()

    if norm == "nllb":
        return NLLBTranslationProvider(**kwargs)
    elif norm == "gemini":
        return GeminiTranslationProvider(api_key=api_key, model=model, **kwargs)
    else:
        raise ValueError(
            f"Unsupported translation provider '{provider_name}'. Supported providers: 'nllb', 'gemini'"
        )


def test_provider_connection(
    provider_name: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Tuple[bool, str]:
    """Test connection and authentication for a specific translation provider."""
    norm = (provider_name or "").strip().lower()
    if norm == "nllb":
        # NLLB is a local model, verify environment
        return True, "Meta NLLB-200 local provider is available."
    elif norm == "gemini":
        provider = GeminiTranslationProvider(api_key=api_key, model=model)
        return provider.test_connection(api_key=api_key)
    else:
        return False, f"Unknown translation provider '{provider_name}'."
