import logging
from typing import Dict, List, Optional, Any, Tuple

from app.core.credentials import (
    is_api_key_configured,
    get_masked_api_key,
    get_provider_credentials,
)
from app.services.translation.base import TranslationProvider
from app.services.translation.nllb import NLLBTranslationProvider
from app.services.translation.gemini import (
    GeminiTranslationProvider,
    DEFAULT_GEMINI_MODEL,
    SUPPORTED_GEMINI_MODELS,
)
from app.services.translation.openai_compat import (
    OpenAITranslationProvider,
    DEFAULT_OPENAI_MODEL,
    SUPPORTED_OPENAI_MODELS,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_GROQ_MODEL,
    SUPPORTED_GROQ_MODELS,
    DEFAULT_GROQ_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    SUPPORTED_DEEPSEEK_MODELS,
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_CUSTOM_MODEL,
    SUPPORTED_CUSTOM_MODELS,
)
from app.services.translation.claude import (
    ClaudeTranslationProvider,
    DEFAULT_CLAUDE_MODEL,
    SUPPORTED_CLAUDE_MODELS,
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
        "id": "groq",
        "name": "Groq",
        "type": "cloud_llm",
        "description": "Ultra-fast LPU inference (openai/gpt-oss-120b, openai/gpt-oss-20b, qwen/qwen3.8-27b). Free tier with near-instant Khmer translation.",
        "requires_api_key": True,
        "requires_base_url": False,
        "supports_styles": True,
        "supports_alternatives": True,
        "default_model": DEFAULT_GROQ_MODEL,
        "available_models": SUPPORTED_GROQ_MODELS,
        "default_base_url": DEFAULT_GROQ_BASE_URL,
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "type": "cloud_llm",
        "description": "DeepSeek-V3 and DeepSeek-R1 (deepseek-chat, deepseek-reasoner). Extremely cost-effective and capable models.",
        "requires_api_key": True,
        "requires_base_url": False,
        "supports_styles": True,
        "supports_alternatives": True,
        "default_model": DEFAULT_DEEPSEEK_MODEL,
        "available_models": SUPPORTED_DEEPSEEK_MODELS,
        "default_base_url": DEFAULT_DEEPSEEK_BASE_URL,
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
    {
        "id": "openai",
        "name": "OpenAI",
        "type": "cloud_llm",
        "description": "OpenAI GPT models (GPT-4o, GPT-4o-mini). High accuracy Khmer translations with fine-grained styling and video dubbing constraints.",
        "requires_api_key": True,
        "supports_styles": True,
        "supports_alternatives": True,
        "default_model": DEFAULT_OPENAI_MODEL,
        "available_models": SUPPORTED_OPENAI_MODELS,
        "default_base_url": DEFAULT_OPENAI_BASE_URL,
    },
    {
        "id": "claude",
        "name": "Anthropic Claude",
        "type": "cloud_llm",
        "description": "Anthropic Claude 3.5 models. Excellent conversational nuance, scriptio continua formatting, and dubbing timing adaptation.",
        "requires_api_key": True,
        "supports_styles": True,
        "supports_alternatives": True,
        "default_model": DEFAULT_CLAUDE_MODEL,
        "available_models": SUPPORTED_CLAUDE_MODELS,
    },
    {
        "id": "custom",
        "name": "Custom AI API (OpenAI-Compatible)",
        "type": "custom_llm",
        "description": "Connect any custom OpenAI-compatible endpoint (OpenRouter, Mistral, Ollama, vLLM, LMStudio). Flexible base URL and model selection.",
        "requires_api_key": True,
        "requires_base_url": True,
        "supports_styles": True,
        "supports_alternatives": True,
        "default_model": DEFAULT_CUSTOM_MODEL,
        "available_models": SUPPORTED_CUSTOM_MODELS,
        "default_base_url": "https://api.deepseek.com/v1",
    },
]

DEFAULT_TRANSLATION_PROVIDER = "nllb"
DEFAULT_TRANSLATION_STYLE = "natural"


def list_translation_providers() -> List[Dict[str, Any]]:
    """Return all translation providers enriched with credential configuration status."""
    providers = []
    for p in SUPPORTED_TRANSLATION_PROVIDERS:
        item = dict(p)
        creds = get_provider_credentials(p["id"])
        if p["requires_api_key"]:
            item["is_configured"] = is_api_key_configured(p["id"])
            item["masked_key"] = get_masked_api_key(p["id"])
        else:
            item["is_configured"] = True
            item["masked_key"] = get_masked_api_key(p["id"]) if is_api_key_configured(p["id"]) else None

        if creds.get("base_url"):
            item["base_url"] = creds["base_url"]
        elif "default_base_url" in p:
            item["base_url"] = p["default_base_url"]
        else:
            item["base_url"] = None

        if creds.get("model"):
            item["configured_model"] = creds["model"]
        else:
            item["configured_model"] = p.get("default_model")
        providers.append(item)
    return providers


def validate_translation_provider(provider_name: str) -> bool:
    """Validate if the given provider ID is recognized and supported."""
    p_norm = (provider_name or "").strip().lower()
    return any(p["id"] == p_norm for p in SUPPORTED_TRANSLATION_PROVIDERS)


def get_active_ai_provider_name() -> str:
    """Return the first configured AI provider, or 'groq' / 'gemini' as fallback."""
    for pid in ["groq", "deepseek", "gemini", "openai", "claude", "custom"]:
        if is_api_key_configured(pid):
            return pid
    return "groq" if is_api_key_configured("groq") else "gemini"


def get_translation_provider(
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    **kwargs,
) -> TranslationProvider:
    """Factory to retrieve a configured TranslationProvider instance by name."""
    norm = (provider_name or DEFAULT_TRANSLATION_PROVIDER).strip().lower()

    if norm == "nllb":
        return NLLBTranslationProvider(**kwargs)
    elif norm == "gemini":
        return GeminiTranslationProvider(api_key=api_key, model=model, **kwargs)
    elif norm in ("openai", "custom", "groq", "deepseek"):
        return OpenAITranslationProvider(
            provider_id=norm,
            api_key=api_key,
            base_url=base_url,
            model=model,
            **kwargs,
        )
    elif norm == "claude":
        return ClaudeTranslationProvider(
            api_key=api_key,
            model=model,
            **kwargs,
        )
    else:
        supported = ", ".join(f"'{p['id']}'" for p in SUPPORTED_TRANSLATION_PROVIDERS)
        raise ValueError(
            f"Unsupported translation provider '{provider_name}'. Supported providers: {supported}"
        )


def test_provider_connection(
    provider_name: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Tuple[bool, str]:
    """Test connection and authentication for a specific translation provider."""
    norm = (provider_name or "").strip().lower()
    if norm == "nllb":
        # NLLB is a local model, verify environment
        return True, "Meta NLLB-200 local provider is available."
    elif norm == "gemini":
        provider = GeminiTranslationProvider(api_key=api_key, model=model)
        return provider.test_connection(api_key=api_key)
    elif norm in ("openai", "custom", "groq", "deepseek"):
        provider = OpenAITranslationProvider(
            provider_id=norm,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        return provider.test_connection(api_key=api_key)
    elif norm == "claude":
        provider = ClaudeTranslationProvider(api_key=api_key, model=model)
        return provider.test_connection(api_key=api_key)
    else:
        return False, f"Unknown translation provider '{provider_name}'."
