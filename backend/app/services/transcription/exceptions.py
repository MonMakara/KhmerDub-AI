class TranscriptionError(Exception):
    """Base exception for transcription failures."""
    pass


class ModelLoadError(TranscriptionError):
    """Raised when faster-whisper model fails to load or download."""
    pass


class AudioTranscriptionError(TranscriptionError):
    """Raised when transcription processing encounters an error."""
    pass
