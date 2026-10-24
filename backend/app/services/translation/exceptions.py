class TranslationError(Exception):
    """Base exception for translation failures."""
    pass


class ModelLoadError(TranslationError):
    """Raised when translation model fails to load or download."""
    pass


class TextTranslationError(TranslationError):
    """Raised when translation inference encounters an error."""
    pass


class ProviderAuthenticationError(TranslationError):
    """Raised when API key is missing or invalid."""
    pass


class RateLimitError(TranslationError):
    """Raised when API provider rate limits or quotas are exceeded."""
    pass


class ProviderTimeoutError(TranslationError):
    """Raised when external API request exceeds allowed timeout."""
    pass


class ProviderUnavailableError(TranslationError):
    """Raised when external translation provider endpoint is unreachable or model is unavailable."""
    pass
