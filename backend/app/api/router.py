from fastapi import APIRouter
from app.api.endpoints import health, projects, tts, translation, subtitles, voices, toolkit, audio_cleaning, system

api_router = APIRouter(prefix="/api")

api_router.include_router(health.router)
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(projects.router)
api_router.include_router(subtitles.router, prefix="/projects", tags=["subtitles"])
api_router.include_router(tts.router, prefix="/tts", tags=["tts"])
api_router.include_router(translation.router, prefix="/translation", tags=["translation"])
api_router.include_router(voices.router, prefix="/voices", tags=["voices"])
api_router.include_router(toolkit.router, prefix="/toolkit", tags=["toolkit"])
api_router.include_router(audio_cleaning.router, prefix="/toolkit/audio-cleaning", tags=["toolkit"])
api_router.include_router(audio_cleaning.router, prefix="/audio-cleaning", tags=["toolkit"], include_in_schema=False)
