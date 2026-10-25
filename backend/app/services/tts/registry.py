import logging
from typing import Any, Dict, List, Optional

from app.database.session import SessionLocal
from app.models.voice import VoiceConsent, VoiceProfile
from app.services.tts.base import TTSProvider
from app.services.tts.edge import EdgeTTSProvider
from app.services.tts.google import GoogleTTSProvider
from app.services.tts.voxcpm import VoxCPM2TTSProvider

logger = logging.getLogger(__name__)

AVAILABLE_VOICES: List[Dict[str, Any]] = [
    {
        "provider": "gtts",
        "voice": "default",
        "label": "Google Khmer (Default)",
        "gender": "neutral",
        "language": "km",
        "description": "Standard Google Translate Khmer online voice",
        "sample_rate": 24000,
        "is_custom": False,
        "is_available": True,
    },
    {
        "provider": "edge",
        "voice": "km-KH-PisethNeural",
        "label": "Microsoft Piseth (Male)",
        "gender": "male",
        "language": "km",
        "description": "Microsoft Edge Neural Voice (Male, friendly & natural)",
        "sample_rate": 24000,
        "is_custom": False,
        "is_available": True,
    },
    {
        "provider": "edge",
        "voice": "km-KH-SreymomNeural",
        "label": "Microsoft Sreymom (Female)",
        "gender": "female",
        "language": "km",
        "description": "Microsoft Edge Neural Voice (Female, expressive & natural)",
        "sample_rate": 24000,
        "is_custom": False,
        "is_available": True,
    },
    {
        "provider": "edge",
        "voice": "en-US-AriaNeural",
        "label": "Microsoft Aria (Female)",
        "gender": "female",
        "language": "en",
        "description": "Microsoft Edge Neural Voice (English US, clear & natural)",
        "sample_rate": 24000,
        "is_custom": False,
        "is_available": True,
    },
    {
        "provider": "edge",
        "voice": "en-US-GuyNeural",
        "label": "Microsoft Guy (Male)",
        "gender": "male",
        "language": "en",
        "description": "Microsoft Edge Neural Voice (English US, clear & natural)",
        "sample_rate": 24000,
        "is_custom": False,
        "is_available": True,
    },
]

DEFAULT_PROVIDER = "gtts"
DEFAULT_VOICE = "default"


def list_supported_voices(db: Optional[Any] = None, language: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return all available TTS voices with metadata, filtered optionally by language ('km' or 'en')."""
    voices = [dict(v) for v in AVAILABLE_VOICES]

    # Query active, legally authorized custom voice profiles if database session or connection is available
    custom_profiles = []
    try:
        if db is not None:
            custom_profiles = (
                db.query(VoiceProfile)
                .filter(VoiceProfile.is_active == 1)
                .order_by(VoiceProfile.created_at.desc())
                .all()
            )
        else:
            with SessionLocal() as session:
                custom_profiles = (
                    session.query(VoiceProfile)
                    .filter(VoiceProfile.is_active == 1)
                    .order_by(VoiceProfile.created_at.desc())
                    .all()
                )
    except Exception as e:
        logger.warning("Could not query custom voice profiles for registry: %s", e)

    if custom_profiles:
        # Check GPU worker online status once
        vox_provider = VoxCPM2TTSProvider()
        worker_online = vox_provider.is_worker_online()

        for profile in custom_profiles:
            # Check consent authorization
            is_authorized = False
            speaker_name = profile.name
            try:
                if db is not None:
                    consent = db.query(VoiceConsent).filter(VoiceConsent.id == profile.consent_id).first()
                else:
                    with SessionLocal() as session:
                        consent = session.query(VoiceConsent).filter(VoiceConsent.id == profile.consent_id).first()
                if consent and consent.is_authorized:
                    is_authorized = True
                    speaker_name = consent.speaker_name
            except Exception:
                is_authorized = False

            if is_authorized:
                voices.append({
                    "provider": "voxcpm",
                    "voice": profile.id,
                    "label": f"{profile.name} (Custom Clone)",
                    "gender": profile.gender or "custom",
                    "language": profile.language or "km",
                    "description": f"Custom voice cloned from authorized speaker '{speaker_name}' using VoxCPM2 GPU inference",
                    "sample_rate": profile.reference_audio_sample_rate or 48000,
                    "is_custom": True,
                    "profile_id": profile.id,
                    "is_available": worker_online,
                })

    if language:
        clean_lang = language.strip().lower()
        voices = [v for v in voices if v.get("language", "km") == clean_lang]

    return voices


def is_valid_voice_combination(provider: str, voice: str, db: Optional[Any] = None) -> bool:
    """Check if the given provider and voice pairing is supported."""
    p_norm = (provider or "").strip().lower()
    v_norm = (voice or "").strip()

    # Built-in system voices
    if any(v["provider"] == p_norm and v["voice"] == v_norm for v in AVAILABLE_VOICES):
        return True

    # Custom VoxCPM2 voices
    if p_norm in ("voxcpm", "voxcpm2", "custom"):
        # Strip common prefixes like 'custom:' or 'voxcpm:' if passed by UI
        target_v = v_norm
        for prefix in ("custom:", "voxcpm:", "voxcpm2:"):
            if target_v.lower().startswith(prefix):
                target_v = target_v[len(prefix):].strip()
                break

        try:
            if db is not None:
                profile = (
                    db.query(VoiceProfile)
                    .filter(
                        (VoiceProfile.id == target_v) | (VoiceProfile.name == target_v),
                        VoiceProfile.is_active == 1,
                    )
                    .first()
                )
                if profile:
                    consent = (
                        db.query(VoiceConsent)
                        .filter(VoiceConsent.id == profile.consent_id, VoiceConsent.is_authorized == 1)
                        .first()
                    )
                    return consent is not None
            else:
                with SessionLocal() as session:
                    profile = (
                        session.query(VoiceProfile)
                        .filter(
                            (VoiceProfile.id == target_v) | (VoiceProfile.name == target_v),
                            VoiceProfile.is_active == 1,
                        )
                        .first()
                    )
                    if profile:
                        consent = (
                            session.query(VoiceConsent)
                            .filter(VoiceConsent.id == profile.consent_id, VoiceConsent.is_authorized == 1)
                            .first()
                        )
                        return consent is not None
        except Exception as e:
            logger.warning("Error checking custom voice validity: %s", e)

    return False


def get_tts_provider(provider_name: str) -> TTSProvider:
    """Factory to retrieve a configured TTSProvider instance by name."""
    norm = (provider_name or "").strip().lower()
    if norm == "gtts":
        return GoogleTTSProvider()
    elif norm == "edge":
        return EdgeTTSProvider()
    elif norm in ("voxcpm", "voxcpm2", "custom"):
        return VoxCPM2TTSProvider()
    else:
        raise ValueError(
            f"Unsupported TTS provider '{provider_name}'. Supported providers: 'gtts', 'edge', 'voxcpm'"
        )
