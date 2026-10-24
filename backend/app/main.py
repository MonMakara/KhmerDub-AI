from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.recovery import recover_interrupted_jobs
from app.database.session import init_db, SessionLocal
from app.api.router import api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_time = datetime.now(timezone.utc)
    # Startup: Ensure directories and database tables exist
    init_db()

    # Safely recover any interrupted jobs from previous server session
    db = SessionLocal()
    try:
        recover_interrupted_jobs(db, process_start_time=startup_time)
    except Exception as e:
        logger.error("Failed to run startup job recovery: %s", e)
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
