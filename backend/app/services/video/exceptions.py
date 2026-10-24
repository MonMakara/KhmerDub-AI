class VideoProcessingError(Exception):
    """Base exception for video/audio processing operations."""
    pass


class CorruptedVideoError(VideoProcessingError):
    """Raised when the video file cannot be parsed or is corrupted."""
    pass


class InvalidVideoFormatError(VideoProcessingError):
    """Raised when the video format is not a supported MP4 container."""
    pass


class NoAudioTrackError(VideoProcessingError):
    """Raised when the video has no audio track for dubbing."""
    pass
