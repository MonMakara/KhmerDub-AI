import logging
from typing import Dict, List, Optional, Any

from app.services.tts.base import TTSProvider
from app.services.tts.google import GoogleTTSProvider
from app.services.tts.edge import EdgeTTSProvider

logger = logging.getLogger(__name__)

AVAILABLE_VOICES: List[Dict[str, Any]] = [
    {
        "provider": "gtts",
        "voice": "default",
        "label": "Google Khmer (Default)",
        "gender": "neutral",
        "description": "Standard Google Translate Khmer online voice",
        "sample_rate": 24000,
    },
    {
        "provider": "edge",
        "voice": "km-KH-PisethNeural",
        "label": "Microsoft Piseth (Male)",
        "gender": "male",
        "description": "Microsoft Edge Neural Voice (Male, friendly & natural)",
        "sample_rate": 24000,
    },
    {
        "provider": "edge",
        "voice": "km-KH-SreymomNeural",
        "label": "Microsoft Sreymom (Female)",
        "gender": "female",
        "description": "Microsoft Edge Neural Voice (Female, expressive & natural)",
        "sample_rate": 24000,
    },
]

DEFAULT_PROVIDER = "gtts"
DEFAULT_VOICE = "default"


def list_supported_voices() -> List[Dict[str, Any]]:
    """Return all available Khmer TTS voices with metadata."""
    return list(AVAILABLE_VOICES)


def is_valid_voice_combination(provider: str, voice: str) -> bool:
    """Check if the given provider and voice pairing is supported."""
    p_norm = (provider or "").strip().lower()
    v_norm = (voice or "").strip()
    return any(
        v["provider"] == p_norm and v["voice"] == v_norm
        for v in AVAILABLE_VOICES
    )


def get_tts_provider(provider_name: str) -> TTSProvider:
    """Factory to retrieve a configured TTSProvider instance by name."""
    norm = (provider_name or "").strip().lower()
    if norm == "gtts":
        return GoogleTTSProvider()
    elif norm == "edge":
        return EdgeTTSProvider()
    else:
        raise ValueError(
            f"Unsupported TTS provider '{provider_name}'. Supported providers: 'gtts', 'edge'"
        )
