class TranslationError(Exception):
    """Base exception for translation failures."""
    pass


class ModelLoadError(TranslationError):
    """Raised when translation model fails to load or download."""
    pass


class TextTranslationError(TranslationError):
    """Raised when translation inference encounters an error."""
    pass
