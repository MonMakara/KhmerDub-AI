import shutil
from fastapi import APIRouter
from app.core.config import settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Check backend service health and system readiness."""
    ffmpeg_available = shutil.which("ffmpeg") is not None
    storage_ready = settings.DATA_DIR.exists()

    return HealthResponse(
        status="ok",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
        system_info={
            "ffmpeg_available": ffmpeg_available,
            "storage_ready": storage_ready,
            "whisper_device": settings.WHISPER_DEVICE,
            "whisper_model": settings.WHISPER_MODEL_SIZE,
        },
    )
