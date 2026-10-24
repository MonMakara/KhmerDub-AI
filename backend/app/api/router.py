from fastapi import APIRouter
from app.api.endpoints import health, projects, tts

api_router = APIRouter(prefix="/api")

api_router.include_router(health.router)
api_router.include_router(projects.router)
api_router.include_router(tts.router, prefix="/tts", tags=["tts"])
