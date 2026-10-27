import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy.orm import Session

from app.core.storage import resolve_audio_file, get_audio_segment_path
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
        self.max_tempo = max_tempo
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
        tempo_cap = max_tempo or self.max_tempo
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

                trans_seg_map[t_id] = trans_seg
                raw_items.append({
                    "idx": idx,
                    "segment_order": seg_order,
                    "segment_id": t_id,
                    "audio_path": Path(audio_rec.audio_path) if (audio_rec and audio_rec.audio_path) else None,
                    "start_time": start_time,
                    "end_time": end_time,
                    "orig_duration": slot_dur,
                    "raw_duration": raw_dur,
                    "khmer_text": trans_seg.khmer_text or "",
                    "english_text": english_text,
                    "is_manually_edited": bool(trans_seg.is_manually_edited),
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
                        trimmed_duration=p.raw_duration,
                        required_tempo=p.required_tempo,
                        tempo_factor=p.applied_tempo,
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

    def optimize_project(
        self,
        project_id: str,
        db: Session,
        max_tempo: Optional[float] = None,
        max_attempts_per_segment: int = 2,
        target_char_rate: float = 11.0,
    ) -> TimelineOptimizationResult:
        """Execute automated multi-tier timing optimization across the project:
        1. Edge silence trimming on all synthesized audio segments.
        2. Safe gap scheduling & minimal speed adjustment planning.
        3. Bounded automatic sentence shortening & selective single-segment re-synthesis
           for any remaining overflowing segments.
        4. Strict validation preventing silent truncation or cumulative drift.
        """
        tempo_cap = max_tempo or self.max_tempo
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        pipeline_ver = getattr(project, "pipeline_version", "v1") or "v1"

        # Tier 1: Trim edge silence on all existing audio segments in-place (legacy only; v2.1/v2.2 preserves complete speech)
        trimmed_count = 0
        if pipeline_ver not in ("v2.1", "v2.2", "v2.3") and project.translation_segments:
            for trans_seg in project.translation_segments:
                audio_rec = trans_seg.generated_audio
                if audio_rec and audio_rec.audio_path:
                    dest = resolve_audio_file(project_id, trans_seg.id, audio_rec.audio_path)
                    if dest.exists() and dest.stat().st_size > 0:
                        try:
                            self.sync_service.trim_audio_silence(dest, dest)
                            new_d = self.video_processor.get_audio_duration(dest)
                            if new_d > 0.0 and abs(new_d - (audio_rec.duration_seconds or 0.0)) > 0.05:
                                audio_rec.duration_seconds = new_d
                                trimmed_count += 1
                        except Exception as e:
                            logger.warning("Silence trim failed for segment #%d: %s", trans_seg.segment_order, e)
            db.commit()

        # Tier 2: Analyze timeline budgets with silence gap allocation
        analysis = self.analyze_timeline(project_id, db, max_tempo=tempo_cap)
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

        tts_provider_name = project.tts_provider or "gtts"
        tts_voice = project.tts_voice or "default"
        tts_provider = get_tts_provider(tts_provider_name)

        # Deterministic project seed for acoustic consistency across speech re-synthesis
        import hashlib
        project_seed = int(hashlib.md5(project_id.encode("utf-8")).hexdigest()[:8], 16)

        sentence_optimized_count = 0
        segments_updated_count = 0

        # Tier 3: Selective sentence optimization for overflow segments
        # In v2.1/v2.2, speech completeness and translation preservation strictly take precedence over
        # automated text deletion. We do not perform lossy character or word slicing.
        if pipeline_ver in ("v2.1", "v2.2", "v2.3"):
            overflow_items = []
        else:
            overflow_items = [item for item in analysis if item.status == "needs_optimization"]

        for item in overflow_items:
            # Safeguard: never overwrite manually approved translations without user intent
            if item.is_manually_edited:
                logger.info(
                    "Skipping automated rewrite for manually edited segment #%d",
                    item.segment_order,
                )
                continue

            trans_seg = (
                db.query(TranslationSegment)
                .filter(TranslationSegment.id == item.translation_segment_id)
                .first()
            )
            audio_rec = (
                db.query(GeneratedAudio)
                .filter(GeneratedAudio.translation_segment_id == item.translation_segment_id)
                .first()
            )
            if not trans_seg or not audio_rec:
                continue

            current_text = trans_seg.khmer_text
            effective_win = item.effective_window
            target_chars = max(18, int(effective_win * target_char_rate))

            # Bounded attempts (max 2 attempts)
            resolved = False
            for attempt in range(1, max_attempts_per_segment + 1):
                # Budget character count slightly tighter on second attempt
                attempt_budget = target_chars if attempt == 1 else max(16, int(target_chars * 0.88))
                shortened = shorten_khmer_text(current_text, target_char_count=attempt_budget)

                if shortened == current_text and attempt > 1:
                    # Further trim common filler adverbials
                    shortened = re.sub(r"(យ៉ាងខ្លាំង|យ៉ាងលឿន|យ៉ាងច្បាស់|មែនទែន)", "", shortened).strip()
                    if not shortened.endswith("។"):
                        shortened += "។"

                if shortened == current_text:
                    # Shortening produced no difference
                    continue

                dest_audio = resolve_audio_file(project_id, trans_seg.id, audio_rec.audio_path)
                dest_audio.parent.mkdir(parents=True, exist_ok=True)

                try:
                    tts_res = tts_provider.synthesize(
                        text=shortened,
                        output_path=dest_audio,
                        language="km",
                        voice=tts_voice,
                        seed=project_seed,
                    )
                    self.sync_service.trim_audio_silence(dest_audio, dest_audio)
                    new_dur = self.video_processor.get_audio_duration(dest_audio)
                    if new_dur <= 0.0 and tts_res and tts_res.duration_seconds:
                        new_dur = tts_res.duration_seconds

                    # Update records
                    trans_seg.khmer_text = shortened
                    trans_seg.is_manually_edited = False
                    trans_seg.is_outdated = False
                    audio_rec.duration_seconds = new_dur
                    audio_rec.is_outdated = False
                    current_text = shortened
                    segments_updated_count += 1

                    # Check if fits within tempo limit
                    req_tempo = round(new_dur / effective_win, 3)
                    if req_tempo <= tempo_cap:
                        resolved = True
                        sentence_optimized_count += 1
                        break

                except Exception as e:
                    logger.error(
                        "Re-synthesis failed during auto-optimization of segment #%d (attempt %d): %s",
                        item.segment_order,
                        attempt,
                        e,
                    )
                    break

            if resolved:
                logger.info(
                    "Successfully auto-optimized segment #%d to %.2fs (required tempo %.2fx)",
                    item.segment_order,
                    audio_rec.duration_seconds,
                    req_tempo,
                )

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
