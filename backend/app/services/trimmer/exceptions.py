"""Exceptions for Media Trimmer Service."""


class TrimmerError(Exception):
    """Base exception for all trimmer errors."""
    pass


class InvalidTimestampError(TrimmerError):
    """Raised when timestamp format or range is invalid."""
    pass


class MediaTrimmingError(TrimmerError):
    """Raised when FFmpeg trimming operation fails."""
    pass
