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
from app.services.translation.timing import speaking_budget

from app.services.tts.selection import (
    voice_aware_groups, source_keys, preserve_partition, assignment_map, partition_voice,
)

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
            saved_voice_units = db.query(TranslationSegment).filter_by(project_id=project_id).all()
            dubbing_units = voice_aware_groups(transcript_segments, saved_voice_units)
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

            if any(t.voice_override_id for t in existing_translations):
                by_sources = {tuple(json.loads(t.source_segment_ids or "[]")): t for t in existing_translations}
                existing_map = {u.unit_order: by_sources[tuple(u.source_segment_ids)]
                                for u in dubbing_units if tuple(u.source_segment_ids) in by_sources}

            # A new transcript partition must never silently retarget approved Khmer.
            for existing in existing_translations:
                if not existing.is_manually_edited:
                    continue
                source_ids = json.loads(existing.source_segment_ids or "[]")
                exact = next((unit for unit in dubbing_units
                              if unit.source_segment_ids == source_ids
                              or (existing.transcript_segment_id is not None
                                  and existing.transcript_segment_id == unit.source_segment_ids[0])), None)
                if existing.is_outdated and exact is None:
                    raise TranslationError(
                        "Approved Khmer translations reference a previous transcript partition. "
                        "Please review their source mapping before translating again."
                    )

            units_to_translate = []
            contexts_to_translate = []
            durations_to_translate = []
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

                if u_idx < len(dubbing_units) - 1:
                    next_u_start = dubbing_units[u_idx + 1].start_time
                    avail_dur = speaking_budget(u.start_time, u.end_time, next_u_start)
                else:
                    avail_dur = speaking_budget(u.start_time, u.end_time)
                durations_to_translate.append(avail_dur)

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
                    contexts=contexts_to_translate,
                    durations=durations_to_translate,
                )
                job.progress_percentage = 85
                db.commit()

            # Save dubbing units into translation_segments table
            t_seg_dict = {t.id: t for t in transcript_segments}
            current_unit_orders = set()
            retained_ids = set()
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
                        khmer_changed = (existing.khmer_text != trans_str)
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
                        if existing.generated_audio:
                            # Invalidate attached audio whenever translation text changes or was previously outdated
                            if khmer_changed or existing.generated_audio.is_outdated:
                                existing.generated_audio.is_outdated = True
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

                saved_unit = db.query(TranslationSegment).filter_by(id=trans_unit_id).one()
                pair = u.voice_override
                saved_unit.voice_override_provider = pair[0] if pair else None
                saved_unit.voice_override_id = pair[1] if pair else None
                saved_unit.voice_source_keys = json.dumps(sorted(source_keys(
                    [t_seg_dict[i] for i in u.source_segment_ids]
                ))) if pair else None

                # Propagate speaker label from primary or source transcript segments
                assigned_spk = None
                if primary_t_id and primary_t_id in t_seg_dict:
                    assigned_spk = t_seg_dict[primary_t_id].speaker_label
                elif u.source_segment_ids:
                    for sid in u.source_segment_ids:
                        if sid in t_seg_dict and t_seg_dict[sid].speaker_label:
                            assigned_spk = t_seg_dict[sid].speaker_label
                            break
                if assigned_spk:
                    saved_unit.speaker_label = assigned_spk
                    if not saved_unit.voice_override_id:
                        from app.models.project import ProjectSpeaker
                        spk_model = db.query(ProjectSpeaker).filter(
                            ProjectSpeaker.project_id == project_id,
                            ProjectSpeaker.speaker_label == assigned_spk,
                        ).first()
                        if spk_model and spk_model.assigned_voice_provider and spk_model.assigned_voice_id:
                            saved_unit.voice_override_provider = spk_model.assigned_voice_provider
                            saved_unit.voice_override_id = spk_model.assigned_voice_id

                retained_ids.add(trans_unit_id)

                # Link member transcript segments to this dubbing unit
                for src_id in u.source_segment_ids:
                    t_member = t_seg_dict.get(src_id)
                    if t_member:
                        t_member.dubbing_unit_id = trans_unit_id

            # Clean up leftover translation segments if segment count reduced
            for old_t in existing_translations:
                if old_t.id not in retained_ids:
                    if old_t.is_manually_edited:
                        old_t.is_outdated = True
                    else:
                        if old_t.generated_audio:
                            db.delete(old_t.generated_audio)
                        db.delete(old_t)

            if project.video and project.video.exported_video_path:
                project.video.is_export_outdated = True

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

        preserve_partition(transcript_segments, existing_translations)
        saved_assignments = assignment_map(existing_translations)

        # Identify which segments need translation vs preserved manual edits
        segments_to_translate = []
        contexts_to_translate = []
        durations_to_translate = []
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

            if idx < len(transcript_segments) - 1:
                next_t_start = transcript_segments[idx + 1].start_time
                avail_dur = speaking_budget(t_seg.start_time, t_seg.end_time, next_t_start)
            else:
                avail_dur = speaking_budget(t_seg.start_time, t_seg.end_time)
            durations_to_translate.append(avail_dur)

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
                contexts=contexts_to_translate,
                durations=durations_to_translate,
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
            saved_unit = existing or new_trans
            pair = partition_voice(source_keys([t_seg]), saved_assignments)
            saved_unit.voice_override_provider = pair[0] if pair else None
            saved_unit.voice_override_id = pair[1] if pair else None
            saved_unit.voice_source_keys = json.dumps(sorted(source_keys([t_seg]))) if pair else None

            if t_seg.speaker_label:
                saved_unit.speaker_label = t_seg.speaker_label
                if not saved_unit.voice_override_id:
                    from app.models.project import ProjectSpeaker
                    spk_model = db.query(ProjectSpeaker).filter(
                        ProjectSpeaker.project_id == project_id,
                        ProjectSpeaker.speaker_label == t_seg.speaker_label,
                    ).first()
                    if spk_model and spk_model.assigned_voice_provider and spk_model.assigned_voice_id:
                        saved_unit.voice_override_provider = spk_model.assigned_voice_provider
                        saved_unit.voice_override_id = spk_model.assigned_voice_id

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
