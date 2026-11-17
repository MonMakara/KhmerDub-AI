import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import (
    get_voice_profile_audio_path,
    delete_voice_profile_storage,
    sanitize_profile_id,
)
from app.database.session import get_db
from app.models.voice import VoiceConsent, VoiceProfile
from app.schemas.project import VoiceOptionResponse
from app.schemas.voice import (
    VoiceProfileResponse,
    VoiceProfileUpdate,
    VoiceStudioResponse,
)
from app.services.tts.registry import (
    AVAILABLE_VOICES,
    DEFAULT_PROVIDER,
    DEFAULT_VOICE,
)
from app.services.tts.voxcpm import VoxCPM2TTSProvider
from app.services.voice.inspector import AudioQualityInspector
from app.services.voice.exceptions import AudioValidationError

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_VOICE_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
inspector = AudioQualityInspector()

LEGAL_CONSENT_TEMPLATE = (
    "I explicitly authorize KhmerDub AI to condition custom voice synthesis on my "
    "provided reference audio recording for English-to-Khmer dubbing. I verify that "
    "I possess full rights and legal authorization to use and process this voice data."
)


@router.get("", response_model=VoiceStudioResponse)
def get_voice_studio(db: Session = Depends(get_db)) -> VoiceStudioResponse:
    """Retrieve all available system voices and registered custom voice profiles."""
    system_raw = list(AVAILABLE_VOICES)
    system_voices = [VoiceOptionResponse(**v) for v in system_raw]

    profiles = (
        db.query(VoiceProfile)
        .filter(VoiceProfile.is_library.is_(True))
        .order_by(VoiceProfile.created_at.desc())
        .all()
    )

    custom_responses = [VoiceProfileResponse.model_validate(p) for p in profiles]

    # Dynamically probe VoxCPM2 GPU inference worker status
    vox_provider = VoxCPM2TTSProvider()
    worker_health = vox_provider.check_worker_health()
    if worker_health.get("status") == "online":
        gpu_label = worker_health.get("gpu_name", "CUDA GPU")
        engine_status = f"Online (VoxCPM2 — {gpu_label})"
    else:
        engine_status = "Offline (VoxCPM2 Worker Unavailable)"

    return VoiceStudioResponse(
        system_voices=system_voices,
        custom_profiles=custom_responses,
        total_custom_profiles=len(custom_responses),
        cloning_engine_status=engine_status,
        default_provider=DEFAULT_PROVIDER,
        default_voice=DEFAULT_VOICE,
    )


@router.post("", response_model=VoiceProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_voice_profile(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    gender: str = Form("neutral"),
    speaker_name: str = Form(...),
    authorized_by: str = Form(...),
    consent_confirmed: bool = Form(...),
    reference_transcript: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> VoiceProfileResponse:
    """
    Create a new authorized voice profile with reference audio validation and normalization.
    Explicit consent confirmation is legally and strictly required.
    """
    # 1. Validate textual inputs
    clean_name = (name or "").strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Voice profile name cannot be empty.")
    if len(clean_name) > 100:
        raise HTTPException(status_code=400, detail="Voice profile name must be 100 characters or fewer.")

    clean_speaker = (speaker_name or "").strip()
    clean_authorizer = (authorized_by or "").strip()
    if not clean_speaker:
        raise HTTPException(status_code=400, detail="Speaker name is required.")
    if not clean_authorizer:
        raise HTTPException(status_code=400, detail="Authorized by (grantor) is required.")

    # 2. Strict Consent Verification
    if not consent_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Explicit speaker authorization and consent confirmation is required before creating a voice profile.",
        )

    # 3. Validate audio file format
    if not file.filename:
        raise HTTPException(status_code=400, detail="Audio file must have a valid filename.")

    try:
        ext = inspector.validate_file_extension(file.filename)
    except AudioValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 4. Stream upload to a temporary file
    profile_id = str(uuid.uuid4())
    temp_dir = settings.TEMP_DIR
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / f"temp_voice_{profile_id}{ext}"

    total_bytes = 0
    hasher = hashlib.sha256()

    try:
        with open(temp_file, "wb") as f:
            while chunk := await file.read(1024 * 64):
                total_bytes += len(chunk)
                if total_bytes > MAX_VOICE_FILE_SIZE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Uploaded audio file exceeds maximum limit of {MAX_VOICE_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
                    )
                hasher.update(chunk)
                f.write(chunk)

        file_sha256 = hasher.hexdigest()

        # 5. Inspect and normalize audio via FFmpeg
        target_path = get_voice_profile_audio_path(profile_id)
        audio_meta = inspector.normalize_reference_audio(temp_file, target_path)

        # 6. Generate cryptographic signature hash for consent audit trail
        consent_now = datetime.now(timezone.utc)
        sig_data = f"{clean_speaker}|{clean_authorizer}|{file_sha256}|{consent_now.isoformat()}"
        signature_hash = hashlib.sha256(sig_data.encode("utf-8")).hexdigest()

        # 7. Persist Consent and Profile in Database
        consent = VoiceConsent(
            id=str(uuid.uuid4()),
            speaker_name=clean_speaker,
            authorized_by=clean_authorizer,
            consent_statement=LEGAL_CONSENT_TEMPLATE,
            is_authorized=True,
            signature_hash=signature_hash,
            granted_at=consent_now,
        )
        db.add(consent)
        db.flush()

        # Stored relative path for portability
        relative_audio_path = f"voice_profiles/{profile_id}/reference.wav"

        profile = VoiceProfile(
            id=profile_id,
            name=clean_name,
            description=(description or "").strip() or None,
            gender=gender.lower() if gender.lower() in ["male", "female", "neutral"] else "neutral",
            language="km",
            reference_audio_path=relative_audio_path,
            reference_audio_duration=audio_meta["duration"],
            reference_audio_sample_rate=audio_meta["sample_rate"],
            reference_transcript=(reference_transcript or "").strip() or None,
            audio_format="wav",
            is_active=True,
            consent_id=consent.id,
            created_at=consent_now,
            updated_at=consent_now,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        logger.info(
            f"Created VoiceProfile '{profile.name}' (id={profile.id}, duration={profile.reference_audio_duration}s, consent={consent.id})"
        )
        return VoiceProfileResponse.model_validate(profile)

    except AudioValidationError as e:
        logger.warning("Audio validation failed: %s", e)
        # Clean up target directory if partially created
        delete_voice_profile_storage(profile_id)
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        delete_voice_profile_storage(profile_id)
        raise
    except Exception as e:
        logger.exception("Unexpected error creating voice profile: %s", e)
        delete_voice_profile_storage(profile_id)
        raise HTTPException(status_code=500, detail=f"Failed to create voice profile: {e}")
    finally:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception as e:
                logger.warning(f"Failed to remove temp file {temp_file}: {e}")


@router.get("/{profile_id}", response_model=VoiceProfileResponse)
def get_voice_profile(profile_id: str, db: Session = Depends(get_db)) -> VoiceProfileResponse:
    """Retrieve details of a single custom voice profile."""
    safe_id = sanitize_profile_id(profile_id)
    profile = db.query(VoiceProfile).filter(VoiceProfile.id == safe_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Voice profile not found.")
    return VoiceProfileResponse.model_validate(profile)


@router.patch("/{profile_id}", response_model=VoiceProfileResponse)
def update_voice_profile(
    profile_id: str,
    payload: VoiceProfileUpdate,
    db: Session = Depends(get_db),
) -> VoiceProfileResponse:
    """Rename or update metadata for a voice profile."""
    safe_id = sanitize_profile_id(profile_id)
    profile = db.query(VoiceProfile).filter(VoiceProfile.id == safe_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Voice profile not found.")

    if payload.name is not None:
        clean_name = payload.name.strip()
        if not clean_name:
            raise HTTPException(status_code=400, detail="Voice profile name cannot be empty.")
        profile.name = clean_name

    if payload.description is not None:
        profile.description = payload.description.strip() or None

    if payload.gender is not None:
        g = payload.gender.strip().lower()
        if g in ["male", "female", "neutral"]:
            profile.gender = g

    if payload.reference_transcript is not None:
        profile.reference_transcript = payload.reference_transcript.strip() or None

    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    logger.info(f"Updated VoiceProfile {safe_id}: name='{profile.name}'")
    return VoiceProfileResponse.model_validate(profile)


@router.delete("/{profile_id}")
def delete_voice_profile(
    profile_id: str,
    db: Session = Depends(get_db),
):
    """
    Safely delete a custom voice profile and its normalized reference recording.
    Storage deletion is strictly isolated from project assets and models.
    """
    safe_id = sanitize_profile_id(profile_id)
    profile = db.query(VoiceProfile).filter(VoiceProfile.id == safe_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Voice profile not found.")

    consent_id = profile.consent_id

    # Delete storage first
    cleanup_result = delete_voice_profile_storage(safe_id)

    # Delete from DB
    db.delete(profile)
    if consent_id:
        consent = db.query(VoiceConsent).filter(VoiceConsent.id == consent_id).first()
        if consent:
            db.delete(consent)

    db.commit()
    logger.info(f"Deleted VoiceProfile {safe_id} and storage files ({cleanup_result['deleted_count']} deleted)")

    return {
        "message": "Voice profile successfully deleted.",
        "id": safe_id,
        "deleted_files_count": cleanup_result["deleted_count"],
    }


@router.api_route("/{profile_id}/audio", methods=["GET", "HEAD"])
def stream_reference_audio(
    profile_id: str,
    db: Session = Depends(get_db),
):
    """Stream normalized reference audio for in-browser preview."""
    safe_id = sanitize_profile_id(profile_id)
    profile = db.query(VoiceProfile).filter(VoiceProfile.id == safe_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Voice profile not found.")

    audio_path = get_voice_profile_audio_path(safe_id)
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="Reference audio file not found on disk.")

    return FileResponse(
        path=str(audio_path),
        media_type="audio/wav",
        filename=f"reference_{safe_id}.wav",
        content_disposition_type="inline",
    )
