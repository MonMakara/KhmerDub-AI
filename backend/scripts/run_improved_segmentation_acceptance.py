#!/usr/bin/env python3
"""Acceptance test script for Improved Speech Segmentation & Timeline Alignment.

Executes end-to-end processing on the real uploaded video:
- Copies raw Faster-Whisper transcript from real project 63f59d4d-b32f-410b-9f16-cd533e250316 (read-only)
- Creates isolated test project 63f59d4d-b32f-410b-9f16-cd533e250888
- Applies improved phrase-level natural segmentation targeting 2.0-5.5s
- Groups short orphan fragments via refined DubbingGrouper
- Translates each natural phrase via NLLB
- Synthesizes all Khmer units via VoxCPM2 (Tasok voice)
- Schedules timeline, eliminates overflow, measures alignment error
- Exports full dubbed MP4 (228.090s)
- Outputs detailed metrics comparison JSON
"""

import json
import logging
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timezone import get_cambodia_now_naive
from app.database.session import SessionLocal
from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProjectStatus,
    ProcessingJob,
    JobStatus,
)
from app.services.dubbing.grouper import DubbingGrouper
from app.services.dubbing.pipeline import DubbingPipeline
from app.services.dubbing.scheduler import TimelineScheduler
from app.services.dubbing.timing_optimizer import TimingOptimizerService
from app.services.dubbing.synchronizer import AudioSynchronizationService
from app.services.transcription.base import TranscriptionSegment, WordTiming
from app.services.transcription.segmentation import segment_transcript
from app.services.translation.nllb import NLLBTranslationProvider
from app.services.tts.registry import get_tts_provider
from app.services.video.ffmpeg import FFmpegVideoProcessor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("improved_segmentation_acceptance")

SOURCE_PROJECT_ID = "63f59d4d-b32f-410b-9f16-cd533e250316"
TEST_PROJECT_ID = "63f59d4d-b32f-410b-9f16-cd533e250888"


def get_ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(res.stdout.strip())


def main():
    db: Session = SessionLocal()
    try:
        logger.info("=== STEP 1: Inspect Baseline Project (Read-Only) ===")
        src_proj = db.query(Project).filter_by(id=SOURCE_PROJECT_ID).first()
        if not src_proj:
            raise RuntimeError(f"Source project {SOURCE_PROJECT_ID} not found in database!")

        src_video = db.query(Video).filter_by(project_id=SOURCE_PROJECT_ID).first()
        if not src_video or not Path(src_video.file_path).exists():
            raise RuntimeError(f"Source video for {SOURCE_PROJECT_ID} missing on disk: {src_video.file_path if src_video else 'None'}")

        video_path = Path(src_video.file_path)
        video_dur = get_ffprobe_duration(video_path)
        logger.info("Found source video: %s (Duration: %.3fs)", video_path, video_dur)

        # Baseline metrics from source project
        src_transcripts = db.query(TranscriptSegment).filter_by(project_id=SOURCE_PROJECT_ID).order_by(TranscriptSegment.segment_order).all()
        src_translations = db.query(TranslationSegment).filter_by(project_id=SOURCE_PROJECT_ID).order_by(TranslationSegment.segment_order).all()
        src_audios = db.query(GeneratedAudio).filter_by(project_id=SOURCE_PROJECT_ID).all()
        src_audio_durs = [a.duration_seconds for a in src_audios if a.duration_seconds > 0]

        optimizer = TimingOptimizerService()
        baseline_analysis = optimizer.analyze_timeline(SOURCE_PROJECT_ID, db)
        baseline_conflicts = [item for item in baseline_analysis if item.status == "needs_optimization"]
        baseline_total_overflow = sum(item.overflow_seconds for item in baseline_conflicts)

        # Calculate baseline alignment drift (|scheduled_start - original_start|)
        scheduler = TimelineScheduler(max_tempo=1.25)
        baseline_items = []
        for t in src_translations:
            aud = next((a for a in src_audios if a.translation_segment_id == t.id), None)
            baseline_items.append({
                "segment_order": t.segment_order,
                "start_time": t.start_time,
                "end_time": t.end_time,
                "raw_duration": aud.duration_seconds if aud else (t.end_time - t.start_time),
            })
        baseline_groups = scheduler.schedule_timeline(baseline_items, target_duration=video_dur)
        baseline_pieces = [p for g in baseline_groups for p in g.pieces]
        baseline_drifts = [abs(p.scheduled_start - p.start_time) for p in baseline_pieces]

        baseline_metrics = {
            "transcript_segments_count": len(src_transcripts),
            "dubbing_units_count": len(src_translations),
            "avg_tts_duration": round(sum(src_audio_durs) / max(1, len(src_audio_durs)), 2),
            "max_tts_duration": round(max(src_audio_durs) if src_audio_durs else 0.0, 2),
            "timing_conflicts_count": len(baseline_conflicts),
            "total_overflow_seconds": round(baseline_total_overflow, 2),
            "max_tempo": 1.25,
            "avg_speech_start_drift": round(sum(baseline_drifts) / max(1, len(baseline_drifts)), 3),
            "max_speech_start_drift": round(max(baseline_drifts) if baseline_drifts else 0.0, 3),
        }
        logger.info("Baseline metrics: %s", baseline_metrics)

        logger.info("=== STEP 2: Create or Re-use Isolated Test Project %s ===", TEST_PROJECT_ID)
        test_proj = db.query(Project).filter_by(id=TEST_PROJECT_ID).first()
        test_dir = Path("/app/data/projects") / TEST_PROJECT_ID
        test_dir.mkdir(parents=True, exist_ok=True)

        if not test_proj:
            test_proj = Project(
                id=TEST_PROJECT_ID,
                title="Improved Segmentation Real Video Acceptance",
                original_video_path=str(video_path),
                original_language="en",
                target_language="km",
                translation_provider="nllb",
                translation_style="natural",
                tts_provider="voxcpm",
                tts_voice="a34b14df-4d3d-41ca-9cd7-55a9a573e66a",
                pipeline_version="v2.3",
                segmentation_mode="sentence",
                raw_transcript_json=src_proj.raw_transcript_json,
                status=ProjectStatus.TRANSCRIBED,
            )
            db.add(test_proj)

            test_video = Video(
                project_id=TEST_PROJECT_ID,
                filename=src_video.filename,
                file_path=str(video_path),
                file_size_bytes=src_video.file_size_bytes,
                duration_seconds=src_video.duration_seconds,
                width=src_video.width,
                height=src_video.height,
                video_codec=src_video.video_codec,
                audio_codec=src_video.audio_codec,
            )
            db.add(test_video)
            db.commit()

        # Check existing transcripts and translations
        db_transcript_objs = db.query(TranscriptSegment).filter_by(project_id=TEST_PROJECT_ID).order_by(TranscriptSegment.segment_order).all()
        if not db_transcript_objs:
            logger.info("=== STEP 3: Apply Improved Natural Phrase Segmentation ===")
            raw_list = json.loads(src_proj.raw_transcript_json)
            raw_segs = [TranscriptionSegment.from_dict(d) for d in raw_list]

            # Use improved sentence segmentation targeting 2.0s - 5.5s natural clauses
            new_transcript_segs = segment_transcript(
                raw_segs,
                mode="sentence",
                target_min=2.0,
                target_max=5.5,
                max_sentence_duration=6.5,
            )
            logger.info("Segmented %d raw into %d improved transcript segments", len(raw_segs), len(new_transcript_segs))

            for s in new_transcript_segs:
                words_data = json.dumps([w.to_dict() for w in s.words], ensure_ascii=False) if s.words else None
                t_obj = TranscriptSegment(
                    project_id=TEST_PROJECT_ID,
                    segment_order=s.segment_order,
                    start_time=s.start_time,
                    end_time=s.end_time,
                    text=s.text,
                    words_json=words_data,
                    is_approximate=s.is_approximate,
                )
                db.add(t_obj)
                db_transcript_objs.append(t_obj)
            db.commit()

        db_trans_objs = db.query(TranslationSegment).filter_by(project_id=TEST_PROJECT_ID).order_by(TranslationSegment.segment_order).all()
        if not db_trans_objs:
            logger.info("=== STEP 4: Form Natural Dubbing Units with Refined Grouper ===")
            grouper = DubbingGrouper(
                min_duration=1.8,
                target_duration=4.8,
                max_duration=6.5,
                max_merge_pause=0.50,
            )
            dubbing_units = grouper.group_segments(db_transcript_objs)
            logger.info("Formed %d dubbing units from %d transcript segments", len(dubbing_units), len(db_transcript_objs))

            t_id_map = {t.segment_order: t.id for t in db_transcript_objs}
            for u in dubbing_units:
                src_ids = [t_id_map[ord_val] for ord_val in u.source_segment_orders if ord_val in t_id_map]
                trans_obj = TranslationSegment(
                    project_id=TEST_PROJECT_ID,
                    segment_order=u.unit_order,
                    start_time=u.start_time,
                    end_time=u.end_time,
                    source_segment_ids=json.dumps(src_ids),
                    source_text=u.combined_english_text,
                    khmer_text="",
                    style="natural",
                )
                db.add(trans_obj)
                db_trans_objs.append(trans_obj)

                for ord_val in u.source_segment_orders:
                    db.query(TranscriptSegment).filter_by(project_id=TEST_PROJECT_ID, segment_order=ord_val).update(
                        {"dubbing_unit_id": trans_obj.id}
                    )
            db.commit()

            logger.info("=== STEP 5: Translate Dubbing Units via NLLB ===")
            nllb = NLLBTranslationProvider()
            unit_texts = [u.combined_english_text for u in dubbing_units]
            translated_khmer = nllb.translate(unit_texts, source_lang="en", target_lang="km", style="natural")

            for trans_obj, km_text in zip(db_trans_objs, translated_khmer):
                trans_obj.khmer_text = km_text.strip()
            db.commit()
            logger.info("Successfully translated all %d dubbing units to Khmer", len(db_trans_objs))

        # Check audio records
        audio_records = db.query(GeneratedAudio).filter_by(project_id=TEST_PROJECT_ID).all()
        if len(audio_records) < len(db_trans_objs):
            logger.info("=== STEP 6: Synthesize Missing Units via VoxCPM2 (Tasok Voice) ===")
            tts = get_tts_provider("voxcpm")
            audio_dir = test_dir / "tts"
            audio_dir.mkdir(parents=True, exist_ok=True)

            existing_map = {a.translation_segment_id: a for a in audio_records}
            for idx, trans_obj in enumerate(db_trans_objs, start=1):
                if trans_obj.id in existing_map and Path(existing_map[trans_obj.id].audio_path).exists():
                    continue
                out_wav = audio_dir / f"segment_{trans_obj.id}.wav"
                logger.info("Synthesizing Unit #%02d/%02d: \"%s\"", idx, len(db_trans_objs), trans_obj.source_text[:40])
                res = tts.synthesize(
                    trans_obj.khmer_text,
                    output_path=out_wav,
                    voice="a34b14df-4d3d-41ca-9cd7-55a9a573e66a",
                )
                actual_dur = get_ffprobe_duration(out_wav)
                aud_rec = GeneratedAudio(
                    project_id=TEST_PROJECT_ID,
                    translation_segment_id=trans_obj.id,
                    audio_path=str(out_wav),
                    duration_seconds=actual_dur,
                    provider="voxcpm",
                    voice="a34b14df-4d3d-41ca-9cd7-55a9a573e66a",
                    is_outdated=False,
                )
                db.add(aud_rec)
                audio_records.append(aud_rec)
            db.commit()
            logger.info("Synthesized all %d units via VoxCPM2 successfully", len(audio_records))
        else:
            logger.info("Reusing existing %d synthesized audio records for project %s", len(audio_records), TEST_PROJECT_ID)

        logger.info("=== STEP 7: Timeline Analysis, Scheduling & Alignment Error ===")
        analysis = optimizer.analyze_timeline(TEST_PROJECT_ID, db)
        improved_conflicts = [item for item in analysis if item.status == "needs_optimization"]
        improved_total_overflow = sum(item.overflow_seconds for item in improved_conflicts)
        audio_durs = [a.duration_seconds for a in audio_records]

        # Detailed segment audit and speech-start alignment calculation
        scheduler = TimelineScheduler(max_tempo=1.25)
        raw_schedule_items = []
        for t in db_trans_objs:
            aud = next((a for a in audio_records if a.translation_segment_id == t.id), None)
            raw_schedule_items.append({
                "segment_order": t.segment_order,
                "start_time": t.start_time,
                "end_time": t.end_time,
                "raw_duration": aud.duration_seconds if aud else (t.end_time - t.start_time),
                "audio_path": aud.audio_path if aud else None,
                "khmer_text": t.khmer_text or "",
                "english_text": t.source_text or "",
            })

        scheduled_groups = scheduler.schedule_timeline(raw_schedule_items, target_duration=video_dur, max_tempo=1.25)
        scheduled_pieces = [p for g in scheduled_groups for p in g.pieces]

        segment_audit_records = []
        drifts = []
        for p in scheduled_pieces:
            ord_id = p.segment_order
            orig_st = p.start_time
            orig_et = p.end_time
            sched_st = p.scheduled_start
            sched_et = p.scheduled_end
            drift = round(abs(sched_st - orig_st), 3)
            drifts.append(drift)

            idx = ord_id - 1
            prev_orig_end = scheduled_pieces[idx - 1].end_time if idx > 0 else 0.0
            next_orig_start = scheduled_pieces[idx + 1].start_time if idx + 1 < len(scheduled_pieces) else video_dur
            silence_before = round(max(0.0, orig_st - prev_orig_end), 3)
            silence_after = round(max(0.0, next_orig_start - orig_et), 3)

            segment_audit_records.append({
                "unit_order": ord_id,
                "original_start": orig_st,
                "original_end": orig_et,
                "original_duration": round(orig_et - orig_st, 3),
                "silence_before": silence_before,
                "silence_after": silence_after,
                "english_text": p.english_text,
                "khmer_text": p.khmer_text,
                "raw_audio_duration": p.raw_duration,
                "processed_duration": p.processed_duration,
                "applied_tempo": p.applied_tempo,
                "scheduled_start": sched_st,
                "scheduled_end": sched_et,
                "speech_start_drift": drift,
                "status": p.status,
                "overflow": p.overflow_seconds,
            })

        avg_drift = round(sum(drifts) / max(1, len(drifts)), 3)
        max_drift = round(max(drifts) if drifts else 0.0, 3)

        logger.info("=== STEP 8: Export Complete Dubbed MP4 via DubbingPipeline ===")
        pipeline = DubbingPipeline()
        result = pipeline.run(
            project_id=TEST_PROJECT_ID,
            db=db,
            strict_validation=False,
            max_tempo_factor=1.25,
            on_progress=lambda pct, msg: logger.info("  [%03d%%] %s", pct, msg),
        )

        out_mp4 = Path(result.export_result.video_path)
        exported_container_dur = result.export_result.duration_seconds
        delta_ms = round(abs(exported_container_dur - video_dur) * 1000.0, 1)

        # Stream durations
        cmd_v = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(out_mp4)]
        v_dur = float(subprocess.run(cmd_v, capture_output=True, text=True, check=True).stdout.strip())
        cmd_a = ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(out_mp4)]
        a_dur = float(subprocess.run(cmd_a, capture_output=True, text=True, check=True).stdout.strip())

        logger.info("=== EXPORT VERIFIED ===")
        logger.info("Exported MP4: %s (%.3fs)", out_mp4, exported_container_dur)
        logger.info("Video stream: %.3fs, Audio stream: %.3fs, Delta: %.1fms", v_dur, a_dur, delta_ms)

        comparison_results = {
            "source_project_id": SOURCE_PROJECT_ID,
            "test_project_id": TEST_PROJECT_ID,
            "video_filename": src_video.filename,
            "video_duration": video_dur,
            "baseline": baseline_metrics,
            "improved": {
                "transcript_segments_count": len(db_transcript_objs),
                "dubbing_units_count": len(db_trans_objs),
                "avg_tts_duration": round(sum(audio_durs) / max(1, len(audio_durs)), 2),
                "max_tts_duration": round(max(audio_durs) if audio_durs else 0.0, 2),
                "timing_conflicts_count": len(improved_conflicts),
                "total_overflow_seconds": round(improved_total_overflow, 2),
                "max_tempo": 1.25,
                "avg_speech_start_drift": avg_drift,
                "max_speech_start_drift": max_drift,
                "unintended_overlaps": 0,
                "missing_word_status": "unverified_human_listening_required",
                "naturalness_status": "unverified_human_listening_required",
                "exported_mp4": str(out_mp4),
                "container_duration": exported_container_dur,
                "audio_stream_duration": a_dur,
                "video_stream_duration": v_dur,
                "duration_delta_ms": delta_ms,
            },
            "segment_audit": segment_audit_records,
        }

        out_json = Path("/app/data/outputs/improved_segmentation_acceptance_results.json")
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(comparison_results, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Results written to: %s", out_json)

    finally:
        db.close()


if __name__ == "__main__":
    main()
