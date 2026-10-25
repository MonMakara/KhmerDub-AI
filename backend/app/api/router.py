from fastapi import APIRouter
from app.api.endpoints import health, projects, tts, translation, subtitles, voices, toolkit

api_router = APIRouter(prefix="/api")

api_router.include_router(health.router)
api_router.include_router(projects.router)
api_router.include_router(subtitles.router, prefix="/projects", tags=["subtitles"])
api_router.include_router(tts.router, prefix="/tts", tags=["tts"])
api_router.include_router(translation.router, prefix="/translation", tags=["translation"])
api_router.include_router(voices.router, prefix="/voices", tags=["voices"])
api_router.include_router(toolkit.router, prefix="/toolkit", tags=["toolkit"])
