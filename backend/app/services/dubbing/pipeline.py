import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Tuple, Callable

from sqlalchemy.orm import Session

from app.core.storage import get_timeline_audio_path, get_exported_video_path
from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
)
from app.services.dubbing.synchronizer import (
    AudioSynchronizationService,
    SynchronizationResult,
    TimingConflict,
    TimingConflictError,
)
from app.services.dubbing.exporter import VideoExportService, ExportResult
from app.services.video.exceptions import VideoProcessingError

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
        for trans_seg in translation_segments:
            t_seg = trans_seg.transcript_segment
            if not t_seg:
                t_seg = (
                    db.query(TranscriptSegment)
                    .filter(TranscriptSegment.id == trans_seg.transcript_segment_id)
                    .first()
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

            if audio_rec.is_outdated:
                raise ValueError(
                    f"Speech audio for segment #{trans_seg.segment_order} is outdated "
                    f"because translation text was modified. Please regenerate speech audio."
                )

            segment_items.append((t_seg, trans_seg, audio_rec))

        report(30, "Aligning speech segments and calculating timing adjustments...")
        timeline_path = get_timeline_audio_path(project_id)

        report(50, "Synthesizing Khmer audio timeline WAV with silence padding...")
        sync_result = self.synchronizer.synchronize(
            project_id=project_id,
            segment_items=segment_items,
            target_duration=video_dur,
            output_timeline_path=timeline_path,
            strict_validation=strict_validation,
        )

        report(75, "Remuxing video with synchronized Khmer audio timeline...")
        output_video_path = get_exported_video_path(project_id)
        export_result = self.exporter.export(
            video_path=video_path,
            audio_timeline_path=sync_result.timeline_path,
            output_video_path=output_video_path,
            expected_duration=video_dur,
        )

        report(95, "Verifying exported video integrity...")
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
