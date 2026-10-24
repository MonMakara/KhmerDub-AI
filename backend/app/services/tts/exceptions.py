class TTSError(Exception):
    """Base exception for all TTS-related operations."""
    pass


class LanguageNotSupportedError(TTSError):
    """Raised when the requested language is not supported by the TTS provider."""
    pass


class EmptyTextError(TTSError):
    """Raised when input text for speech synthesis is empty."""
    pass


class TTSNetworkError(TTSError):
    """Raised when network connectivity fails during TTS synthesis."""
    pass


class TTSGenerationError(TTSError):
    """Raised when audio synthesis or file writing fails."""
    pass
