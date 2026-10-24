import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import get_audio_segment_path
from app.database.session import SessionLocal
from app.models.project import (
    Project,
    TranslationSegment,
    GeneratedAudio,
    ProcessingJob,
    ProjectStatus,
    JobStatus,
)
from app.services.tts.google import GoogleTTSProvider
from app.services.tts.exceptions import TTSError

logger = logging.getLogger(__name__)


def synthesize_segment_audio(
    project_id: str,
    segment: TranslationSegment,
    provider: GoogleTTSProvider,
    db: Session,
) -> GeneratedAudio:
    """Helper to synthesize audio for a single translation segment and update the database."""
    output_path = get_audio_segment_path(project_id, segment.id)
    result = provider.synthesize(
        text=segment.khmer_text,
        output_path=output_path,
        language="km",
        voice="default",
    )

    audio_record = (
        db.query(GeneratedAudio)
        .filter(GeneratedAudio.translation_segment_id == segment.id)
        .first()
    )

    if audio_record:
        audio_record.audio_path = str(result.audio_path)
        audio_record.duration_seconds = result.duration_seconds
        audio_record.provider = result.provider_name
        audio_record.voice = result.voice
        audio_record.is_outdated = False
        audio_record.updated_at = datetime.utcnow()
    else:
        audio_record = GeneratedAudio(
            project_id=project_id,
            translation_segment_id=segment.id,
            audio_path=str(result.audio_path),
            duration_seconds=result.duration_seconds,
            provider=result.provider_name,
            voice=result.voice,
            is_outdated=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(audio_record)

    db.commit()
    db.refresh(audio_record)
    return audio_record


def process_tts(project_id: str, job_id: str, db: Optional[Session] = None) -> None:
    """Synchronous worker function to run in background tasks for Khmer speech synthesis."""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        project = db.query(Project).filter(Project.id == project_id).first()

        if not job or not project:
            logger.error("Job or project record missing: project_id=%s, job_id=%s", project_id, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = "Project or job record missing"
                db.commit()
            return

        translation_segments = (
            db.query(TranslationSegment)
            .filter(TranslationSegment.project_id == project_id)
            .order_by(TranslationSegment.segment_order.asc())
            .all()
        )

        if not translation_segments:
            error_msg = "No translated Khmer segments found to synthesize. Please translate first."
            logger.error(error_msg)
            job.status = JobStatus.FAILED
            job.error_message = error_msg
            project.status = ProjectStatus.FAILED
            db.commit()
            return

        job.status = JobStatus.RUNNING
        job.progress_percentage = 10
        project.status = ProjectStatus.GENERATING_VOICE
        db.commit()

        provider = GoogleTTSProvider()
        total_segments = len(translation_segments)
        logger.info(
            "Starting TTS synthesis for project %s (%d segments)...",
            project_id,
            total_segments,
        )

        for idx, seg in enumerate(translation_segments):
            if not seg.khmer_text or not seg.khmer_text.strip():
                logger.warning(
                    "Skipping segment order %d with empty Khmer text",
                    seg.segment_order,
                )
                continue

            try:
                synthesize_segment_audio(project_id, seg, provider, db)
            except Exception as e:
                logger.error(
                    "Failed to synthesize segment %s (order %d): %s",
                    seg.id,
                    seg.segment_order,
                    e,
                )
                raise TTSError(f"Error synthesizing segment {seg.segment_order}: {e}") from e

            # Update progress
            progress = 10 + int(85 * ((idx + 1) / total_segments))
            job.progress_percentage = min(progress, 95)
            db.commit()

        job.progress_percentage = 100
        job.status = JobStatus.COMPLETED
        project.status = ProjectStatus.VOICE_GENERATED
        db.commit()
        logger.info("Successfully completed TTS speech synthesis for project %s", project_id)

    except Exception as e:
        logger.exception("Unexpected error in process_tts: %s", e)
        if db:
            db.rollback()
            job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
            project = db.query(Project).filter(Project.id == project_id).first()
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(e)
            if project:
                project.status = ProjectStatus.FAILED
            db.commit()
    finally:
        if should_close:
            db.close()
