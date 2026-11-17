from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.recovery import (
    recover_interrupted_jobs,
    recover_interrupted_deletions,
    recover_interrupted_toolkit_tasks,
)
from app.database.session import init_db, SessionLocal
from app.api.router import api_router
from app.services.subtitles.checker import verify_subtitle_system_prerequisites

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_time = datetime.now(timezone.utc)
    # Startup: Ensure directories and database tables exist
    init_db()

    # Verify subtitle burn-in prerequisites (FFmpeg + libass + HarfBuzz + Khmer fonts)
    verify_subtitle_system_prerequisites()

    # Ensure audio-cleaning environment symlink if persistent model_cache volume contains it
    try:
        from pathlib import Path
        cache_env = settings.MODEL_CACHE_DIR / "audio-cleaning-env"
        opt_env = Path("/opt/audio-cleaning-env")
        if cache_env.exists() and not opt_env.exists():
            opt_env.symlink_to(cache_env)
    except Exception as e:
        logger.warning("Could not symlink audio-cleaning-env: %s", e)

    # Safely recover any interrupted jobs and incomplete project deletions from previous server session
    db = SessionLocal()
    try:
        recover_interrupted_jobs(db, process_start_time=startup_time)
        recover_interrupted_deletions(db)
        recover_interrupted_toolkit_tasks(db)
    except Exception as e:
        logger.error("Failed to run startup recovery: %s", e)
    finally:
        db.close()

    yield
    # Shutdown logic if needed


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="KhmerDub AI - Automated English-to-Khmer video dubbing platform",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(api_router)


@app.get("/")
def root():
    return {
        "message": f"Welcome to {settings.APP_NAME} API",
        "version": settings.APP_VERSION,
        "docs_url": "/docs",
        "health_check": "/api/health",
    }
