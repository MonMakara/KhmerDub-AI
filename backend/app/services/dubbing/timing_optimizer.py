import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session

from app.core.storage import resolve_audio_file
from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
)
from app.services.dubbing.auto_fit import shorten_khmer_text
from app.services.dubbing.scheduler import TimelineScheduler
from app.services.dubbing.synchronizer import AudioSynchronizationService
from app.services.tts.registry import get_tts_provider
from app.services.video.ffmpeg import FFmpegVideoProcessor

logger = logging.getLogger(__name__)


@dataclass
class SegmentTimingAnalysis:
    """Detailed timing budget and status for a single speech segment."""
    segment_order: int
    transcript_segment_id: str
    translation_segment_id: str
    start_time: float
    end_time: float
    slot_duration: float
    next_start: float
    inter_segment_gap: float
    available_window: float
    effective_window: float
    audio_path: Optional[str]
    raw_duration: float
    trimmed_duration: float
    required_tempo: float
    tempo_factor: float
    status: str  # "natural", "speed_adjusted", "needs_optimization", "unresolved"
    overflow_seconds: float
    khmer_text: str
    english_text: str
    is_manually_edited: bool
    scheduled_start: float = 0.0
    scheduled_end: float = 0.0
    processed_duration: float = 0.0
    local_overflow_seconds: float = 0.0
    alignment_delay_seconds: float = 0.0


@dataclass
class TimelineOptimizationResult:
    """Overall summary of automatic timing optimization across a project."""
    project_id: str
    pipeline_version: str
    total_segments: int
    fitted_naturally: int
    speed_adjusted: int
    sentence_optimized: int
    unresolved_conflicts: int
    segments_updated: int
    conflicts: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_export_ready(self) -> bool:
        return self.unresolved_conflicts == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "pipeline_version": self.pipeline_version,
            "total_segments": self.total_segments,
            "fitted_naturally": self.fitted_naturally,
            "speed_adjusted": self.speed_adjusted,
            "sentence_optimized": self.sentence_optimized,
            "automatically_optimized": self.speed_adjusted + self.sentence_optimized,
            "unresolved_conflicts": self.unresolved_conflicts,
            "segments_updated": self.segments_updated,
            "is_export_ready": self.is_export_ready,
            "status": "ready" if self.is_export_ready else "review_required",
            "conflicts": self.conflicts,
        }


class TimingOptimizerService:
    """Production-grade service that automatically prevents and resolves speech timing
    mismatches for new dubbing projects while strictly preserving audio integrity,
    original video runtime, and custom voice identity without silent truncation.
    """

    def __init__(
        self,
        video_processor: Optional[FFmpegVideoProcessor] = None,
        sync_service: Optional[AudioSynchronizationService] = None,
        max_tempo: float = 1.25,
        min_pause_seconds: float = 0.08,
        safety_margin_seconds: float = 0.05,
    ):
        self.video_processor = video_processor or FFmpegVideoProcessor()
        self.sync_service = sync_service or AudioSynchronizationService(video_processor=self.video_processor)
        self.max_tempo = float(max_tempo) if max_tempo is not None else 1.25
        self.min_pause_seconds = min_pause_seconds
        self.safety_margin_seconds = safety_margin_seconds

    def analyze_timeline(
        self,
        project_id: str,
        db: Session,
        max_tempo: Optional[float] = None,
    ) -> List[SegmentTimingAnalysis]:
        """Perform deterministic conflict-aware analysis of all speech segments,
        inter-sentence pauses, required tempo adjustments, and timing budgets.
        """
        tempo_cap = float(max_tempo) if max_tempo is not None else self.max_tempo
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        video = project.video or db.query(Video).filter(Video.project_id == project_id).first()
        target_dur = float(video.duration_seconds or 0.0) if video else 0.0

        sorted_trans = (
            db.query(TranslationSegment)
            .filter(TranslationSegment.project_id == project_id)
            .order_by(TranslationSegment.segment_order.asc())
            .all()
        )

        analysis_items: List[SegmentTimingAnalysis] = []
        pipeline_ver = getattr(project, "pipeline_version", "v1") or "v1"

        if pipeline_ver in ("v2.1", "v2.2", "v2.3"):
            # --- V2.1/V2.2/V2.3: Phrase-Group & Whole-Timeline Adaptive Budget Analysis ---
            raw_items = []
            trans_seg_map = {}
            for idx, trans_seg in enumerate(sorted_trans):
                t_seg = (
                    trans_seg.transcript_segment
                    or db.query(TranscriptSegment).filter(TranscriptSegment.id == trans_seg.transcript_segment_id).first()
                )
                audio_rec = (
                    trans_seg.generated_audio
                    or db.query(GeneratedAudio).filter(GeneratedAudio.translation_segment_id == trans_seg.id).first()
                )
                if not t_seg and trans_seg.start_time is None:
                    continue
                start_time = max(0.0, float(trans_seg.start_time if trans_seg.start_time is not None else t_seg.start_time))
                end_time = max(start_time, float(trans_seg.end_time if trans_seg.end_time is not None else t_seg.end_time))
                slot_dur = max(0.1, end_time - start_time)
                raw_dur = float(audio_rec.duration_seconds or 0.0) if audio_rec else 0.0
                seg_order = trans_seg.segment_order
                t_id = trans_seg.transcript_segment_id or (t_seg.id if t_seg else f"trans_{trans_seg.id}")
                english_text = trans_seg.source_text or (t_seg.text if t_seg else "")

                is_outdated = bool((audio_rec and audio_rec.is_outdated) or trans_seg.is_outdated)
                is_missing = bool(audio_rec is None or not audio_rec.audio_path)

                audio_file = None
                if audio_rec and audio_rec.audio_path:
                    resolved_p = resolve_audio_file(project_id, trans_seg.id, audio_rec.audio_path)
                    if resolved_p.exists():
                        audio_file = resolved_p

                trans_seg_map[t_id] = trans_seg
                raw_items.append({
                    "idx": idx,
                    "segment_order": seg_order,
                    "segment_id": t_id,
                    "audio_path": audio_file,
                    "start_time": start_time,
                    "end_time": end_time,
                    "orig_duration": slot_dur,
                    "raw_duration": raw_dur,
                    "khmer_text": trans_seg.khmer_text or "",
                    "english_text": english_text,
                    "is_manually_edited": bool(trans_seg.is_manually_edited),
                    "is_outdated": is_outdated,
                    "is_missing": is_missing,
                })

            scheduler = TimelineScheduler(
                max_tempo=tempo_cap,
                safety_margin_seconds=self.safety_margin_seconds,
            )
            scheduled_groups = scheduler.schedule_timeline(
                raw_items,
                target_duration=target_dur,
                max_tempo=tempo_cap,
            )

            all_pieces = []
            for g in scheduled_groups:
                for p in g.pieces:
                    all_pieces.append((g, p))

            for idx_p, (g, p) in enumerate(all_pieces):
                t_seg_id = p.segment_id
                trans_seg = trans_seg_map.get(t_seg_id)
                if idx_p < len(all_pieces) - 1:
                    item_next_start = all_pieces[idx_p + 1][1].start_time
                    item_gap = max(0.0, item_next_start - p.end_time)
                else:
                    item_next_start = target_dur if target_dur > 0 else p.end_time
                    item_gap = max(0.0, item_next_start - p.end_time)

                analysis_items.append(
                    SegmentTimingAnalysis(
                        segment_order=p.segment_order,
                        transcript_segment_id=t_seg_id,
                        translation_segment_id=trans_seg.id if trans_seg else t_seg_id,
                        start_time=p.start_time,
                        end_time=p.end_time,
                        slot_duration=p.orig_duration,
                        next_start=round(item_next_start, 2),
                        inter_segment_gap=round(item_gap, 2),
                        available_window=p.available_window,
                        effective_window=p.effective_window,
                        audio_path=str(p.audio_path) if p.audio_path else None,
                        raw_duration=p.raw_duration,
                        trimmed_duration=p.trimmed_duration if p.trimmed_duration > 0.0 else p.raw_duration,
                        required_tempo=p.required_tempo,
                        tempo_factor=p.applied_tempo,
                        local_overflow_seconds=p.local_overflow_seconds,
                        alignment_delay_seconds=p.alignment_delay_seconds,
                        scheduled_start=p.scheduled_start,
                        scheduled_end=p.scheduled_end,
                        processed_duration=p.processed_duration,
                        status=p.status,
                        overflow_seconds=p.overflow_seconds,
                        khmer_text=p.khmer_text,
                        english_text=p.english_text,
                        is_manually_edited=p.is_manually_edited,
                    )
                )

            return analysis_items

        for idx, trans_seg in enumerate(sorted_trans):
            t_seg = (
                trans_seg.transcript_segment
                or db.query(TranscriptSegment).filter(TranscriptSegment.id == trans_seg.transcript_segment_id).first()
            )
            audio_rec = (
                trans_seg.generated_audio
                or db.query(GeneratedAudio).filter(GeneratedAudio.translation_segment_id == trans_seg.id).first()
            )

            if not t_seg:
                continue

            start_time = max(0.0, float(t_seg.start_time))
            end_time = max(start_time, float(t_seg.end_time))
            slot_dur = max(0.1, end_time - start_time)

            # Determine next segment start time to allocate inter-sentence pause safely
            if idx < len(sorted_trans) - 1:
                next_trans = sorted_trans[idx + 1]
                next_t = (
                    next_trans.transcript_segment
                    or db.query(TranscriptSegment).filter(TranscriptSegment.id == next_trans.transcript_segment_id).first()
                )
                next_start = float(next_t.start_time) if next_t else end_time
                if next_start > start_time:
                    gap = max(0.0, next_start - end_time)
                    # Safe window extends into gap while strictly preserving min_pause before next utterance
                    avail_window = min(next_start - start_time - self.min_pause_seconds, target_dur - start_time) if target_dur > 0 else (next_start - start_time - self.min_pause_seconds)
                else:
                    gap = 0.0
                    avail_window = slot_dur
            else:
                next_start = target_dur if target_dur > 0 else end_time
                gap = max(0.0, next_start - end_time)
                avail_window = (target_dur - start_time) if target_dur > 0 else slot_dur

            avail_window = max(0.1, avail_window)
            effective_window = max(0.05, round(avail_window - self.safety_margin_seconds, 3))

            raw_dur = float(audio_rec.duration_seconds or 0.0) if audio_rec else 0.0
            trimmed_dur = raw_dur

            # Evaluate required tempo
            if raw_dur > 0.0:
                required_tempo = round(raw_dur / effective_window, 3)
            else:
                required_tempo = 1.0

            overflow = 0.0
            if required_tempo <= 1.0:
                status = "natural"
                tempo_factor = 1.0
            elif required_tempo <= tempo_cap:
                status = "speed_adjusted"
                tempo_factor = required_tempo
            else:
                status = "needs_optimization"
                tempo_factor = tempo_cap
                overflow = round((raw_dur / tempo_cap) - effective_window, 2)

            analysis_items.append(
                SegmentTimingAnalysis(
                    segment_order=t_seg.segment_order,
                    transcript_segment_id=t_seg.id,
                    translation_segment_id=trans_seg.id,
                    start_time=round(start_time, 2),
                    end_time=round(end_time, 2),
                    slot_duration=round(slot_dur, 2),
                    next_start=round(next_start, 2),
                    inter_segment_gap=round(gap, 2),
                    available_window=round(avail_window, 2),
                    effective_window=round(effective_window, 2),
                    audio_path=audio_rec.audio_path if audio_rec else None,
                    raw_duration=round(raw_dur, 2),
                    trimmed_duration=round(trimmed_dur, 2),
                    required_tempo=round(required_tempo, 2),
                    tempo_factor=round(tempo_factor, 2),
                    status=status,
                    overflow_seconds=overflow,
                    khmer_text=trans_seg.khmer_text or "",
                    english_text=t_seg.text or "",
                    is_manually_edited=bool(trans_seg.is_manually_edited),
                )
            )

        return analysis_items

    def optimize_speech_tempo(
        self,
        project_id: str,
        db: Session,
        max_tempo: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Prepare measured variants without replacing raw audio or its duration."""
        tempo_cap = float(max_tempo) if max_tempo is not None else self.max_tempo
        analysis = self.analyze_timeline(project_id, db, max_tempo=tempo_cap)
        # The shared scheduler renders measured variants from immutable masters.
        # Publishing a variant over GeneratedAudio made subsequent analysis treat
        # already accelerated audio as raw and apply acceleration a second time.
        return {
            "project_id": project_id,
            "total_segments": len(analysis),
            "fitted_naturally": sum(a.status == "natural" for a in analysis),
            "speed_adjusted": sum(a.status == "speed_adjusted" for a in analysis),
            "unresolved_conflicts": sum(a.status == "needs_optimization" for a in analysis),
            "segments_updated": 0,
            "details": [{"segment_order": a.segment_order, "applied_speed": a.tempo_factor,
                         "status": a.status, "old_duration": a.raw_duration,
                         "final_duration": a.processed_duration} for a in analysis],
        }

    def optimize_project(
        self,
        project_id: str,
        db: Session,
        max_tempo: Optional[float] = None,
        max_attempts_per_segment: int = 2,
        target_char_rate: float = 11.0,
    ) -> TimelineOptimizationResult:
        """Plan measured timing variants without rewriting text or raw audio."""
        tempo_cap = float(max_tempo) if max_tempo is not None else self.max_tempo
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        pipeline_ver = getattr(project, "pipeline_version", "v1") or "v1"

        # Tier 2: Analyze timeline budgets with silence gap allocation
        analysis = self.analyze_timeline(project_id, db, max_tempo=tempo_cap)
        segments_updated_count = 0
        if not analysis:
            return TimelineOptimizationResult(
                project_id=project_id,
                pipeline_version=pipeline_ver,
                total_segments=0,
                fitted_naturally=0,
                speed_adjusted=0,
                sentence_optimized=0,
                unresolved_conflicts=0,
                segments_updated=0,
            )

        # Text shortening cannot establish semantic equivalence. Preserve the
        # approved text and expose genuine shortages for explicit review.
        sentence_optimized_count = 0

        # Tier 3: Apply intelligent pitch-preserving speech acceleration
        tempo_result = self.optimize_speech_tempo(project_id, db, max_tempo=tempo_cap)
        segments_updated_count += tempo_result.get("segments_updated", 0)

        if segments_updated_count > 0:
            if project.video:
                project.video.is_export_outdated = True
            db.commit()

        # Re-analyze final state
        final_analysis = self.analyze_timeline(project_id, db, max_tempo=tempo_cap)

        fitted_naturally = sum(1 for a in final_analysis if a.status == "natural")
        speed_adjusted = sum(1 for a in final_analysis if a.status == "speed_adjusted")
        unresolved_items = [a for a in final_analysis if a.status == "needs_optimization" and a.overflow_seconds > 0.05]

        unresolved_conflicts = len(unresolved_items)

        conflict_dicts = []
        for u in unresolved_items:
            est_words = max(1, math.ceil(u.overflow_seconds / 0.35))
            action = (
                f"Shorten the Khmer translation for Segment #{u.segment_order} by approximately "
                f"{est_words} word(s) (~{u.overflow_seconds:.1f}s excess), regenerate audio, and retry export."
            )
            conflict_dicts.append({
                "segment_order": u.segment_order,
                "transcript_segment_id": u.transcript_segment_id,
                "translation_segment_id": u.translation_segment_id,
                "start_time": u.start_time,
                "end_time": u.end_time,
                "slot_duration": u.slot_duration,
                "khmer_duration": u.raw_duration,
                "available_window": u.available_window,
                "effective_window": u.effective_window,
                "required_tempo": u.required_tempo,
                "max_tempo_factor": tempo_cap,
                "tempo_factor": u.tempo_factor,
                "overflow_seconds": u.overflow_seconds,
                "suggested_action": action,
                "message": (
                    f"Segment #{u.segment_order} ({u.raw_duration:.1f}s) exceeds available window "
                    f"({u.available_window:.2f}s raw, {u.effective_window:.2f}s effective) "
                    f"by {u.overflow_seconds:.1f}s even at {tempo_cap}x speed. {action}"
                ),
            })

        logger.info(
            "Timing optimization complete for project %s (pipeline=%s): "
            "%d total, %d natural, %d speed-adjusted, %d sentence-optimized, %d unresolved",
            project_id,
            pipeline_ver,
            len(final_analysis),
            fitted_naturally,
            speed_adjusted,
            sentence_optimized_count,
            unresolved_conflicts,
        )

        return TimelineOptimizationResult(
            project_id=project_id,
            pipeline_version=pipeline_ver,
            total_segments=len(final_analysis),
            fitted_naturally=fitted_naturally,
            speed_adjusted=speed_adjusted,
            sentence_optimized=sentence_optimized_count,
            unresolved_conflicts=unresolved_conflicts,
            segments_updated=segments_updated_count,
            conflicts=conflict_dicts,
        )
