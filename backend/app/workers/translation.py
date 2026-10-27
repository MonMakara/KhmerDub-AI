import logging
from typing import Optional, Dict
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.models.project import (
    Project,
    TranscriptSegment,
    TranslationSegment,
    ProcessingJob,
    ProjectStatus,
    JobStatus,
)
from app.services.translation.nllb import NLLBTranslationProvider
from app.services.translation.registry import get_translation_provider
from app.services.translation.exceptions import TranslationError

logger = logging.getLogger(__name__)


def process_translation(project_id: str, job_id: str, db: Optional[Session] = None) -> None:
    """Synchronous worker function to run in background tasks for English-to-Khmer translation."""
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

        # Fetch English transcript segments
        transcript_segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.project_id == project_id)
            .order_by(TranscriptSegment.segment_order.asc())
            .all()
        )

        if not transcript_segments:
            error_msg = "No English transcript segments found to translate. Please transcribe audio first."
            logger.error(error_msg)
            job.status = JobStatus.FAILED
            job.error_message = error_msg
            project.status = ProjectStatus.FAILED
            db.commit()
            return

        job.status = JobStatus.RUNNING
        job.progress_percentage = 15
        project.status = ProjectStatus.TRANSLATING
        db.commit()

        pipeline_ver = getattr(project, "pipeline_version", "v1") or "v1"
        is_grouped_dubbing = (pipeline_ver in ("v2.3", "v3", "v3.0"))

        if is_grouped_dubbing:
            # --- V2.3: Separate Transcript Segments from Dubbing Generation Units ---
            import json
            from app.services.dubbing.grouper import DubbingGrouper

            grouper = DubbingGrouper()
            dubbing_units = grouper.group_segments(transcript_segments)
            logger.info(
                "Grouped %d English transcript segments into %d dubbing units for project %s (pipeline=%s)",
                len(transcript_segments),
                len(dubbing_units),
                project_id,
                pipeline_ver,
            )

            # Query existing translation segments
            existing_translations = (
                db.query(TranslationSegment)
                .filter(TranslationSegment.project_id == project_id)
                .all()
            )
            existing_map: Dict[int, TranslationSegment] = {
                t.segment_order: t for t in existing_translations
            }

            units_to_translate = []
            contexts_to_translate = []
            units_order_map = []

            for u_idx, u in enumerate(dubbing_units):
                existing = existing_map.get(u.unit_order)
                if existing and existing.is_manually_edited:
                    logger.info(
                        "Preserving manually edited Khmer dubbing unit %d for project %s",
                        u.unit_order,
                        project_id,
                    )
                    continue

                units_to_translate.append(u.combined_english_text)
                units_order_map.append(u.unit_order)

                prev_text = dubbing_units[u_idx - 1].combined_english_text if u_idx > 0 else ""
                next_text = dubbing_units[u_idx + 1].combined_english_text if u_idx + 1 < len(dubbing_units) else ""
                context_str = f"{prev_text} {u.combined_english_text} {next_text}".strip()
                contexts_to_translate.append(context_str)

            translated_texts = []
            provider_name = getattr(project, "translation_provider", "nllb") or "nllb"
            style = getattr(project, "translation_style", "natural") or "natural"

            if units_to_translate:
                job.progress_percentage = 30
                db.commit()

                if provider_name == "nllb":
                    provider = NLLBTranslationProvider()
                else:
                    provider = get_translation_provider(provider_name)
                job.progress_percentage = 50
                db.commit()

                translated_texts = provider.translate(
                    texts=units_to_translate,
                    source_lang=project.original_language or "en",
                    target_lang=project.target_language or "km",
                    style=style,
                )
                job.progress_percentage = 85
                db.commit()

            # Save dubbing units into translation_segments table
            t_seg_dict = {t.id: t for t in transcript_segments}
            current_unit_orders = set()
            trans_idx = 0

            for u_idx, u in enumerate(dubbing_units):
                current_unit_orders.add(u.unit_order)
                existing = existing_map.get(u.unit_order)
                primary_t_id = u.source_segment_ids[0] if u.source_segment_ids else None
                src_ids_json = json.dumps(u.source_segment_ids)

                if existing and existing.is_manually_edited:
                    existing.start_time = u.start_time
                    existing.end_time = u.end_time
                    existing.source_segment_ids = src_ids_json
                    existing.source_text = u.combined_english_text
                    trans_unit_id = existing.id
                else:
                    trans_str = translated_texts[trans_idx] if trans_idx < len(translated_texts) else ""
                    trans_idx += 1

                    if existing:
                        existing.khmer_text = trans_str
                        existing.start_time = u.start_time
                        existing.end_time = u.end_time
                        existing.source_segment_ids = src_ids_json
                        existing.source_text = u.combined_english_text
                        existing.transcript_segment_id = primary_t_id
                        existing.style = style
                        existing.is_outdated = False
                        existing.is_manually_edited = False
                        trans_unit_id = existing.id
                    else:
                        new_trans = TranslationSegment(
                            project_id=project_id,
                            transcript_segment_id=primary_t_id,
                            segment_order=u.unit_order,
                            start_time=u.start_time,
                            end_time=u.end_time,
                            source_segment_ids=src_ids_json,
                            source_text=u.combined_english_text,
                            khmer_text=trans_str,
                            style=style,
                            is_manually_edited=False,
                            is_outdated=False,
                        )
                        db.add(new_trans)
                        db.flush()
                        trans_unit_id = new_trans.id

                # Link member transcript segments to this dubbing unit
                for src_id in u.source_segment_ids:
                    t_member = t_seg_dict.get(src_id)
                    if t_member:
                        t_member.dubbing_unit_id = trans_unit_id

            # Clean up leftover translation segments if segment count reduced
            for old_t in existing_translations:
                if old_t.segment_order not in current_unit_orders:
                    db.delete(old_t)

            project.status = ProjectStatus.TRANSLATED
            job.status = JobStatus.COMPLETED
            job.progress_percentage = 100
            job.error_message = None
            db.commit()

            logger.info(
                "Successfully completed dubbing-unit translation for project %s: %d units created from %d transcript segments",
                project_id,
                len(dubbing_units),
                len(transcript_segments),
            )
            return

        # Query existing translation segments
        existing_translations = (
            db.query(TranslationSegment)
            .filter(TranslationSegment.project_id == project_id)
            .all()
        )
        existing_map: Dict[str, TranslationSegment] = {
            t.transcript_segment_id: t for t in existing_translations if t.transcript_segment_id
        }

        # Identify which segments need translation vs preserved manual edits
        segments_to_translate = []
        contexts_to_translate = []
        indices_to_translate = []

        for idx, t_seg in enumerate(transcript_segments):
            existing = existing_map.get(t_seg.id)
            if existing and existing.is_manually_edited:
                # Preserve manually edited text, do not overwrite without explicit request
                logger.info(
                    "Preserving manually edited Khmer segment %d for project %s",
                    t_seg.segment_order,
                    project_id,
                )
                continue

            segments_to_translate.append(t_seg.text)
            indices_to_translate.append(idx)

            # Build lightweight context window from adjacent segments
            prev_text = transcript_segments[idx - 1].text if idx > 0 else ""
            next_text = transcript_segments[idx + 1].text if idx + 1 < len(transcript_segments) else ""
            context_str = f"{prev_text} {t_seg.text} {next_text}".strip()
            contexts_to_translate.append(context_str)

        translated_texts = []
        provider_name = getattr(project, "translation_provider", "nllb") or "nllb"
        style = getattr(project, "translation_style", "natural") or "natural"

        if segments_to_translate:
            job.progress_percentage = 30
            db.commit()

            if provider_name == "nllb":
                provider = NLLBTranslationProvider()
            else:
                provider = get_translation_provider(provider_name)
            job.progress_percentage = 50
            db.commit()

            translated_texts = provider.translate(
                texts=segments_to_translate,
                source_lang=project.original_language or "en",
                target_lang=project.target_language or "km",
                style=style,
            )
            job.progress_percentage = 85
            db.commit()

        # Persist translations into database
        trans_idx = 0
        for idx, t_seg in enumerate(transcript_segments):
            existing = existing_map.get(t_seg.id)
            if existing and existing.is_manually_edited:
                # If manually edited, preserve text. But if English was untouched, ensure segment_order matches
                existing.segment_order = t_seg.segment_order
                continue

            translated_str = translated_texts[trans_idx] if trans_idx < len(translated_texts) else ""
            trans_idx += 1

            if existing:
                existing.khmer_text = translated_str
                existing.segment_order = t_seg.segment_order
                existing.style = style
                existing.is_outdated = False
                existing.is_manually_edited = False
            else:
                new_trans = TranslationSegment(
                    project_id=project_id,
                    transcript_segment_id=t_seg.id,
                    segment_order=t_seg.segment_order,
                    khmer_text=translated_str,
                    style=style,
                    is_manually_edited=False,
                    is_outdated=False,
                )
                db.add(new_trans)

        project.status = ProjectStatus.TRANSLATED
        job.status = JobStatus.COMPLETED
        job.progress_percentage = 100
        job.error_message = None
        db.commit()

        logger.info(
            "Successfully completed translation for project %s: processed %d segments",
            project_id,
            len(transcript_segments),
        )

    except TranslationError as e:
        logger.error("Translation error for project %s: %s", project_id, e)
        if job:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
        if project:
            project.status = ProjectStatus.FAILED
        db.commit()

    except Exception as e:
        logger.exception("Unexpected error during translation for project %s: %s", project_id, e)
        if job:
            job.status = JobStatus.FAILED
            job.error_message = f"Unexpected translation failure: {e}"
        if project:
            project.status = ProjectStatus.FAILED
        db.commit()

    finally:
        if should_close:
            db.close()
