from app.services.translation.base import (
    TranslationProvider,
    TranslationSegmentResult,
    TranslationAlternative,
    AIImprovementResult,
)
from app.services.translation.nllb import (
    NLLBTranslationProvider,
    normalize_language_code,
    get_current_process_ram_mb,
)
from app.services.translation.gemini import (
    GeminiTranslationProvider,
    DEFAULT_GEMINI_MODEL,
    SUPPORTED_GEMINI_MODELS,
)
from app.services.translation.registry import (
    get_translation_provider,
    list_translation_providers,
    validate_translation_provider,
    test_provider_connection,
    DEFAULT_TRANSLATION_PROVIDER,
    DEFAULT_TRANSLATION_STYLE,
    SUPPORTED_TRANSLATION_PROVIDERS,
)
from app.services.translation.formatter import KhmerTextFormatter
from app.services.translation.glossary import KhmerGlossary
from app.services.translation.prompts import (
    TRANSLATION_STYLES,
    build_ai_improve_prompt,
    build_alternatives_prompt,
)
from app.services.translation.exceptions import (
    TranslationError,
    ModelLoadError,
    TextTranslationError,
    ProviderAuthenticationError,
    RateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

__all__ = [
    "TranslationProvider",
    "TranslationSegmentResult",
    "TranslationAlternative",
    "AIImprovementResult",
    "NLLBTranslationProvider",
    "GeminiTranslationProvider",
    "get_translation_provider",
    "list_translation_providers",
    "validate_translation_provider",
    "test_provider_connection",
    "DEFAULT_TRANSLATION_PROVIDER",
    "DEFAULT_TRANSLATION_STYLE",
    "SUPPORTED_TRANSLATION_PROVIDERS",
    "DEFAULT_GEMINI_MODEL",
    "SUPPORTED_GEMINI_MODELS",
    "KhmerTextFormatter",
    "KhmerGlossary",
    "TRANSLATION_STYLES",
    "build_ai_improve_prompt",
    "build_alternatives_prompt",
    "normalize_language_code",
    "get_current_process_ram_mb",
    "TranslationError",
    "ModelLoadError",
    "TextTranslationError",
    "ProviderAuthenticationError",
    "RateLimitError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
]
