import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.storage import (
    StorageCleanRequest,
    StorageCleanResponse,
    StorageUsageResponse,
)
from app.services.storage_manager import clean_storage, get_storage_usage, purge_all_user_data

logger = logging.getLogger(__name__)

router = APIRouter(tags=["System & Storage"])


@router.get("/storage", response_model=StorageUsageResponse)
def get_system_storage_usage(
    db: Session = Depends(get_db),
) -> StorageUsageResponse:
    """Retrieve detailed disk metrics, categorized data volumes, and cleanable cache statistics."""
    try:
        return get_storage_usage(db=db)
    except Exception as e:
        logger.error("Failed to retrieve system storage usage: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not retrieve system storage usage: {str(e)}",
        )


@router.post("/storage/clean", response_model=StorageCleanResponse)
def execute_system_storage_cleanup(
    payload: StorageCleanRequest,
    db: Session = Depends(get_db),
) -> StorageCleanResponse:
    """Safely execute targeted cleanup of temporary files, intermediate caches, logs, or old tasks.

    AI model weights, active dubbing projects, and active tasks are strictly protected.
    """
    try:
        return clean_storage(
            targets=payload.targets,
            older_than_days=payload.older_than_days,
            db=db,
        )
    except Exception as e:
        logger.error("Storage cleanup failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage cleanup operation failed: {str(e)}",
        )


@router.post("/storage/purge-all-data", response_model=StorageCleanResponse)
def purge_system_user_data(
    db: Session = Depends(get_db),
) -> StorageCleanResponse:
    """Purge all user-created projects, toolkit tasks, uploads, outputs, and temp files.

    Custom voice profile reference audios and AI model weights are preserved.
    """
    try:
        return purge_all_user_data(
            db=db,
            keep_models=True,
            keep_voice_profiles=True,
        )
    except Exception as e:
        logger.error("Data purge failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Data purge operation failed: {str(e)}",
        )
