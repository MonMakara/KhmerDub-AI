import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.project import Project
from app.schemas.project import (
    SubtitleListResponse,
    SubtitleSegmentItem,
    SubtitleSegmentUpdate,
    SubtitleResetResponse,
)
from app.services.subtitles.service import SubtitleService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{project_id}/subtitles", response_model=SubtitleListResponse)
def get_project_subtitles(
    project_id: str,
    language: str = Query("km", description="Language code: 'km' or 'en'"),
    db: Session = Depends(get_db),
) -> SubtitleListResponse:
    """
    Retrieve project subtitle cues for English or Khmer.
    Merges custom user edits with source transcript/translation segments.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        data = SubtitleService.get_subtitles(project_id=project_id, language=language, db=db)
        return SubtitleListResponse(**data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to fetch subtitles for project %s: %s", project_id, e)
        raise HTTPException(status_code=500, detail="Failed to load project subtitles")


@router.patch("/{project_id}/subtitles/{segment_order}", response_model=SubtitleSegmentItem)
def update_project_subtitle_segment(
    project_id: str,
    segment_order: int,
    payload: SubtitleSegmentUpdate,
    db: Session = Depends(get_db),
) -> SubtitleSegmentItem:
    """
    Update the subtitle text for a specific segment.
    Saves as a subtitle-specific customization without invalidating generated TTS speech.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        updated = SubtitleService.update_subtitle_segment(
            project_id=project_id,
            language=payload.language or "km",
            segment_order=segment_order,
            text=payload.text,
            db=db,
        )
        return SubtitleSegmentItem(**updated)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            "Failed to update subtitle segment %d for project %s: %s",
            segment_order,
            project_id,
            e,
        )
        raise HTTPException(status_code=500, detail="Failed to update subtitle segment")


@router.post("/{project_id}/subtitles/reset", response_model=SubtitleResetResponse)
def reset_project_subtitles(
    project_id: str,
    language: str = Query("km", description="Language to reset: 'km' or 'en'"),
    db: Session = Depends(get_db),
) -> SubtitleResetResponse:
    """
    Reset all customized subtitle edits for a language back to original source text.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        deleted_count = SubtitleService.reset_subtitles(
            project_id=project_id,
            language=language,
            db=db,
        )
        lang_name = "Khmer" if SubtitleService.normalize_language(language) == "km" else "English"
        return SubtitleResetResponse(
            message=f"{lang_name} subtitles successfully reset to original text.",
            deleted_count=deleted_count,
            language=SubtitleService.normalize_language(language),
        )
    except Exception as e:
        logger.error("Failed to reset subtitles for project %s: %s", project_id, e)
        raise HTTPException(status_code=500, detail="Failed to reset subtitles")


@router.get("/{project_id}/subtitles/export")
def export_project_subtitles(
    project_id: str,
    language: str = Query("km", description="Language code: 'km' or 'en'"),
    format: str = Query("srt", description="Subtitle format: 'srt' or 'vtt'"),
    db: Session = Depends(get_db),
):
    """
    Download subtitles as a formatted .srt or .vtt file with proper UTF-8 encoding.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        content, filename, mime_type = SubtitleService.export_subtitles(
            project_id=project_id,
            language=language,
            format_type=format,
            db=db,
        )
        return Response(
            content=content.encode("utf-8"),
            media_type=mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": mime_type,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to export subtitles for project %s: %s", project_id, e)
        raise HTTPException(status_code=500, detail="Failed to export subtitles")


@router.get("/{project_id}/subtitles/stream")
def stream_project_subtitles(
    project_id: str,
    language: str = Query("km", description="Language code: 'km' or 'en'"),
    format: str = Query("vtt", description="Subtitle format: 'vtt' or 'srt'"),
    db: Session = Depends(get_db),
):
    """
    Stream subtitles inline (e.g. for HTML5 video <track> elements).
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        content, filename, mime_type = SubtitleService.export_subtitles(
            project_id=project_id,
            language=language,
            format_type=format,
            db=db,
        )
        return Response(
            content=content.encode("utf-8"),
            media_type=mime_type,
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "Content-Type": mime_type,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to stream subtitles for project %s: %s", project_id, e)
        raise HTTPException(status_code=500, detail="Failed to stream subtitles")
