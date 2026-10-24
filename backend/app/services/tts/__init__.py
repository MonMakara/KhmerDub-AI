from app.services.tts.base import TTSProvider, TTSAudioResult
from app.services.tts.google import GoogleTTSProvider
from app.services.tts.edge import EdgeTTSProvider
from app.services.tts.registry import (
    get_tts_provider,
    list_supported_voices,
    is_valid_voice_combination,
    AVAILABLE_VOICES,
)
from app.services.tts.exceptions import (
    TTSError,
    LanguageNotSupportedError,
    VoiceNotSupportedError,
    EmptyTextError,
    TTSNetworkError,
    TTSGenerationError,
)

__all__ = [
    "TTSProvider",
    "TTSAudioResult",
    "GoogleTTSProvider",
    "EdgeTTSProvider",
    "get_tts_provider",
    "list_supported_voices",
    "is_valid_voice_combination",
    "AVAILABLE_VOICES",
    "TTSError",
    "LanguageNotSupportedError",
    "VoiceNotSupportedError",
    "EmptyTextError",
    "TTSNetworkError",
    "TTSGenerationError",
]

