class AudioValidationError(Exception):
    """Raised when uploaded audio fails format, duration, or quality checks."""
    pass


class AudioTooShortError(AudioValidationError):
    """Raised when audio duration is less than the required minimum."""
    pass


class AudioTooLongError(AudioValidationError):
    """Raised when audio duration exceeds the allowable limit."""
    pass


class AudioSilentError(AudioValidationError):
    """Raised when audio recording is silent or has inadequate signal."""
    pass


class AudioCorruptedError(AudioValidationError):
    """Raised when audio file cannot be parsed or decoded by ffprobe/ffmpeg."""
    pass
