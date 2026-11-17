import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Add app paths
sys.path.insert(0, "/app")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.session import SessionLocal
from app.models.project import Project, TranslationSegment, GeneratedAudio
from app.services.dubbing.scheduler import TimelineScheduler
from app.services.dubbing.speech_guard import SpeechGuardService
from app.core.storage import resolve_audio_file


def measure_silences(audio_path: Path, noise_db: float = -40.0, min_dur: float = 0.08):
    cmd_probe = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    try:
        total_dur = float(subprocess.check_output(cmd_probe).strip())
    except Exception:
        total_dur = 0.0

    if total_dur <= 0.05:
        return total_dur, 0.0, 0.0, 0.0, 0.0, []

    cmd = [
        "ffmpeg", "-i", str(audio_path),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}",
        "-f", "null", "-",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)

    silences = []
    current_start = None
    for line in res.stderr.splitlines():
        if "silence_start:" in line:
            m = re.search(r"silence_start:\s*([0-9.]+)", line)
            if m:
                current_start = float(m.group(1))
        elif "silence_end:" in line:
            m = re.search(r"silence_end:\s*([0-9.]+)", line)
            if m and current_start is not None:
                silences.append((current_start, float(m.group(1))))
                current_start = None
    if current_start is not None:
        silences.append((current_start, total_dur))

    # Calculate leading, trailing, and internal silences
    lead_silence = 0.0
    trail_silence = 0.0
    internal_silences = []

    if silences:
        # Check if first silence is at start
        if silences[0][0] <= 0.05:
            lead_silence = silences[0][1]
            check_silences = silences[1:]
        else:
            check_silences = silences[:]

        # Check if last silence is at end
        if check_silences and check_silences[-1][1] >= (total_dur - 0.05):
            trail_silence = total_dur - check_silences[-1][0]
            check_silences = check_silences[:-1]

        internal_silences = check_silences

    internal_silence_dur = sum(end - start for start, end in internal_silences)
    active_dur = max(0.0, total_dur - lead_silence - trail_silence - internal_silence_dur)

    return total_dur, lead_silence, trail_silence, internal_silence_dur, active_dur, internal_silences


def analyze_speaking_speed(project_id: str = "bf2d3186-5b6d-4d3a-a6d7-b74aabcde102"):
    db = SessionLocal()
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        print(f"Error: Project {project_id} not found.")
        return

    video = proj.video
    target_dur = float(video.duration_seconds or 0.0) if video else 228.090

    trans_segs = (
        db.query(TranslationSegment)
        .filter(TranslationSegment.project_id == project_id)
        .order_by(TranslationSegment.segment_order.asc())
        .all()
    )

    scheduler_items = []
    seg_records = []
    for s in trans_segs:
        aud = s.generated_audio
        aud_p = resolve_audio_file(project_id, s.id, aud.audio_path) if aud else None
        scheduler_items.append({
            "idx": s.segment_order - 1,
            "segment_order": s.segment_order,
            "segment_id": s.id,
            "audio_path": aud_p,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "orig_duration": s.end_time - s.start_time,
            "raw_duration": aud.duration_seconds if aud else 0.0,
            "khmer_text": s.khmer_text or "",
            "english_text": s.source_text or "",
            "is_outdated": False,
            "is_missing": False,
        })
        seg_records.append((s, aud, aud_p))

    scheduler = TimelineScheduler(max_tempo=1.25)
    scheduled_groups = scheduler.schedule_timeline(scheduler_items, target_duration=target_dur)

    scheduled_pieces = {}
    for g in scheduled_groups:
        for p in g.pieces:
            scheduled_pieces[p.segment_order] = p

    results = []
    total_raw_dur = 0.0
    total_internal_silence = 0.0
    total_lead_silence = 0.0
    total_trail_silence = 0.0
    total_active_dur = 0.0
    total_overflow = 0.0

    print("=" * 110)
    print(f"INVESTIGATION: RAW TTS SPEAKING SPEED & DELIVERY FOR PROJECT: {proj.title}")
    print(f"Project ID: {project_id} | Video Duration: {target_dur:.3f}s | Units: {len(trans_segs)}")
    print("=" * 110)

    for s, aud, aud_p in seg_records:
        ord_id = s.segment_order
        p = scheduled_pieces.get(ord_id)
        khmer_text = (s.khmer_text or "").strip()
        eng_text = (s.source_text or "").strip()
        char_count = len(khmer_text)
        avail_window = s.end_time - s.start_time

        if aud_p and aud_p.exists():
            total_dur, lead_sil, trail_sil, int_sil, act_dur, int_sil_list = measure_silences(aud_p)
        else:
            total_dur = aud.duration_seconds if aud else 0.0
            lead_sil, trail_sil, int_sil, act_dur = 0.0, 0.0, 0.0, total_dur
            int_sil_list = []

        total_raw_dur += total_dur
        total_internal_silence += int_sil
        total_lead_silence += lead_sil
        total_trail_silence += trail_sil
        total_active_dur += act_dur

        raw_overflow = max(0.0, total_dur - avail_window)
        total_overflow += raw_overflow

        applied_tempo = p.applied_tempo if p else 1.0
        processed_dur = p.processed_duration if p else (total_dur / applied_tempo)

        raw_char_rate = (char_count / total_dur) if total_dur > 0 else 0.0
        active_char_rate = (char_count / act_dur) if act_dur > 0 else 0.0

        # Diagnosis: Unusually slow vs naturally long
        # Conversational Khmer is ~12-16 chars/sec.
        # If raw_char_rate < 10.0 chars/sec OR active_char_rate < 12.0 chars/sec OR int_sil > 0.8s
        slow_reasons = []
        if raw_char_rate < 9.5:
            slow_reasons.append(f"sluggish delivery ({raw_char_rate:.1f} ch/s < 9.5)")
        if int_sil > 0.70:
            slow_reasons.append(f"long internal pause ({int_sil:.2f}s)")
        if lead_sil + trail_sil > 0.60:
            slow_reasons.append(f"excessive boundary silence ({lead_sil + trail_sil:.2f}s)")

        is_slow = len(slow_reasons) > 0
        is_naturally_long = (not is_slow) and (raw_overflow > 0.0)

        item = {
            "order": ord_id,
            "segment_id": s.id,
            "khmer_text": khmer_text,
            "english_text": eng_text,
            "char_count": char_count,
            "available_window": round(avail_window, 3),
            "raw_duration": round(total_dur, 3),
            "processed_duration": round(processed_dur, 3),
            "applied_tempo": round(applied_tempo, 3),
            "leading_silence": round(lead_sil, 3),
            "trailing_silence": round(trail_sil, 3),
            "internal_silence": round(int_sil, 3),
            "active_duration": round(act_dur, 3),
            "raw_char_rate": round(raw_char_rate, 2),
            "active_char_rate": round(active_char_rate, 2),
            "raw_overflow": round(raw_overflow, 3),
            "is_unusually_slow": is_slow,
            "is_naturally_long": is_naturally_long,
            "slow_reasons": slow_reasons,
        }
        results.append(item)

    print(f"\n{'#':2} | {'Avail':5} | {'RawDur':6} | {'Active':6} | {'IntSil':6} | {'Tempo':5} | {'Raw ch/s':8} | {'Act ch/s':8} | {'Overflow':8} | {'Diagnosis'}")
    print("-" * 110)
    slow_count = 0
    overflow_count = 0
    for r in results:
        status_str = "NORMAL"
        if r["is_unusually_slow"]:
            status_str = "SLOW: " + ", ".join(r["slow_reasons"])
            slow_count += 1
        elif r["is_naturally_long"]:
            status_str = f"NATURALLY LONG (fit via speed {r['applied_tempo']}x)"

        if r["raw_overflow"] > 0:
            overflow_count += 1

        print(
            f"{r['order']:02d} | {r['available_window']:5.2f}s | {r['raw_duration']:5.2f}s | {r['active_duration']:5.2f}s | "
            f"{r['internal_silence']:5.2f}s | {r['applied_tempo']:4.2f}x | {r['raw_char_rate']:6.1f}/s | "
            f"{r['active_char_rate']:6.1f}/s | {r['raw_overflow']:+6.2f}s | {status_str}"
        )

    print("-" * 110)
    print(f"SUMMARY:")
    print(f"  Total Raw TTS Duration      : {total_raw_dur:.3f}s")
    print(f"  Total Active Speaking Dur   : {total_active_dur:.3f}s")
    print(f"  Total Internal Silence      : {total_internal_silence:.3f}s")
    print(f"  Total Boundary Silence      : {total_lead_silence + total_trail_silence:.3f}s")
    print(f"  Units with Raw Overflow     : {overflow_count} / {len(trans_segs)}")
    print(f"  Total Raw Overflow          : {total_overflow:.3f}s")
    print(f"  Units with Unusually Slow   : {slow_count} / {len(trans_segs)}")

    output_path = Path("/app/data/outputs/slow_tts_investigation_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "project_id": project_id,
                "video_duration": target_dur,
                "total_units": len(trans_segs),
                "total_raw_duration": round(total_raw_dur, 3),
                "total_active_duration": round(total_active_dur, 3),
                "total_internal_silence": round(total_internal_silence, 3),
                "total_lead_silence": round(total_lead_silence, 3),
                "total_trail_silence": round(total_trail_silence, 3),
                "total_raw_overflow": round(total_overflow, 3),
                "slow_units_count": slow_count,
                "overflow_units_count": overflow_count,
                "units": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"Detailed analysis saved to: {output_path}")


if __name__ == "__main__":
    analyze_speaking_speed()
