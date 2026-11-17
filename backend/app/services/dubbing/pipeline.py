import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Tuple, Callable

from sqlalchemy.orm import Session

from app.core.storage import get_timeline_audio_path, get_exported_video_path
from app.models.project import (
    Project,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
)
from app.services.dubbing.synchronizer import (
    AudioSynchronizationService,
    SynchronizationResult,
    TimingConflict,
)
from app.services.dubbing.exporter import VideoExportService, ExportResult

from app.services.tts.selection import audio_matches_selection, effective_voice

logger = logging.getLogger(__name__)


@dataclass
class DubbingPipelineResult:
    export_result: ExportResult
    sync_result: SynchronizationResult
    timing_conflicts: List[TimingConflict] = field(default_factory=list)


class DubbingPipeline:
    """Orchestrates audio synchronization, timeline composition, and final video export."""

    def __init__(
        self,
        synchronizer: Optional[AudioSynchronizationService] = None,
        exporter: Optional[VideoExportService] = None,
    ):
        self.synchronizer = synchronizer or AudioSynchronizationService()
        self.exporter = exporter or VideoExportService()

    def run(
        self,
        project_id: str,
        db: Session,
        on_progress: Optional[Callable[[int, str], None]] = None,
        strict_validation: bool = True,
        max_tempo_factor: Optional[float] = None,
        trim_silence: Optional[bool] = None,
        fill_mode: str = "natural",
        overflow_policy: str = "allow_overlap",
        preserve_bgm: bool = False,
        ducking_preset: str = "balanced",
        bgm_volume: float = 0.35,
        attenuate_center_vocals: bool = True,
        aspect_ratio: str = "original",
        reframe_mode: str = "blur_pillar",
        burn_subtitles: bool = False,
        subtitle_style: str = "tiktok_yellow",
        subtitle_language: str = "km",
        subtitle_font: Optional[str] = None,
    ) -> DubbingPipelineResult:
        """Execute end-to-end synchronization and export for a project."""
        def report(pct: int, msg: str):
            if on_progress:
                on_progress(pct, msg)

        report(10, "Validating project prerequisites...")
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        video = project.video
        if not video or not video.file_path or not Path(video.file_path).exists():
            raise FileNotFoundError("Original video file is missing or not uploaded.")

        pipeline_ver = getattr(project, "pipeline_version", "v1") or "v1"
        is_v2 = pipeline_ver in ("v2", "v2.1", "v2.2", "v2.3")
        # In v2.1/v2.2, destructive silence trimming is disabled by default to preserve speech phonemes
        active_trim_silence = True if pipeline_ver == "v2" else False
        if trim_silence is not None:
            active_trim_silence = trim_silence

        video_path = Path(video.file_path)
        video_dur = float(video.duration_seconds or 0.0)
        if video_dur <= 0.0:
            # Probe metadata if missing
            meta = self.exporter.video_processor.get_metadata(video_path)
            video_dur = meta.duration_seconds
            video.duration_seconds = video_dur
            db.commit()

        # Query all translated segments
        translation_segments = (
            db.query(TranslationSegment)
            .filter(TranslationSegment.project_id == project_id)
            .order_by(TranslationSegment.segment_order.asc())
            .all()
        )

        if not translation_segments:
            raise ValueError("No translation segments found. Translate transcript first.")

        # Match with transcript segments and generated audios
        segment_items: List[Tuple[TranscriptSegment, TranslationSegment, GeneratedAudio]] = []
        voice_snapshot = {}
        for trans_seg in translation_segments:
            t_seg = trans_seg.transcript_segment
            if not t_seg:
                t_seg = (
                    db.query(TranscriptSegment)
                    .filter(TranscriptSegment.id == trans_seg.transcript_segment_id)
                    .first()
                )
            if not t_seg and getattr(trans_seg, "source_segment_ids", None):
                try:
                    src_ids = json.loads(trans_seg.source_segment_ids)
                    if src_ids:
                        t_seg = db.query(TranscriptSegment).filter(TranscriptSegment.id == src_ids[0]).first()
                except Exception:
                    pass
            if not t_seg and getattr(trans_seg, "start_time", None) is not None:
                # In v2.3, dubbing units have independent timing
                t_seg = TranscriptSegment(
                    id=f"synth_{trans_seg.id}",
                    project_id=project_id,
                    segment_order=trans_seg.segment_order,
                    start_time=trans_seg.start_time,
                    end_time=trans_seg.end_time,
                    text=trans_seg.source_text or "",
                )
            if not t_seg:
                raise ValueError(f"Missing transcript segment for translation #{trans_seg.segment_order}")

            audio_rec = trans_seg.generated_audio
            if not audio_rec:
                audio_rec = (
                    db.query(GeneratedAudio)
                    .filter(GeneratedAudio.translation_segment_id == trans_seg.id)
                    .first()
                )
            if not audio_rec:
                raise ValueError(
                    f"Generated speech audio missing for segment #{trans_seg.segment_order}. "
                    f"Please generate Khmer audio first."
                )

            if not audio_matches_selection(project, trans_seg, audio_rec):
                raise ValueError(
                    f"Speech audio for segment #{trans_seg.segment_order} is outdated "
                    f"because translation text was modified. Please regenerate speech audio."
                )

            segment_items.append((t_seg, trans_seg, audio_rec))
            voice_snapshot[trans_seg.id] = (
                trans_seg.voice_revision, trans_seg.khmer_text,
                effective_voice(project, trans_seg), audio_rec.audio_path,
            )

        report(30, "Aligning speech segments and calculating timing adjustments...")
        timeline_path = get_timeline_audio_path(project_id)

        report(50, "Synthesizing Khmer audio timeline WAV with silence padding...")
        sync_result = self.synchronizer.synchronize(
            project_id=project_id,
            segment_items=segment_items,
            target_duration=video_dur,
            output_timeline_path=timeline_path,
            strict_validation=strict_validation,
            max_tempo_factor=max_tempo_factor,
            trim_silence=active_trim_silence,
            pipeline_version=pipeline_ver,
            fill_mode=fill_mode,
            overflow_policy=overflow_policy,
        )

        report(75, "Remuxing video with synchronized Khmer audio timeline...")
        output_video_path = get_exported_video_path(project_id)
        source_audio_path = video_path

        temp_ass_path: Optional[Path] = None
        try:
            if burn_subtitles:
                report(72, "Generating viral burn-in subtitles with Khmer typography...")
                from app.services.subtitles.service import SubtitleService
                from app.services.subtitles.generator import SubtitleCue, generate_ass
                from app.services.dubbing.exporter import ASPECT_RATIO_PRESETS

                sub_lang = (subtitle_language or "km").strip().lower()
                cues: List[SubtitleCue] = []

                if sub_lang in ("bilingual", "both"):
                    km_res = SubtitleService.get_subtitles(project_id, "km", db)
                    en_res = SubtitleService.get_subtitles(project_id, "en", db)
                    en_map = {
                        s.get("source_segment_order") or s.get("segment_order"): s.get("text", "")
                        for s in en_res.get("segments", [])
                    }
                    for s in km_res.get("segments", []):
                        order = s.get("source_segment_order") or s.get("segment_order")
                        en_txt = (en_map.get(order) or "").strip()
                        km_txt = (s.get("text") or "").strip()
                        if km_txt:
                            from app.services.translation.formatter import KhmerTextFormatter
                            km_txt = KhmerTextFormatter.format(km_txt)
                        if km_txt and en_txt:
                            # Khmer on top, smaller English italic caption below
                            combo_text = f"{km_txt}\\N{{\\fs34\\i1}}{en_txt}"
                        else:
                            combo_text = km_txt or en_txt
                        if combo_text:
                            cues.append(
                                SubtitleCue(
                                    sequence=s.get("segment_order", len(cues) + 1),
                                    start_time=float(s.get("start_time", 0.0)),
                                    end_time=float(s.get("end_time", 0.0)),
                                    text=combo_text,
                                )
                            )
                else:
                    target_code = "en" if sub_lang in ("en", "english") else "km"
                    sub_res = SubtitleService.get_subtitles(project_id, target_code, db)
                    for s in sub_res.get("segments", []):
                        txt = (s.get("text") or "").strip()
                        if txt:
                            if target_code == "km":
                                from app.services.translation.formatter import KhmerTextFormatter
                                txt = KhmerTextFormatter.format(txt)
                            cues.append(
                                SubtitleCue(
                                    sequence=s.get("segment_order", len(cues) + 1),
                                    start_time=float(s.get("start_time", 0.0)),
                                    end_time=float(s.get("end_time", 0.0)),
                                    text=txt,
                                )
                            )

                if cues:
                    # Determine target resolution for ASS script header
                    if aspect_ratio in ASPECT_RATIO_PRESETS:
                        res_x, res_y = ASPECT_RATIO_PRESETS[aspect_ratio]
                    else:
                        try:
                            meta = self.exporter.video_processor.get_metadata(video_path)
                            res_x = meta.get("width") or 1920
                            res_y = meta.get("height") or 1080
                        except Exception:
                            res_x, res_y = (1920, 1080)

                    ass_content = generate_ass(
                        cues=cues,
                        style_name=subtitle_style or "tiktok_yellow",
                        font_name=subtitle_font,
                        play_res_x=res_x,
                        play_res_y=res_y,
                    )
                    if ass_content.strip():
                        temp_ass_path = output_video_path.with_suffix(".burnin.tmp.ass")
                        temp_ass_path.write_text(ass_content, encoding="utf-8")
                        logger.info("Generated %d subtitle cues for burn-in to %s", len(cues), temp_ass_path)

            export_result = self.exporter.export(
                video_path=video_path,
                audio_timeline_path=sync_result.timeline_path,
                output_video_path=output_video_path,
                expected_duration=video_dur,
                preserve_bgm=preserve_bgm,
                ducking_preset=ducking_preset,
                bgm_volume=bgm_volume,
                attenuate_center_vocals=attenuate_center_vocals,
                source_audio_path=source_audio_path,
                aspect_ratio=aspect_ratio,
                reframe_mode=reframe_mode,
                burn_subtitles=burn_subtitles and temp_ass_path is not None,
                subtitle_path=temp_ass_path,
            )
        finally:
            if temp_ass_path and temp_ass_path.exists():
                try:
                    temp_ass_path.unlink()
                except OSError:
                    pass

        report(95, "Verifying exported video integrity...")
        # Check again after slow FFmpeg work. A voice mutation must never make
        # a soundtrack rendered from a previous selection appear current.
        db.expire_all()
        for unit_id, snapshot in voice_snapshot.items():
            revision, text, selected_voice, audio_path = snapshot
            claimed = db.query(TranslationSegment).filter(
                TranslationSegment.id == unit_id,
                TranslationSegment.voice_revision == revision,
                TranslationSegment.khmer_text == text,
                TranslationSegment.is_outdated.is_(False),
            ).update({TranslationSegment.voice_revision: revision}, synchronize_session=False)
            current = db.query(TranslationSegment).filter_by(id=unit_id).first()
            if (claimed != 1 or current is None
                    or effective_voice(project, current) != selected_voice
                    or not current.generated_audio
                    or current.generated_audio.audio_path != audio_path
                    or not audio_matches_selection(project, current, current.generated_audio)):
                db.rollback()
                db.refresh(video)
                video.is_export_outdated = True
                db.commit()
                raise ValueError("Voice or speech changed during export. Regenerate affected speech and export again.")
        # Update video record with export metadata
        video.exported_video_path = str(export_result.video_path)
        video.audio_timeline_path = str(sync_result.timeline_path)
        video.exported_duration_seconds = export_result.duration_seconds
        video.exported_file_size_bytes = export_result.file_size_bytes
        video.is_export_outdated = False
        db.commit()

        report(100, "Dubbed video export completed successfully.")
        return DubbingPipelineResult(
            export_result=export_result,
            sync_result=sync_result,
            timing_conflicts=sync_result.conflicts,
        )
