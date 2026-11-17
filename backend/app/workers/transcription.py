import json
import logging
from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.core.config import settings
from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProcessingJob,
    ProjectStatus,
    JobStatus,
)
from app.services.transcription.whisper import FasterWhisperTranscriptionProvider
from app.services.transcription.segmentation import segment_transcript, validate_word_coverage
from app.services.transcription.base import project_segment_id
from app.services.transcription.exceptions import TranscriptionError

from app.services.tts.selection import preserve_partition

logger = logging.getLogger(__name__)


def process_transcription(project_id: str, job_id: str, db: Optional[Session] = None) -> None:
    """Synchronous worker function designed to run in background tasks for STT transcription."""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        project = db.query(Project).filter(Project.id == project_id).first()
        video = db.query(Video).filter(Video.project_id == project_id).first()

        if not job or not project or not video:
            logger.error("Job, project, or video record missing: project_id=%s, job_id=%s", project_id, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = "Project or video record missing"
                db.commit()
            return

        if not video.extracted_audio_path or not Path(video.extracted_audio_path).exists():
            error_msg = "Extracted audio file does not exist. Please extract audio first."
            logger.error(error_msg)
            job.status = JobStatus.FAILED
            job.error_message = error_msg
            project.status = ProjectStatus.FAILED
            db.commit()
            return

        job.status = JobStatus.RUNNING
        job.progress_percentage = 20
        project.status = ProjectStatus.TRANSCRIBING
        db.commit()

        audio_path = Path(video.extracted_audio_path)
        provider = FasterWhisperTranscriptionProvider()
        raw_segments = provider.transcribe(audio_path, language=project.original_language or "en", word_timestamps=True)

        job.progress_percentage = 80
        db.commit()

        preserve_partition(raw_segments, project.translation_segments)

        # Persist raw transcription segments and word timings
        raw_dict_list = [s.to_dict() for s in raw_segments]
        raw_json_str = json.dumps(raw_dict_list, ensure_ascii=False)
        project.raw_transcript_json = raw_json_str

        # Also save to data/projects/{project_id}/asr_raw.json for persistent reference
        try:
            asr_dir = Path(settings.PROJECTS_DATA_DIR if hasattr(settings, "PROJECTS_DATA_DIR") else "/app/data/projects") / project_id
            asr_dir.mkdir(parents=True, exist_ok=True)
            (asr_dir / "asr_raw.json").write_text(raw_json_str, encoding="utf-8")
        except Exception as e:
            logger.warning("Could not write asr_raw.json to disk: %s", e)

        # Apply segmentation mode (default to "sentence" for natural phrasing)
        segment_mode = project.segmentation_mode or "sentence"
        final_segments = segment_transcript(raw_segments, mode=segment_mode)
        validate_word_coverage(raw_segments, final_segments)

        # Check if downstream entities exist; if so, mark them outdated upon re-transcription
        existing_translations = db.query(TranslationSegment).filter(TranslationSegment.project_id == project_id).count()
        if existing_translations > 0:
            db.query(TranslationSegment).filter(TranslationSegment.project_id == project_id).update(
                {TranslationSegment.is_outdated: True}
            )
            db.query(GeneratedAudio).filter(GeneratedAudio.project_id == project_id).update(
                {GeneratedAudio.is_outdated: True}
            )
            if project.video and project.video.exported_video_path:
                project.video.is_export_outdated = True

        # Safely replace any existing transcript segments
        db.query(TranscriptSegment).filter(TranscriptSegment.project_id == project_id).delete()

        # Insert new segmented records
        for seg in final_segments:
            words_data = json.dumps([w.to_dict() for w in seg.words], ensure_ascii=False) if seg.words else None
            db_segment = TranscriptSegment(
                id=project_segment_id(project_id, seg.id),
                project_id=project_id,
                segment_order=seg.segment_order,
                start_time=seg.start_time,
                end_time=seg.end_time,
                text=seg.text,
                words_json=words_data,
                is_approximate=seg.is_approximate,
                is_manually_edited=seg.is_manually_edited,
            )
            db.add(db_segment)

        project.status = ProjectStatus.TRANSCRIBED
        job.status = JobStatus.COMPLETED
        job.progress_percentage = 100
        job.error_message = None
        db.commit()

        logger.info(
            "Successfully completed transcription for project %s: mode=%s, saved %d segments from %d raw",
            project_id,
            segment_mode,
            len(final_segments),
            len(raw_segments),
        )

    except TranscriptionError as e:
        logger.error("Transcription error for project %s: %s", project_id, e)
        if job:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
        if project:
            project.status = ProjectStatus.FAILED
        db.commit()

    except Exception as e:
        logger.exception("Unexpected error during transcription for project %s: %s", project_id, e)
        if job:
            job.status = JobStatus.FAILED
            job.error_message = f"Unexpected transcription failure: {e}"
        if project:
            project.status = ProjectStatus.FAILED
        db.commit()

    finally:
        if should_close:
            db.close()
