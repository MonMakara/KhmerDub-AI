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
    SubtitleAutoSplitRequest,
    SubtitleManualSplitRequest,
    SubtitleMergeRequest,
    SubtitleKeepEditsRequest,
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
    Merges custom user edits, detects source text modifications, and computes readability indicators.
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
    Update the subtitle text and/or timing for a specific segment.
    Saves as a subtitle customization without invalidating generated TTS speech.
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
            start_time=payload.start_time,
            end_time=payload.end_time,
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


@router.post("/{project_id}/subtitles/auto-split", response_model=SubtitleListResponse)
def auto_split_project_subtitles(
    project_id: str,
    payload: SubtitleAutoSplitRequest = SubtitleAutoSplitRequest(),
    db: Session = Depends(get_db),
) -> SubtitleListResponse:
    """
    Auto-split long subtitle cues into shorter, readable captions with proportional timings.
    Preserves Khmer Unicode and avoids splitting within orthographic clusters.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        data = SubtitleService.auto_split_subtitles(
            project_id=project_id,
            language=payload.language or "km",
            max_chars=payload.max_chars or 75,
            max_duration=payload.max_duration or 6.5,
            db=db,
        )
        return SubtitleListResponse(**data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to auto-split subtitles for project %s: %s", project_id, e)
        raise HTTPException(status_code=500, detail="Failed to auto-split subtitles")


@router.post("/{project_id}/subtitles/{segment_order}/split", response_model=SubtitleListResponse)
def split_project_subtitle_cue(
    project_id: str,
    segment_order: int,
    payload: SubtitleManualSplitRequest = SubtitleManualSplitRequest(),
    db: Session = Depends(get_db),
) -> SubtitleListResponse:
    """
    Split a specific subtitle cue into two consecutive cues.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        data = SubtitleService.split_subtitle_cue(
            project_id=project_id,
            language=payload.language or "km",
            segment_order=segment_order,
            split_index=payload.split_index,
            split_ratio=payload.split_ratio,
            db=db,
        )
        return SubtitleListResponse(**data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to split subtitle cue %d for project %s: %s", segment_order, project_id, e)
        raise HTTPException(status_code=500, detail="Failed to split subtitle cue")


@router.post("/{project_id}/subtitles/{segment_order}/merge", response_model=SubtitleListResponse)
def merge_project_subtitle_cue(
    project_id: str,
    segment_order: int,
    payload: SubtitleMergeRequest = SubtitleMergeRequest(),
    db: Session = Depends(get_db),
) -> SubtitleListResponse:
    """
    Merge a subtitle cue with the adjacent next cue.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        data = SubtitleService.merge_subtitle_cues(
            project_id=project_id,
            language=payload.language or "km",
            segment_order=segment_order,
            db=db,
        )
        return SubtitleListResponse(**data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to merge subtitle cue %d for project %s: %s", segment_order, project_id, e)
        raise HTTPException(status_code=500, detail="Failed to merge subtitle cue")


@router.post("/{project_id}/subtitles/{segment_order}/keep", response_model=SubtitleListResponse)
def keep_project_subtitle_edits(
    project_id: str,
    segment_order: int,
    payload: SubtitleKeepEditsRequest = SubtitleKeepEditsRequest(),
    db: Session = Depends(get_db),
) -> SubtitleListResponse:
    """
    Acknowledge source translation updates and clear outdated warnings while keeping customized subtitle text.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        data = SubtitleService.keep_subtitle_edits(
            project_id=project_id,
            language=payload.language or "km",
            segment_order=segment_order,
            db=db,
        )
        return SubtitleListResponse(**data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to keep subtitle edits for cue %d in project %s: %s", segment_order, project_id, e)
        raise HTTPException(status_code=500, detail="Failed to keep subtitle edits")


@router.post("/{project_id}/subtitles/{segment_order}/reset", response_model=SubtitleListResponse)
def reset_project_subtitle_cue(
    project_id: str,
    segment_order: int,
    language: str = Query("km", description="Language: 'km' or 'en'"),
    db: Session = Depends(get_db),
) -> SubtitleListResponse:
    """
    Reset a single subtitle cue back to original source text and timestamps.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        data = SubtitleService.reset_subtitle_cue(
            project_id=project_id,
            language=language,
            segment_order=segment_order,
            db=db,
        )
        return SubtitleListResponse(**data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to reset subtitle cue %d for project %s: %s", segment_order, project_id, e)
        raise HTTPException(status_code=500, detail="Failed to reset subtitle cue")


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
