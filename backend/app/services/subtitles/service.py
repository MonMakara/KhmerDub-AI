import logging
import re
from datetime import datetime
from app.core.timezone import get_cambodia_now_naive
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
from app.services.subtitles.splitter import SubtitleSplitter
from app.core.storage import get_subtitle_file_path

logger = logging.getLogger(__name__)


class SubtitleService:
    """Service managing project subtitles, readability segmentation, and SRT/VTT generation."""

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
    def _get_source_map(cls, project_id: str, lang: str, db: Session) -> Dict[int, Dict[str, Any]]:
        """Fetch underlying source text and timestamps mapped by segment_order."""
        source_map: Dict[int, Dict[str, Any]] = {}
        if lang == "en":
            t_segs = (
                db.query(TranscriptSegment)
                .filter(TranscriptSegment.project_id == project_id)
                .order_by(TranscriptSegment.segment_order.asc())
                .all()
            )
            for t in t_segs:
                source_map[t.segment_order] = {
                    "id": t.id,
                    "order": t.segment_order,
                    "start_time": t.start_time,
                    "end_time": t.end_time,
                    "text": t.text,
                    "hash": SubtitleSplitter.compute_source_hash(t.text),
                }
        else:
            trans_segs = (
                db.query(TranslationSegment)
                .filter(TranslationSegment.project_id == project_id)
                .order_by(TranslationSegment.segment_order.asc())
                .all()
            )
            t_segs = (
                db.query(TranscriptSegment)
                .filter(TranscriptSegment.project_id == project_id)
                .all()
            )
            t_by_id = {t.id: t for t in t_segs}
            t_by_order = {t.segment_order: t for t in t_segs}

            for tr in trans_segs:
                t = t_by_id.get(tr.transcript_segment_id) or t_by_order.get(tr.segment_order)
                start = t.start_time if t else 0.0
                end = t.end_time if t else (start + 1.0)
                source_map[tr.segment_order] = {
                    "id": tr.id,
                    "order": tr.segment_order,
                    "start_time": start,
                    "end_time": end,
                    "text": tr.khmer_text,
                    "hash": SubtitleSplitter.compute_source_hash(tr.khmer_text),
                }
        return source_map

    @classmethod
    def get_subtitles(
        cls,
        project_id: str,
        language: str,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Fetch subtitle cues for a project and language.
        Merges custom subtitle edits with source segment changes and calculates readability indicators.
        """
        lang = cls.normalize_language(language)
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project '{project_id}' not found")

        source_map = cls._get_source_map(project_id, lang, db)

        # 1. Fetch custom subtitle records
        custom_records = (
            db.query(SubtitleSegment)
            .filter(
                SubtitleSegment.project_id == project_id,
                SubtitleSegment.language == lang,
            )
            .order_by(SubtitleSegment.segment_order.asc())
            .all()
        )

        items: List[Dict[str, Any]] = []

        is_full_custom_timeline = (
            len(custom_records) >= len(source_map)
            or any(r.segment_order > len(source_map) for r in custom_records)
        )

        if custom_records and is_full_custom_timeline:
            for r in custom_records:
                src_order = r.source_segment_order or r.segment_order
                src = source_map.get(src_order)
                src_text = src["text"] if src else None
                current_src_hash = src["hash"] if src else None

                # Detect if source has been updated since customization
                is_outdated = False
                if r.is_customized and r.source_text_hash and current_src_hash:
                    if r.source_text_hash != current_src_hash:
                        is_outdated = True
                elif r.is_source_outdated:
                    is_outdated = True

                readability = SubtitleSplitter.calculate_readability(
                    text=r.text,
                    start_time=r.start_time,
                    end_time=r.end_time,
                    language=lang,
                )

                items.append({
                    "id": r.id,
                    "segment_order": r.segment_order,
                    "start_time": round(r.start_time, 3),
                    "end_time": round(r.end_time, 3),
                    "text": r.text,
                    "source_text": src_text,
                    "source_segment_order": src_order,
                    "timing_confidence": r.timing_confidence or "verified",
                    "is_source_outdated": is_outdated,
                    "is_customized": r.is_customized,
                    "language": lang,
                    "readability": readability,
                })
        else:
            custom_map = {r.segment_order: r for r in custom_records}
            for order in sorted(source_map.keys()):
                src = source_map[order]
                if order in custom_map:
                    r = custom_map[order]
                    current_src_hash = src["hash"]
                    is_outdated = False
                    if r.is_customized and r.source_text_hash and current_src_hash:
                        if r.source_text_hash != current_src_hash:
                            is_outdated = True
                    elif r.is_source_outdated:
                        is_outdated = True

                    readability = SubtitleSplitter.calculate_readability(
                        text=r.text,
                        start_time=r.start_time,
                        end_time=r.end_time,
                        language=lang,
                    )
                    items.append({
                        "id": r.id,
                        "segment_order": r.segment_order,
                        "start_time": round(r.start_time, 3),
                        "end_time": round(r.end_time, 3),
                        "text": r.text,
                        "source_text": src["text"],
                        "source_segment_order": order,
                        "timing_confidence": r.timing_confidence or "verified",
                        "is_source_outdated": is_outdated,
                        "is_customized": r.is_customized,
                        "language": lang,
                        "readability": readability,
                    })
                else:
                    readability = SubtitleSplitter.calculate_readability(
                        text=src["text"],
                        start_time=src["start_time"],
                        end_time=src["end_time"],
                        language=lang,
                    )
                    items.append({
                        "id": src["id"],
                        "segment_order": src["order"],
                        "start_time": round(src["start_time"], 3),
                        "end_time": round(src["end_time"], 3),
                        "text": src["text"],
                        "source_text": src["text"],
                        "source_segment_order": src["order"],
                        "timing_confidence": "verified",
                        "is_source_outdated": False,
                        "is_customized": False,
                        "language": lang,
                        "readability": readability,
                    })

        return {
            "project_id": project_id,
            "language": lang,
            "has_custom_edits": any(item["is_customized"] for item in items),
            "total_segments": len(items),
            "segments": items,
        }

    @classmethod
    def _materialize_all_if_needed(cls, project_id: str, lang: str, db: Session) -> List[SubtitleSegment]:
        """Ensure all cues exist as persisted SubtitleSegment rows in DB."""
        existing = (
            db.query(SubtitleSegment)
            .filter(
                SubtitleSegment.project_id == project_id,
                SubtitleSegment.language == lang,
            )
            .order_by(SubtitleSegment.segment_order.asc())
            .all()
        )
        if existing:
            return existing

        # Populate from source map
        source_map = cls._get_source_map(project_id, lang, db)
        created: List[SubtitleSegment] = []
        for order in sorted(source_map.keys()):
            src = source_map[order]
            seg = SubtitleSegment(
                project_id=project_id,
                language=lang,
                segment_order=src["order"],
                start_time=src["start_time"],
                end_time=src["end_time"],
                text=src["text"],
                source_segment_order=src["order"],
                source_text_hash=src["hash"],
                timing_confidence="verified",
                is_source_outdated=False,
                is_customized=False,
            )
            db.add(seg)
            created.append(seg)
        db.commit()
        for c in created:
            db.refresh(c)
        return created

    @classmethod
    def update_subtitle_segment(
        cls,
        project_id: str,
        language: str,
        segment_order: int,
        text: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        db: Session = None,
    ) -> Dict[str, Any]:
        """
        Update text and/or timestamps of a subtitle segment.
        Validates timestamps to prevent invalid intervals or overlaps.
        Does NOT alter source TranslationSegment or TranscriptSegment.
        """
        lang = cls.normalize_language(language)
        source_map = cls._get_source_map(project_id, lang, db)

        target = (
            db.query(SubtitleSegment)
            .filter(
                SubtitleSegment.project_id == project_id,
                SubtitleSegment.language == lang,
                SubtitleSegment.segment_order == segment_order,
            )
            .first()
        )
        if not target:
            src = source_map.get(segment_order)
            if not src:
                raise ValueError(f"Subtitle segment with order {segment_order} not found")
            target = SubtitleSegment(
                project_id=project_id,
                language=lang,
                segment_order=segment_order,
                start_time=src["start_time"],
                end_time=src["end_time"],
                text=src["text"],
                source_segment_order=segment_order,
                source_text_hash=src["hash"],
                timing_confidence="verified",
                is_source_outdated=False,
                is_customized=True,
            )
            db.add(target)
            db.flush()

        # Validate and apply timing updates
        new_start = target.start_time if start_time is None else float(start_time)
        new_end = target.end_time if end_time is None else float(end_time)

        if new_start < 0:
            raise ValueError("Start time cannot be negative.")
        if new_end <= new_start:
            raise ValueError(f"End time ({new_end:.2f}s) must be greater than start time ({new_start:.2f}s).")

        # Overlap check with previous cue
        prev_cue = (
            db.query(SubtitleSegment)
            .filter(
                SubtitleSegment.project_id == project_id,
                SubtitleSegment.language == lang,
                SubtitleSegment.segment_order < segment_order,
            )
            .order_by(SubtitleSegment.segment_order.desc())
            .first()
        )
        if not prev_cue and segment_order > 1:
            prev_src = source_map.get(segment_order - 1)
            if prev_src and new_start < prev_src["start_time"]:
                raise ValueError(
                    f"Start time ({new_start:.2f}s) cannot be earlier than previous cue start ({prev_src['start_time']:.2f}s)."
                )
        elif prev_cue:
            if new_start < prev_cue.start_time:
                raise ValueError(
                    f"Start time ({new_start:.2f}s) cannot be earlier than previous cue start ({prev_cue.start_time:.2f}s)."
                )
            if new_start < prev_cue.end_time:
                prev_cue.end_time = new_start

        # Overlap check with next cue
        next_cue = (
            db.query(SubtitleSegment)
            .filter(
                SubtitleSegment.project_id == project_id,
                SubtitleSegment.language == lang,
                SubtitleSegment.segment_order > segment_order,
            )
            .order_by(SubtitleSegment.segment_order.asc())
            .first()
        )
        if not next_cue and (segment_order + 1) in source_map:
            next_src = source_map.get(segment_order + 1)
            if next_src and new_end > next_src["end_time"]:
                raise ValueError(
                    f"End time ({new_end:.2f}s) cannot exceed next cue end time ({next_src['end_time']:.2f}s)."
                )
        elif next_cue:
            if new_end > next_cue.end_time:
                raise ValueError(
                    f"End time ({new_end:.2f}s) cannot exceed next cue end time ({next_cue.end_time:.2f}s)."
                )
            if new_end > next_cue.start_time:
                next_cue.start_time = new_end

        timing_changed = (
            abs(new_start - target.start_time) > 0.001 or abs(new_end - target.end_time) > 0.001
        )
        target.start_time = round(new_start, 3)
        target.end_time = round(new_end, 3)

        if text is not None:
            clean_text = text.strip()
            if not clean_text:
                raise ValueError("Subtitle text cannot be empty.")
            target.text = clean_text

        if timing_changed:
            target.timing_confidence = "manual"

        target.is_customized = True
        target.updated_at = get_cambodia_now_naive()

        db.commit()
        db.refresh(target)

        readability = SubtitleSplitter.calculate_readability(
            text=target.text,
            start_time=target.start_time,
            end_time=target.end_time,
            language=lang,
        )

        return {
            "id": target.id,
            "segment_order": target.segment_order,
            "start_time": target.start_time,
            "end_time": target.end_time,
            "text": target.text,
            "source_segment_order": target.source_segment_order,
            "timing_confidence": target.timing_confidence,
            "is_source_outdated": target.is_source_outdated,
            "is_customized": True,
            "language": lang,
            "readability": readability,
        }

    @classmethod
    def auto_split_subtitles(
        cls,
        project_id: str,
        language: str,
        max_chars: int = 75,
        max_duration: float = 6.5,
        db: Session = None,
    ) -> Dict[str, Any]:
        """
        Auto-splits long subtitle cues into readable captions with proportional timings.
        Preserves Khmer Unicode and avoids splitting within syllable clusters.
        """
        lang = cls.normalize_language(language)
        sub_data = cls.get_subtitles(project_id, lang, db)
        current_segments = sub_data.get("segments", [])
        if not current_segments:
            return sub_data

        source_map = cls._get_source_map(project_id, lang, db)

        new_cues: List[Dict[str, Any]] = []
        for cue in current_segments:
            text = cue["text"]
            start = cue["start_time"]
            end = cue["end_time"]
            dur = end - start
            src_order = cue.get("source_segment_order") or cue["segment_order"]
            src_hash = source_map.get(src_order, {}).get("hash")

            if len(text) > max_chars or dur > max_duration:
                if lang == "km":
                    chunks = SubtitleSplitter.split_text_khmer(text, max_chars=max_chars)
                else:
                    chunks = SubtitleSplitter.split_text_english(text, max_chars=max_chars)

                if len(chunks) > 1:
                    timings = SubtitleSplitter.estimate_split_timings(chunks, start, end)
                    for (c_start, c_end), chunk_text in zip(timings, chunks):
                        new_cues.append({
                            "start_time": c_start,
                            "end_time": c_end,
                            "text": chunk_text,
                            "source_segment_order": src_order,
                            "source_text_hash": src_hash,
                            "timing_confidence": "estimated",
                            "is_customized": True,
                        })
                    continue

            # Keep as single cue
            new_cues.append({
                "start_time": start,
                "end_time": end,
                "text": text,
                "source_segment_order": src_order,
                "source_text_hash": src_hash,
                "timing_confidence": cue.get("timing_confidence", "verified"),
                "is_customized": cue.get("is_customized", False),
            })

        # Persist new split cues to DB
        db.query(SubtitleSegment).filter(
            SubtitleSegment.project_id == project_id,
            SubtitleSegment.language == lang,
        ).delete(synchronize_session=False)

        for idx, c in enumerate(new_cues):
            seg = SubtitleSegment(
                project_id=project_id,
                language=lang,
                segment_order=idx + 1,
                start_time=c["start_time"],
                end_time=c["end_time"],
                text=c["text"],
                source_segment_order=c["source_segment_order"],
                source_text_hash=c["source_text_hash"],
                timing_confidence=c["timing_confidence"],
                is_source_outdated=False,
                is_customized=c["is_customized"],
            )
            db.add(seg)

        db.commit()
        return cls.get_subtitles(project_id, lang, db)

    @classmethod
    def split_subtitle_cue(
        cls,
        project_id: str,
        language: str,
        segment_order: int,
        split_index: Optional[int] = None,
        split_ratio: Optional[float] = 0.5,
        db: Session = None,
    ) -> Dict[str, Any]:
        """
        Manually split a single subtitle cue into two consecutive cues.
        """
        lang = cls.normalize_language(language)
        cues = cls._materialize_all_if_needed(project_id, lang, db)

        cue_idx = -1
        for i, c in enumerate(cues):
            if c.segment_order == segment_order:
                cue_idx = i
                break

        if cue_idx == -1:
            raise ValueError(f"Cue with order {segment_order} not found")

        target = cues[cue_idx]
        text = target.text.strip()
        if len(text) < 4:
            raise ValueError("Cue text is too short to split.")

        # Determine split position
        if split_index is not None and 1 <= split_index < len(text):
            if lang == "km":
                safe_pos = SubtitleSplitter.find_nearest_safe_khmer_index(text, split_index)
            else:
                safe_pos = split_index
        else:
            ratio = max(0.2, min(0.8, float(split_ratio or 0.5)))
            target_pos = int(len(text) * ratio)
            if lang == "km":
                safe_pos = SubtitleSplitter.find_nearest_safe_khmer_index(text, target_pos)
            else:
                # Find nearest space
                space_before = text.rfind(" ", 0, target_pos)
                space_after = text.find(" ", target_pos)
                if space_before != -1:
                    safe_pos = space_before
                elif space_after != -1:
                    safe_pos = space_after
                else:
                    safe_pos = target_pos

        left_text = text[:safe_pos].strip()
        right_text = text[safe_pos:].strip()

        if not left_text or not right_text:
            raise ValueError("Could not find a valid boundary to split this subtitle.")

        timings = SubtitleSplitter.estimate_split_timings(
            [left_text, right_text], target.start_time, target.end_time
        )
        (t1_start, t1_end), (t2_start, t2_end) = timings

        # Re-index all subsequent cues in memory and DB
        # Shift subsequent cues up by 1 (using descending order to avoid constraint collisions)
        subsequent = (
            db.query(SubtitleSegment)
            .filter(
                SubtitleSegment.project_id == project_id,
                SubtitleSegment.language == lang,
                SubtitleSegment.segment_order > segment_order,
            )
            .order_by(SubtitleSegment.segment_order.desc())
            .all()
        )
        for s in subsequent:
            s.segment_order = s.segment_order + 1
        db.flush()

        # Update first half
        target.text = left_text
        target.start_time = t1_start
        target.end_time = t1_end
        target.timing_confidence = "estimated"
        target.is_customized = True

        # Insert second half at segment_order + 1
        new_cue = SubtitleSegment(
            project_id=project_id,
            language=lang,
            segment_order=segment_order + 1,
            start_time=t2_start,
            end_time=t2_end,
            text=right_text,
            source_segment_order=target.source_segment_order,
            source_text_hash=target.source_text_hash,
            timing_confidence="estimated",
            is_source_outdated=target.is_source_outdated,
            is_customized=True,
        )
        db.add(new_cue)
        db.commit()

        return cls.get_subtitles(project_id, lang, db)

    @classmethod
    def merge_subtitle_cues(
        cls,
        project_id: str,
        language: str,
        segment_order: int,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Merge cue with the next cue (segment_order + 1).
        """
        lang = cls.normalize_language(language)
        cues = cls._materialize_all_if_needed(project_id, lang, db)

        cue_idx = -1
        for i, c in enumerate(cues):
            if c.segment_order == segment_order:
                cue_idx = i
                break

        if cue_idx == -1 or cue_idx >= len(cues) - 1:
            raise ValueError(f"Cannot merge cue {segment_order}: no subsequent cue found.")

        first = cues[cue_idx]
        second = cues[cue_idx + 1]

        # Combine text
        separator = " " if lang == "en" or not first.text.endswith(("។", "៕", "!", "?", "៖")) else " "
        combined_text = f"{first.text}{separator}{second.text}".strip()

        first.text = combined_text
        first.end_time = second.end_time
        first.timing_confidence = "manual"
        first.is_customized = True

        # Delete second cue
        db.delete(second)
        db.flush()

        # Shift all subsequent cues down by 1
        subsequent = (
            db.query(SubtitleSegment)
            .filter(
                SubtitleSegment.project_id == project_id,
                SubtitleSegment.language == lang,
                SubtitleSegment.segment_order > second.segment_order,
            )
            .order_by(SubtitleSegment.segment_order.asc())
            .all()
        )
        for s in subsequent:
            s.segment_order = s.segment_order - 1

        db.commit()
        return cls.get_subtitles(project_id, lang, db)

    @classmethod
    def keep_subtitle_edits(
        cls,
        project_id: str,
        language: str,
        segment_order: int,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Acknowledge source translation changes and clear outdated warning while preserving custom subtitle text.
        """
        lang = cls.normalize_language(language)
        cue = (
            db.query(SubtitleSegment)
            .filter(
                SubtitleSegment.project_id == project_id,
                SubtitleSegment.language == lang,
                SubtitleSegment.segment_order == segment_order,
            )
            .first()
        )
        if not cue:
            raise ValueError(f"Cue {segment_order} not found.")

        source_map = cls._get_source_map(project_id, lang, db)
        src_order = cue.source_segment_order or cue.segment_order
        src_info = source_map.get(src_order)

        if src_info:
            cue.source_text_hash = src_info["hash"]

        cue.is_source_outdated = False
        db.commit()
        db.refresh(cue)

        return cls.get_subtitles(project_id, lang, db)

    @classmethod
    def reset_subtitle_cue(
        cls,
        project_id: str,
        language: str,
        segment_order: int,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Reset a single customized subtitle cue to match its source segment text and timestamps.
        """
        lang = cls.normalize_language(language)
        cue = (
            db.query(SubtitleSegment)
            .filter(
                SubtitleSegment.project_id == project_id,
                SubtitleSegment.language == lang,
                SubtitleSegment.segment_order == segment_order,
            )
            .first()
        )
        if not cue:
            raise ValueError(f"Cue {segment_order} not found.")

        source_map = cls._get_source_map(project_id, lang, db)
        src_order = cue.source_segment_order or cue.segment_order
        src_info = source_map.get(src_order)

        if src_info:
            cue.text = src_info["text"]
            cue.start_time = src_info["start_time"]
            cue.end_time = src_info["end_time"]
            cue.source_text_hash = src_info["hash"]
            cue.timing_confidence = "verified"
            cue.is_source_outdated = False
            cue.is_customized = False
            db.commit()

        return cls.get_subtitles(project_id, lang, db)

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
