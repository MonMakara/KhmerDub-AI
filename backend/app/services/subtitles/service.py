import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.project import (
    Project,
    TranscriptSegment,
    TranslationSegment,
    SubtitleSegment,
)
from app.services.subtitles.generator import (
    SubtitleCue,
    generate_srt,
    generate_vtt,
)
from app.core.storage import get_subtitle_file_path

logger = logging.getLogger(__name__)


class SubtitleService:
    """Service managing project subtitles, custom caption edits, and SRT/VTT generation."""

    @staticmethod
    def normalize_language(lang: str) -> str:
        """Normalize language to standard ISO code: 'en' or 'km'."""
        if not lang:
            return "km"
        lower = lang.strip().lower()
        if lower in ("en", "eng", "english"):
            return "en"
        if lower in ("km", "khm", "khmer", "cambodian"):
            return "km"
        return lower

    @classmethod
    def get_subtitles(
        cls,
        project_id: str,
        language: str,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Fetch subtitle cues for a project and language.
        Merges custom subtitle edits with underlying transcript/translation source data.
        """
        lang = cls.normalize_language(language)
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project '{project_id}' not found")

        # 1. Fetch custom subtitle overrides for this project and language
        custom_records = (
            db.query(SubtitleSegment)
            .filter(
                SubtitleSegment.project_id == project_id,
                SubtitleSegment.language == lang,
            )
            .all()
        )
        custom_map: Dict[int, SubtitleSegment] = {r.segment_order: r for r in custom_records}

        items: List[Dict[str, Any]] = []

        if lang == "en":
            # English subtitles derive from transcript_segments
            t_segments = (
                db.query(TranscriptSegment)
                .filter(TranscriptSegment.project_id == project_id)
                .order_by(TranscriptSegment.segment_order, TranscriptSegment.start_time)
                .all()
            )

            for t_seg in t_segments:
                custom = custom_map.get(t_seg.segment_order)
                if custom and custom.is_customized:
                    items.append({
                        "id": custom.id,
                        "segment_order": t_seg.segment_order,
                        "start_time": custom.start_time,
                        "end_time": custom.end_time,
                        "text": custom.text,
                        "source_text": t_seg.text,
                        "is_customized": True,
                        "language": "en",
                    })
                else:
                    items.append({
                        "id": t_seg.id,
                        "segment_order": t_seg.segment_order,
                        "start_time": t_seg.start_time,
                        "end_time": t_seg.end_time,
                        "text": t_seg.text,
                        "source_text": t_seg.text,
                        "is_customized": False,
                        "language": "en",
                    })

        else:
            # Khmer subtitles derive from translation_segments
            trans_segments = (
                db.query(TranslationSegment)
                .filter(TranslationSegment.project_id == project_id)
                .order_by(TranslationSegment.segment_order)
                .all()
            )

            # Map transcript segments for start and end timestamps
            t_segments = (
                db.query(TranscriptSegment)
                .filter(TranscriptSegment.project_id == project_id)
                .all()
            )
            t_map_by_id = {t.id: t for t in t_segments}
            t_map_by_order = {t.segment_order: t for t in t_segments}

            for trans_seg in trans_segments:
                t_seg = t_map_by_id.get(trans_seg.transcript_segment_id) or t_map_by_order.get(trans_seg.segment_order)
                start_time = t_seg.start_time if t_seg else 0.0
                end_time = t_seg.end_time if t_seg else (start_time + 1.0)

                custom = custom_map.get(trans_seg.segment_order)
                if custom and custom.is_customized:
                    items.append({
                        "id": custom.id,
                        "segment_order": trans_seg.segment_order,
                        "start_time": custom.start_time,
                        "end_time": custom.end_time,
                        "text": custom.text,
                        "source_text": trans_seg.khmer_text,
                        "is_customized": True,
                        "language": "km",
                    })
                else:
                    items.append({
                        "id": trans_seg.id,
                        "segment_order": trans_seg.segment_order,
                        "start_time": start_time,
                        "end_time": end_time,
                        "text": trans_seg.khmer_text,
                        "source_text": trans_seg.khmer_text,
                        "is_customized": False,
                        "language": "km",
                    })

        return {
            "project_id": project_id,
            "language": lang,
            "has_custom_edits": any(item["is_customized"] for item in items),
            "total_segments": len(items),
            "segments": items,
        }

    @classmethod
    def update_subtitle_segment(
        cls,
        project_id: str,
        language: str,
        segment_order: int,
        text: str,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Update or create a customized subtitle segment.
        Does NOT alter source TranslationSegment or TranscriptSegment, preserving TTS audio!
        """
        lang = cls.normalize_language(language)
        cleaned_text = (text or "").strip()

        # Find existing custom record
        custom = (
            db.query(SubtitleSegment)
            .filter(
                SubtitleSegment.project_id == project_id,
                SubtitleSegment.language == lang,
                SubtitleSegment.segment_order == segment_order,
            )
            .first()
        )

        if custom:
            custom.text = cleaned_text
            custom.is_customized = True
            custom.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(custom)
            return {
                "id": custom.id,
                "segment_order": custom.segment_order,
                "start_time": custom.start_time,
                "end_time": custom.end_time,
                "text": custom.text,
                "is_customized": True,
                "language": lang,
            }

        # Need to determine start_time and end_time from source segment
        start_time = 0.0
        end_time = 1.0

        if lang == "en":
            t_seg = (
                db.query(TranscriptSegment)
                .filter(
                    TranscriptSegment.project_id == project_id,
                    TranscriptSegment.segment_order == segment_order,
                )
                .first()
            )
            if t_seg:
                start_time = t_seg.start_time
                end_time = t_seg.end_time
        else:
            trans_seg = (
                db.query(TranslationSegment)
                .filter(
                    TranslationSegment.project_id == project_id,
                    TranslationSegment.segment_order == segment_order,
                )
                .first()
            )
            if trans_seg:
                t_seg = (
                    db.query(TranscriptSegment)
                    .filter(TranscriptSegment.id == trans_seg.transcript_segment_id)
                    .first()
                ) or (
                    db.query(TranscriptSegment)
                    .filter(
                        TranscriptSegment.project_id == project_id,
                        TranscriptSegment.segment_order == segment_order,
                    )
                    .first()
                )
                if t_seg:
                    start_time = t_seg.start_time
                    end_time = t_seg.end_time

        new_segment = SubtitleSegment(
            project_id=project_id,
            language=lang,
            segment_order=segment_order,
            start_time=start_time,
            end_time=end_time,
            text=cleaned_text,
            is_customized=True,
        )
        db.add(new_segment)
        db.commit()
        db.refresh(new_segment)

        return {
            "id": new_segment.id,
            "segment_order": new_segment.segment_order,
            "start_time": new_segment.start_time,
            "end_time": new_segment.end_time,
            "text": new_segment.text,
            "is_customized": True,
            "language": lang,
        }

    @classmethod
    def reset_subtitles(
        cls,
        project_id: str,
        language: str,
        db: Session,
    ) -> int:
        """
        Reset all customized subtitle edits for a project and language back to source text.
        """
        lang = cls.normalize_language(language)
        count = (
            db.query(SubtitleSegment)
            .filter(
                SubtitleSegment.project_id == project_id,
                SubtitleSegment.language == lang,
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        return count

    @classmethod
    def export_subtitles(
        cls,
        project_id: str,
        language: str,
        format_type: str,
        db: Session,
    ) -> Tuple[str, str, str]:
        """
        Generate and optionally cache SRT or WebVTT subtitles.
        Returns: (content_str, filename, mime_type)
        """
        lang = cls.normalize_language(language)
        fmt = (format_type or "srt").strip().lower()
        if fmt not in ("srt", "vtt"):
            raise ValueError(f"Unsupported subtitle format '{format_type}'. Expected 'srt' or 'vtt'.")

        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project '{project_id}' not found")

        subtitle_data = cls.get_subtitles(project_id=project_id, language=lang, db=db)
        segments = subtitle_data.get("segments", [])

        cues: List[SubtitleCue] = []
        for s in segments:
            cues.append(
                SubtitleCue(
                    sequence=s["segment_order"],
                    start_time=s["start_time"],
                    end_time=s["end_time"],
                    text=s["text"],
                )
            )

        if fmt == "srt":
            content = generate_srt(cues, prevent_overlaps=True, filter_empty=True)
            mime_type = "text/plain; charset=utf-8"
        else:
            content = generate_vtt(cues, prevent_overlaps=True, filter_empty=True)
            mime_type = "text/vtt; charset=utf-8"

        # Safe project-scoped filename
        safe_title = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", project.title).strip("_") or "subtitles"
        filename = f"{safe_title}_{lang}.{fmt}"

        # Cache file to project storage
        try:
            cache_path = get_subtitle_file_path(project_id, lang, fmt)
            cache_path.write_text(content, encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to write subtitle cache file for project %s: %s", project_id, e)

        return content, filename, mime_type
