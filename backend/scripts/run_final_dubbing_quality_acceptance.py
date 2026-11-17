import os
import sys
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.project import (
    Project, Video, TranscriptSegment, TranslationSegment, GeneratedAudio, ProjectStatus
)
from app.services.dubbing.pipeline import DubbingPipeline
from app.core.config import settings
DATA_DIR = Path(settings.DATA_DIR)

SOURCE_PROJECT_ID = "63f59d4d-b32f-410b-9f16-cd533e250316"
TEST_PROJECT_ID = "63f59d4d-b32f-410b-9f16-cd533e250999"

def main():
    print("=" * 70)
    print(" KhmerDub AI — End-to-End Real Project Dubbing Quality Acceptance")
    print("=" * 70)
    db = SessionLocal()

    # 1. Verify source project exists read-only
    src_proj = db.query(Project).filter(Project.id == SOURCE_PROJECT_ID).first()
    if not src_proj:
        print(f"[ERROR] Source project {SOURCE_PROJECT_ID} not found in database!")
        sys.exit(1)

    print(f"Verified Source Project: {src_proj.id}")
    print(f"Title: {src_proj.title}")
    print(f"Status: {src_proj.status}")
    print(f"Pipeline Version: {src_proj.pipeline_version}")
    print(f"Original Video: {src_proj.original_video_path}")

    # 2. Clean any prior test project copy
    old_test = db.query(Project).filter(Project.id == TEST_PROJECT_ID).first()
    if old_test:
        print(f"Removing prior test project {TEST_PROJECT_ID} records...")
        db.query(GeneratedAudio).filter(GeneratedAudio.project_id == TEST_PROJECT_ID).delete()
        db.query(TranslationSegment).filter(TranslationSegment.project_id == TEST_PROJECT_ID).delete()
        db.query(TranscriptSegment).filter(TranscriptSegment.project_id == TEST_PROJECT_ID).delete()
        db.query(Video).filter(Video.project_id == TEST_PROJECT_ID).delete()
        db.delete(old_test)
        db.commit()

    test_dir = DATA_DIR / "projects" / TEST_PROJECT_ID
    if test_dir.exists():
        shutil.rmtree(test_dir, ignore_errors=True)

    # 3. Create test project copy
    test_proj = Project(
        id=TEST_PROJECT_ID,
        title="[Disposable Test Quality Repair] " + (src_proj.title or "Test"),
        original_video_path=src_proj.original_video_path,
        original_language=src_proj.original_language,
        target_language=src_proj.target_language,
        status=src_proj.status,
        tts_provider=src_proj.tts_provider,
        tts_voice=src_proj.tts_voice,
        translation_provider=src_proj.translation_provider,
        translation_style=src_proj.translation_style,
        segmentation_mode=src_proj.segmentation_mode,
        raw_transcript_json=src_proj.raw_transcript_json,
        pipeline_version=src_proj.pipeline_version,
    )
    db.add(test_proj)

    src_video = src_proj.video
    if src_video:
        test_video = Video(
            id=f"vid_{TEST_PROJECT_ID[:8]}",
            project_id=TEST_PROJECT_ID,
            filename=src_video.filename,
            file_path=src_video.file_path,
            file_size_bytes=src_video.file_size_bytes,
            duration_seconds=src_video.duration_seconds,
            width=src_video.width,
            height=src_video.height,
            video_codec=src_video.video_codec,
            audio_codec=src_video.audio_codec,
            extracted_audio_path=src_video.extracted_audio_path,
        )
        db.add(test_video)

    # Copy transcript segments
    src_transcripts = db.query(TranscriptSegment).filter(TranscriptSegment.project_id == SOURCE_PROJECT_ID).all()
    trans_id_map = {}
    for st in src_transcripts:
        new_id = f"ts_{TEST_PROJECT_ID[:8]}_{st.segment_order:03d}"
        trans_id_map[st.id] = new_id
        tt = TranscriptSegment(
            id=new_id,
            project_id=TEST_PROJECT_ID,
            segment_order=st.segment_order,
            start_time=st.start_time,
            end_time=st.end_time,
            text=st.text,
            words_json=st.words_json,
            is_approximate=st.is_approximate,
            is_manually_edited=st.is_manually_edited,
            dubbing_unit_id=st.dubbing_unit_id,
        )
        db.add(tt)

    # Copy translation segments & audio files
    src_translations = db.query(TranslationSegment).filter(TranslationSegment.project_id == SOURCE_PROJECT_ID).all()
    test_audio_dir = DATA_DIR / "projects" / TEST_PROJECT_ID / "generated_audio"
    test_audio_dir.mkdir(parents=True, exist_ok=True)

    for tr in src_translations:
        new_tr_id = f"tr_{TEST_PROJECT_ID[:8]}_{tr.segment_order:03d}"
        new_ts_id = trans_id_map.get(tr.transcript_segment_id, tr.transcript_segment_id)
        test_tr = TranslationSegment(
            id=new_tr_id,
            project_id=TEST_PROJECT_ID,
            transcript_segment_id=new_ts_id,
            segment_order=tr.segment_order,
            khmer_text=tr.khmer_text,
            is_manually_edited=tr.is_manually_edited,
            is_outdated=tr.is_outdated,
            style=tr.style,
            explanation=tr.explanation,
            start_time=tr.start_time,
            end_time=tr.end_time,
            source_segment_ids=tr.source_segment_ids,
            source_text=tr.source_text,
        )
        db.add(test_tr)

        src_audio = tr.generated_audio
        if src_audio and src_audio.audio_path:
            src_audio_p = Path(src_audio.audio_path)
            dest_audio_p = test_audio_dir / f"segment_{new_tr_id}.mp3"
            if src_audio_p.exists():
                shutil.copy2(src_audio_p, dest_audio_p)
            test_ga = GeneratedAudio(
                id=f"ga_{TEST_PROJECT_ID[:8]}_{tr.segment_order:03d}",
                project_id=TEST_PROJECT_ID,
                translation_segment_id=new_tr_id,
                audio_path=str(dest_audio_p),
                duration_seconds=src_audio.duration_seconds,
                provider=src_audio.provider,
                voice=src_audio.voice,
                is_outdated=False,
            )
            db.add(test_ga)

    db.commit()
    print(f"Created isolated test project copy: {TEST_PROJECT_ID}")
    print(f"Copied {len(src_translations)} translations and audio files.")

    # 4. Run DubbingPipeline.run() on test project
    print("\nExecuting DubbingPipeline.run() on full 228-second test project...")
    pipeline = DubbingPipeline()
    result = pipeline.run(
        project_id=TEST_PROJECT_ID,
        db=db,
        strict_validation=True,
        max_tempo_factor=1.25,
        on_progress=lambda pct, msg: print(f"  [{pct:03d}%] {msg}"),
    )

    print("\n" + "=" * 70)
    print(" Pipeline Execution Completed Successfully!")
    print("=" * 70)
    print(f"Exported MP4: {result.export_result.video_path}")
    print(f"Reported Conflicts: {len(result.timing_conflicts)}")
    print(f"File Size: {result.export_result.file_size_bytes:,} bytes")
    print(f"Container Duration: {result.export_result.duration_seconds:.3f}s")

    # 5. FFprobe detailed verification of exported MP4
    mp4_p = result.export_result.video_path
    cmd = [
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(mp4_p)
    ]
    probe_res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    probe_data = json.loads(probe_res.stdout)

    v_stream = next(s for s in probe_data["streams"] if s["codec_type"] == "video")
    a_stream = next(s for s in probe_data["streams"] if s["codec_type"] == "audio")
    fmt = probe_data["format"]

    container_dur = float(fmt["duration"])
    v_dur = float(v_stream["duration"])
    a_dur = float(a_stream["duration"])
    ref_dur = float(src_video.duration_seconds)
    delta = abs(container_dur - ref_dur)

    print("\nStream Analysis:")
    print(f"  Reference Video Duration: {ref_dur:.3f}s")
    print(f"  Exported Container Dur:   {container_dur:.3f}s (delta: {delta*1000:.1f}ms)")
    print(f"  Video Stream Duration:    {v_dur:.3f}s (codec: {v_stream['codec_name']})")
    print(f"  Audio Stream Duration:    {a_dur:.3f}s (codec: {a_stream['codec_name']}, {a_stream['sample_rate']}Hz, {a_stream['channels']}ch)")

    # 6. Detailed check of segments 28, 29, 30, 31, 32
    print("\nDetailed Scheduled Piece Verification (Segments 28-32):")
    # Fetch pieces from synchronizer schedule
    from app.services.dubbing.scheduler import TimelineScheduler
    raw_items = []
    test_trans = db.query(TranslationSegment).filter(TranslationSegment.project_id == TEST_PROJECT_ID).order_by(TranslationSegment.segment_order.asc()).all()
    for tr in test_trans:
        ga = tr.generated_audio
        raw_items.append({
            "segment_order": tr.segment_order,
            "start_time": tr.start_time,
            "end_time": tr.end_time,
            "orig_duration": tr.end_time - tr.start_time,
            "raw_duration": ga.duration_seconds if ga else 0.0,
            "audio_path": ga.audio_path if ga else None,
        })
    sched = TimelineScheduler(max_tempo=1.25)
    groups = sched.schedule_timeline(raw_items, target_duration=ref_dur)

    seg_results = {}
    for g in groups:
        for p in g.pieces:
            if p.segment_order in [28, 29, 30, 31, 32]:
                seg_results[p.segment_order] = {
                    "order": p.segment_order,
                    "window": p.orig_duration,
                    "raw_dur": p.raw_duration,
                    "applied_tempo": p.applied_tempo,
                    "sched_start": p.scheduled_start,
                    "sched_end": p.scheduled_end,
                    "processed_dur": p.processed_duration,
                    "status": p.status,
                    "overflow": p.overflow_seconds,
                }
                print(f"  Segment #{p.segment_order:02d}: slot={p.orig_duration:.2f}s, raw={p.raw_duration:.2f}s, tempo={p.applied_tempo:.2f}x, sched={p.scheduled_start:.2f}-{p.scheduled_end:.2f}s ({p.processed_duration:.2f}s), status={p.status}, overflow={p.overflow_seconds:.2f}s")

    # Output results to JSON
    output_summary = {
        "source_project_id": SOURCE_PROJECT_ID,
        "test_project_id": TEST_PROJECT_ID,
        "video_duration": ref_dur,
        "container_duration": container_dur,
        "duration_delta_ms": round(delta * 1000, 1),
        "video_stream_duration": v_dur,
        "audio_stream_duration": a_dur,
        "total_conflicts": len(result.timing_conflicts),
        "segments_audit": seg_results,
        "exported_mp4": str(mp4_p),
    }

    out_json = DATA_DIR / "outputs" / "final_dubbing_quality_acceptance_results.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w") as f:
        json.dump(output_summary, f, indent=2)
    print(f"\nSaved Acceptance Results to: {out_json}")
    db.close()

if __name__ == "__main__":
    main()
