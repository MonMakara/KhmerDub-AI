import hashlib
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import resolve_audio_file
from app.database.session import get_db
from app.models.project import GeneratedAudio
from app.schemas.project import (
    VoiceListResponse,
    VoiceOptionResponse,
    VoicePreviewRequest,
)
from app.services.tts.registry import (
    list_supported_voices,
    is_valid_voice_combination,
    get_tts_provider,
    DEFAULT_PROVIDER,
    DEFAULT_VOICE,
)
from app.services.tts.exceptions import TTSError

logger = logging.getLogger(__name__)

router = APIRouter()

DEFAULT_PREVIEW_TEXT = "សួស្តីអ្នកទាំងអស់គ្នា។ សូមស្វាគមន៍មកកាន់ KhmerDub AI។"
MAX_PREVIEW_TEXT_LENGTH = 200


@router.get("/voices", response_model=VoiceListResponse)
def get_voices() -> VoiceListResponse:
    """Retrieve all available Khmer TTS providers and voices."""
    voices_raw = list_supported_voices()
    voices = [VoiceOptionResponse(**v) for v in voices_raw]
    return VoiceListResponse(
        voices=voices,
        default_provider=DEFAULT_PROVIDER,
        default_voice=DEFAULT_VOICE,
    )


@router.post("/preview")
def preview_voice(payload: VoicePreviewRequest):
    """Generate a short speech preview audio file for a given voice and text."""
    provider = (payload.provider or DEFAULT_PROVIDER).strip().lower()
    voice = (payload.voice or DEFAULT_VOICE).strip()

    if not is_valid_voice_combination(provider, voice):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid voice combination: provider='{provider}', voice='{voice}'",
        )

    text = (payload.text or DEFAULT_PREVIEW_TEXT).strip()
    if not text:
        text = DEFAULT_PREVIEW_TEXT

    if len(text) > MAX_PREVIEW_TEXT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Preview text exceeds maximum allowed length of {MAX_PREVIEW_TEXT_LENGTH} characters.",
        )

    # Hash text + voice to reuse/cache preview file cleanly in temp dir
    text_hash = hashlib.md5(f"{provider}:{voice}:{text}".encode("utf-8")).hexdigest()[:12]
    temp_dir = Path(settings.TEMP_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)
    preview_file = temp_dir / f"preview_{provider}_{voice}_{text_hash}.mp3"

    try:
        if not preview_file.exists() or preview_file.stat().st_size == 0:
            tts_provider = get_tts_provider(provider)
            tts_provider.synthesize(
                text=text,
                output_path=preview_file,
                language="km",
                voice=voice,
            )

        return FileResponse(
            path=str(preview_file),
            media_type="audio/mpeg",
            filename=f"preview_{voice}.mp3",
            content_disposition_type="inline",
        )
    except TTSError as e:
        logger.error("TTS preview synthesis error: %s", e)
        raise HTTPException(status_code=502, detail=f"TTS synthesis error: {e}")
    except Exception as e:
        logger.exception("Failed to generate voice preview: %s", e)
        raise HTTPException(status_code=500, detail=f"Internal voice preview error: {e}")


@router.api_route("/stream/{audio_id}", methods=["GET", "HEAD"])
def stream_audio_by_id(
    audio_id: str,
    db: Session = Depends(get_db),
):
    """Stream synthesized audio by GeneratedAudio record ID for in-browser playback."""
    audio_record = (
        db.query(GeneratedAudio)
        .filter(GeneratedAudio.id == audio_id)
        .first()
    )
    if not audio_record:
        raise HTTPException(status_code=404, detail="Generated audio record not found")

    file_path = resolve_audio_file(
        audio_record.project_id,
        audio_record.translation_segment_id or "",
        audio_record.audio_path,
    )
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="Audio file not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type="audio/mpeg",
        filename=f"tts_{audio_id}.mp3",
        content_disposition_type="inline",
    )
