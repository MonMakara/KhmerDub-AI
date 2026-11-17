"""
KhmerDub AI - Transcript-to-Audio Exact Segment Fitting Engine
Phase 13E.5: Timed Mode Speech Fitting & Sample-Accurate Timeline Assembly

Fits synthesized Khmer speech segments into exact SRT/VTT time slots by:
1. Measuring real raw audio duration via ffprobe.
2. Computing speed ratio (speed up if too long, slow down if too short).
3. Using Edge TTS native rate control first, then FFmpeg pitch-preserving atempo chaining.
4. Clamping to configurable [min_speed, max_speed] limits.
5. Handling remainders via apad (padding silence) or overflow policies (allow_overlap, truncate_fade, fail).
6. Standardizing all pieces to 24000 Hz mono PCM 16-bit for zero-drift concatenation.
7. Caching raw TTS outputs to avoid redundant synthesis during refitting.
"""

import hashlib
import json
import logging
import math
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from app.core.config import settings
from app.services.tts.registry import get_tts_provider
from app.services.tts.edge import EdgeTTSProvider

logger = logging.getLogger(__name__)

STANDARD_SAMPLE_RATE = 24000
STANDARD_CHANNELS = 1


class TimingOverflowError(Exception):
    """Raised when audio exceeds available slot/gap and overflow_policy is 'fail'."""
    pass


@dataclass
class SegmentFitResult:
    """Detailed metadata for a fitted transcript speech segment."""
    segment_id: str
    segment_order: int
    slot_sec: float
    raw_duration_sec: float
    final_duration_sec: float
    speed_factor_applied: float
    method: str  # "native_rate" | "atempo" | "none"
    padded_sec: float
    status: str  # "fit" | "padded" | "sped_up" | "slowed" | "overflow"
    warning: Optional[str] = None
    output_audio_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "segment_order": self.segment_order,
            "slot_sec": round(self.slot_sec, 3),
            "raw_duration_sec": round(self.raw_duration_sec, 3),
            "final_duration_sec": round(self.final_duration_sec, 3),
            "speed_factor_applied": round(self.speed_factor_applied, 3),
            "method": self.method,
            "padded_sec": round(self.padded_sec, 3),
            "status": self.status,
            "warning": self.warning,
            "output_audio_path": str(self.output_audio_path) if self.output_audio_path else None,
        }


def get_audio_duration_ffprobe(file_path: Path) -> float:
    """Measure exact audio duration in seconds using ffprobe.
    Never estimates from text length.
    """
    if not file_path.exists() or file_path.stat().st_size == 0:
        return 0.0

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            return max(0.0, float(res.stdout.strip()))
    except Exception as e:
        logger.warning("ffprobe measurement failed for %s: %s", file_path, e)

    return 0.0


def build_atempo_filter(tempo: float) -> str:
    """Build FFmpeg audio filter string for pitch-preserving speed adjustment.
    FFmpeg's atempo filter requires 0.5 <= atempo <= 2.0.
    For factors outside this range, chain multiple atempo filters.
    """
    if abs(tempo - 1.0) < 0.001:
        return "anull"

    factors: List[float] = []
    rem = float(tempo)
    while rem > 2.0:
        factors.append(2.0)
        rem /= 2.0
    while rem < 0.5:
        factors.append(0.5)
        rem /= 0.5
    factors.append(round(rem, 5))
    return ",".join(f"atempo={f:.5f}".rstrip("0").rstrip(".") for f in factors)


def get_raw_tts_cache_dir() -> Path:
    """Return directory for caching raw TTS outputs."""
    cache_dir = settings.DATA_DIR / "temp" / "tts_raw_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def compute_tts_cache_key(text: str, voice: str, provider: str, language: str) -> str:
    """Generate SHA256 key for caching raw TTS output."""
    payload = f"{text.strip()}:{voice.strip()}:{provider.strip().lower()}:{language.strip().lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def get_cached_raw_audio(text: str, voice: str, provider: str, language: str) -> Optional[Path]:
    """Retrieve existing raw audio file from cache if valid."""
    key = compute_tts_cache_key(text, voice, provider, language)
    cache_dir = get_raw_tts_cache_dir()
    for ext in ["wav", "mp3"]:
        candidate = cache_dir / f"{key}.{ext}"
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    return None


def save_to_raw_tts_cache(source_path: Path, text: str, voice: str, provider: str, language: str) -> Path:
    """Store generated raw audio into cache for future refits."""
    key = compute_tts_cache_key(text, voice, provider, language)
    cache_dir = get_raw_tts_cache_dir()
    ext = source_path.suffix.lstrip(".") or "wav"
    dest = cache_dir / f"{key}.{ext}"
    try:
        shutil.copy2(source_path, dest)
    except Exception as e:
        logger.warning("Failed to cache raw TTS output: %s", e)
    return dest


def generate_silence_wav(duration_seconds: float, output_path: Path, sample_rate: int = STANDARD_SAMPLE_RATE) -> Path:
    """Generate a silence WAV file of exact duration matching standard format."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.001, duration_seconds)
    sample_count = max(1, round(dur * sample_rate))

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r={sample_rate}:cl=mono",
        "-af", f"atrim=end_sample={sample_count}",
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", str(STANDARD_CHANNELS),
        str(output_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg silence generation failed: {res.stderr}")
    return output_path


def standardize_to_wav(input_path: Path, output_path: Path, sample_rate: int = STANDARD_SAMPLE_RATE) -> Path:
    """Convert any audio file to standardized 24000 Hz mono PCM 16-bit WAV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", str(STANDARD_CHANNELS),
        str(output_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg audio standardization failed: {res.stderr}")
    return output_path


def fit_segment_audio(
    segment_id: str,
    segment_order: int,
    text: str,
    slot_sec: float,
    provider_name: str,
    voice: str,
    language: str,
    work_dir: Path,
    output_path: Path,
    min_speed: float = 0.75,
    max_speed: float = 1.25,
    fit_tolerance_sec: float = 0.05,
    allow_slow_down: bool = True,
    overflow_policy: str = "allow_overlap",
    fill_mode: str = "natural",
    available_window_sec: Optional[float] = None,
    raw_audio_input_path: Optional[Path] = None,
) -> SegmentFitResult:
    """Fit a single speech segment into its designated time slot.

    Follows the exact 6-step fitting protocol:
    1. Obtain normal rate synthesis and measure real duration with ffprobe.
    2. Compute speed ratio.
    3. Prefer Edge TTS native rate control; fallback / refine with FFmpeg atempo (up to 3 iterations).
    4. Enforce min/max speed clamping (fill_mode='stretch' allows slowing to 0.5x, 'natural' to 0.75x).
    5. Pad silence (apad) if shorter; handle overflow (allow_overlap, truncate_fade, fail) if longer at max speed.
    6. Standardize to 24000 Hz mono PCM 16-bit WAV with exact slot duration.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    clean_slot = max(0.01, float(slot_sec))
    clean_prov = provider_name.strip().lower()

    # Step 1: Synthesize at normal rate or use cached / provided raw audio
    raw_path = work_dir / f"seg_{segment_order:03d}_raw.wav"
    cached_path = get_cached_raw_audio(text, voice, clean_prov, language)

    if raw_audio_input_path and raw_audio_input_path.exists() and raw_audio_input_path.stat().st_size > 0:
        shutil.copy2(raw_audio_input_path, raw_path)
    elif cached_path and cached_path.exists() and cached_path.stat().st_size > 0:
        shutil.copy2(cached_path, raw_path)
    else:
        prov = get_tts_provider(clean_prov)
        seg_ext = "wav" if clean_prov in ("voxcpm", "voxcpm2", "custom") else "mp3"
        temp_raw = work_dir / f"seg_{segment_order:03d}_synth_raw.{seg_ext}"
        prov.synthesize(
            text=text,
            output_path=temp_raw,
            language=language,
            voice=voice,
        )
        save_to_raw_tts_cache(temp_raw, text, voice, clean_prov, language)
        shutil.copy2(temp_raw, raw_path)

    raw_dur = get_audio_duration_ffprobe(raw_path)
    if raw_dur <= 0.0:
        raw_dur = 0.1

    # Step 4: Speed limit configuration based on fill_mode
    effective_min_speed = float(min_speed)
    if fill_mode == "stretch":
        effective_min_speed = min(effective_min_speed, 0.5)

    # Step 2: Compute speed ratio
    ratio = raw_dur / clean_slot
    ideal_speed = ratio
    if ratio < 1.0 and not allow_slow_down:
        ideal_speed = 1.0

    # Speed limit clamping
    clamped_speed = max(effective_min_speed, min(max_speed, ideal_speed))

    current_audio = raw_path
    applied_speed = 1.0
    method = "none"

    # Step 3a: Prefer Edge TTS native rate control
    if clean_prov in ("edge", "edge_tts") and abs(clamped_speed - 1.0) >= 0.02:
        edge_prov = get_tts_provider("edge")
        pct = int(round((clamped_speed - 1.0) * 100))
        rate_str = f"{pct:+d}%"
        native_candidate = work_dir / f"seg_{segment_order:03d}_native.mp3"
        try:
            edge_prov.synthesize(
                text=text,
                output_path=native_candidate,
                language=language,
                voice=voice,
                rate=rate_str,
            )
            native_dur = get_audio_duration_ffprobe(native_candidate)
            if native_dur > 0.0:
                current_audio = native_candidate
                applied_speed = clamped_speed
                method = "native_rate"
            else:
                native_dur = raw_dur
        except Exception as e:
            logger.warning("Native Edge rate synthesis failed, falling back to atempo: %s", e)

    # Step 3b & 3c: FFmpeg pitch-preserving atempo (up to 3 iterations)
    curr_dur = get_audio_duration_ffprobe(current_audio)
    if abs(curr_dur - clean_slot) > fit_tolerance_sec:
        iter_audio = current_audio
        iter_dur = curr_dur

        for iteration in range(1, 4):
            needed_correction = iter_dur / clean_slot
            target_tempo = applied_speed * needed_correction
            target_tempo_clamped = max(effective_min_speed, min(max_speed, target_tempo))
            step_factor = target_tempo_clamped / applied_speed

            if abs(step_factor - 1.0) < 0.01:
                break

            filter_str = build_atempo_filter(step_factor)
            step_output = work_dir / f"seg_{segment_order:03d}_atempo_iter_{iteration}.wav"
            cmd_tempo = [
                "ffmpeg",
                "-y",
                "-i", str(iter_audio),
                "-af", filter_str,
                "-acodec", "pcm_s16le",
                "-ar", str(STANDARD_SAMPLE_RATE),
                "-ac", str(STANDARD_CHANNELS),
                str(step_output),
            ]
            res_tempo = subprocess.run(cmd_tempo, capture_output=True, text=True, check=False)
            if res_tempo.returncode == 0:
                measured = get_audio_duration_ffprobe(step_output)
                if measured > 0.0:
                    iter_audio = step_output
                    iter_dur = measured
                    applied_speed = target_tempo_clamped
                    method = "atempo"
                    if abs(iter_dur - clean_slot) <= fit_tolerance_sec:
                        break
            else:
                logger.warning("FFmpeg atempo iteration %d failed: %s", iteration, res_tempo.stderr)
                break

        current_audio = iter_audio
        curr_dur = iter_dur

    # Step 5: Remainder handling
    padded_sec = 0.0
    status = "fit"
    warning = None
    target_samples = max(1, round(clean_slot * STANDARD_SAMPLE_RATE))

    if curr_dur < clean_slot - fit_tolerance_sec:
        # Shorter than slot: pad end with silence to exact slot duration
        padded_sec = clean_slot - curr_dur
        pad_output = work_dir / f"seg_{segment_order:03d}_padded.wav"
        cmd_pad = [
            "ffmpeg",
            "-y",
            "-i", str(current_audio),
            "-af", f"apad=whole_dur={clean_slot:.5f},atrim=end_sample={target_samples}",
            "-acodec", "pcm_s16le",
            "-ar", str(STANDARD_SAMPLE_RATE),
            "-ac", str(STANDARD_CHANNELS),
            str(pad_output),
        ]
        res_pad = subprocess.run(cmd_pad, capture_output=True, text=True, check=False)
        if res_pad.returncode == 0:
            current_audio = pad_output
            curr_dur = get_audio_duration_ffprobe(pad_output)
            status = "slowed" if (applied_speed < 0.99) else "padded"
        else:
            logger.warning("FFmpeg apad failed: %s", res_pad.stderr)
            status = "slowed" if (applied_speed < 0.99) else "fit"

    elif curr_dur > clean_slot + fit_tolerance_sec:
        # Longer than slot even after speed adjustment
        overflow_sec = curr_dur - clean_slot
        status = "overflow"
        warning = (
            f"Segment #{segment_order} duration ({curr_dur:.2f}s at {applied_speed:.2f}x speed) "
            f"exceeds slot ({clean_slot:.2f}s) by {overflow_sec:.2f}s."
        )

        clean_policy = overflow_policy.strip().lower()
        if clean_policy == "fail":
            raise TimingOverflowError(warning)
        elif clean_policy == "truncate_fade":
            fade_output = work_dir / f"seg_{segment_order:03d}_truncated.wav"
            fade_start = max(0.0, clean_slot - 0.05)
            cmd_trunc = [
                "ffmpeg",
                "-y",
                "-i", str(current_audio),
                "-af", f"atrim=0:{clean_slot:.5f},afade=t=out:st={fade_start:.5f}:d=0.05",
                "-acodec", "pcm_s16le",
                "-ar", str(STANDARD_SAMPLE_RATE),
                "-ac", str(STANDARD_CHANNELS),
                str(fade_output),
            ]
            res_trunc = subprocess.run(cmd_trunc, capture_output=True, text=True, check=False)
            if res_trunc.returncode == 0:
                current_audio = fade_output
                curr_dur = get_audio_duration_ffprobe(fade_output)
        else:
            # Default "allow_overlap": allow speech to run into gap until next segment starts
            if available_window_sec is not None and available_window_sec > 0.05:
                max_allowed = available_window_sec
                if curr_dur > max_allowed:
                    # Try gentle pitch-preserving atempo acceleration (up to 1.35x) before clipping speech
                    needed_extra = curr_dur / max_allowed
                    if needed_extra <= 1.35 and applied_speed * needed_extra <= 1.35:
                        rescue_filter = build_atempo_filter(needed_extra)
                        rescue_output = work_dir / f"seg_{segment_order:03d}_rescue.wav"
                        cmd_res = [
                            "ffmpeg", "-y", "-i", str(current_audio),
                            "-af", rescue_filter,
                            "-acodec", "pcm_s16le",
                            "-ar", str(STANDARD_SAMPLE_RATE),
                            "-ac", str(STANDARD_CHANNELS),
                            str(rescue_output),
                        ]
                        res_r = subprocess.run(cmd_res, capture_output=True, text=True, check=False)
                        if res_r.returncode == 0:
                            current_audio = rescue_output
                            curr_dur = get_audio_duration_ffprobe(rescue_output)
                            applied_speed = round(applied_speed * needed_extra, 2)

                    if curr_dur > max_allowed:
                        fade_output = work_dir / f"seg_{segment_order:03d}_gap_truncated.wav"
                        fade_start = max(0.0, max_allowed - 0.05)
                        cmd_gap = [
                            "ffmpeg",
                            "-y",
                            "-i", str(current_audio),
                            "-af", f"atrim=0:{max_allowed:.5f},afade=t=out:st={fade_start:.5f}:d=0.05",
                            "-acodec", "pcm_s16le",
                            "-ar", str(STANDARD_SAMPLE_RATE),
                            "-ac", str(STANDARD_CHANNELS),
                            str(fade_output),
                        ]
                        res_gap = subprocess.run(cmd_gap, capture_output=True, text=True, check=False)
                        if res_gap.returncode == 0:
                            current_audio = fade_output
                            curr_dur = get_audio_duration_ffprobe(fade_output)
            # When available_window_sec is None, allow speech to breathe naturally into gap without dropping words
    else:
        # Within tolerance: force sample-exact length via apad + atrim to eliminate fractional drift
        exact_output = work_dir / f"seg_{segment_order:03d}_exact.wav"
        cmd_exact = [
            "ffmpeg",
            "-y",
            "-i", str(current_audio),
            "-af", f"apad=whole_dur={clean_slot:.5f},atrim=end_sample={target_samples}",
            "-acodec", "pcm_s16le",
            "-ar", str(STANDARD_SAMPLE_RATE),
            "-ac", str(STANDARD_CHANNELS),
            str(exact_output),
        ]
        res_exact = subprocess.run(cmd_exact, capture_output=True, text=True, check=False)
        if res_exact.returncode == 0:
            current_audio = exact_output
            curr_dur = get_audio_duration_ffprobe(exact_output)

        if applied_speed > 1.01:
            status = "sped_up"
        elif applied_speed < 0.99:
            status = "slowed"
        else:
            status = "fit"

    # Step 6: Standardize final audio to 24000 Hz mono PCM 16-bit WAV
    standardize_to_wav(current_audio, output_path, sample_rate=STANDARD_SAMPLE_RATE)
    final_dur = get_audio_duration_ffprobe(output_path)

    fit_res = SegmentFitResult(
        segment_id=segment_id,
        segment_order=segment_order,
        slot_sec=clean_slot,
        raw_duration_sec=raw_dur,
        final_duration_sec=final_dur,
        speed_factor_applied=applied_speed,
        method=method,
        padded_sec=padded_sec,
        status=status,
        warning=warning,
        output_audio_path=output_path,
    )

    logger.info(
        "[TimedFit] Segment #%d (id=%s): slot=%.3fs, raw_dur=%.3fs, speed_factor=%.3fx, final_dur=%.3fs, fill_mode=%s, status=%s, padded=%.3fs",
        segment_order,
        segment_id,
        fit_res.slot_sec,
        fit_res.raw_duration_sec,
        fit_res.speed_factor_applied,
        fit_res.final_duration_sec,
        fill_mode,
        fit_res.status,
        fit_res.padded_sec,
    )

    return fit_res


def assemble_fitted_timeline(
    task_id: str,
    fitted_segments: List[SegmentFitResult],
    segment_timing_list: List[Dict[str, Any]],
    output_wav_path: Path,
    output_mp3_path: Path,
    target_timeline_duration: Optional[float] = None,
) -> Tuple[Path, Path, float]:
    """Assemble standardized fitted segments onto an exact timeline using sample offsets.

    Guarantees:
    - Never concatenates segments; creates silence of total length (last end timestamp).
    - Every segment onset aligns with its start timestamp within < 50ms (sample accurate).
    - Total timeline duration equals target_timeline_duration (or last SRT end timestamp).
    """
    import array
    import wave
    try:
        import numpy as np
        has_numpy = True
    except ImportError:
        has_numpy = False

    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    output_mp3_path.parent.mkdir(parents=True, exist_ok=True)

    timing_by_order = {
        int(item.get("segment_order", idx + 1)): item
        for idx, item in enumerate(segment_timing_list)
    }

    sorted_fits = sorted(fitted_segments, key=lambda f: f.segment_order)
    if not sorted_fits:
        raise ValueError("Cannot assemble timeline without speech segments.")

    # Determine timeline end timestamp
    max_srt_end = max(
        (float(timing_by_order.get(f.segment_order, {}).get("end_time", 0.0)) for f in sorted_fits),
        default=0.0,
    )
    max_speech_end = max(
        (float(timing_by_order.get(f.segment_order, {}).get("start_time", 0.0)) + f.final_duration_sec for f in sorted_fits),
        default=0.0,
    )
    calculated_end = max(max_srt_end, max_speech_end)
    total_target_duration = (
        float(target_timeline_duration)
        if (target_timeline_duration is not None and float(target_timeline_duration) > 0.0)
        else calculated_end
    )
    total_target_duration = max(0.1, total_target_duration)
    total_frames = max(1, round(total_target_duration * STANDARD_SAMPLE_RATE))

    # Pre-allocate silence buffer for the entire timeline
    if has_numpy:
        timeline_samples = np.zeros(total_frames, dtype=np.int16)
    else:
        timeline_samples = array.array("h", [0] * total_frames)

    for fit in sorted_fits:
        t_info = timing_by_order.get(fit.segment_order, {})
        seg_start = max(0.0, float(t_info.get("start_time", 0.0)))
        start_frame = round(seg_start * STANDARD_SAMPLE_RATE)

        seg_audio = fit.output_audio_path
        if not seg_audio or not seg_audio.exists():
            raise FileNotFoundError(f"Missing audio for segment #{fit.segment_order} at {seg_audio}")

        with wave.open(str(seg_audio), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw_frames = wf.readframes(n_frames)

        # Standardize if not 24000Hz mono 16-bit
        if n_channels != STANDARD_CHANNELS or sampwidth != 2 or framerate != STANDARD_SAMPLE_RATE:
            temp_std = seg_audio.parent / f"std_{seg_audio.name}"
            standardize_to_wav(seg_audio, temp_std, sample_rate=STANDARD_SAMPLE_RATE)
            with wave.open(str(temp_std), "rb") as wf:
                raw_frames = wf.readframes(wf.getnframes())

        if has_numpy:
            seg_arr = np.frombuffer(raw_frames, dtype=np.int16)
            end_frame = min(total_frames, start_frame + len(seg_arr))
            if end_frame > start_frame:
                slice_len = end_frame - start_frame
                mixed = (
                    timeline_samples[start_frame:end_frame].astype(np.int32)
                    + seg_arr[:slice_len].astype(np.int32)
                )
                timeline_samples[start_frame:end_frame] = np.clip(mixed, -32768, 32767).astype(np.int16)
        else:
            seg_samples = array.array("h")
            seg_samples.frombytes(raw_frames)
            end_frame = min(total_frames, start_frame + len(seg_samples))
            if end_frame > start_frame:
                slice_len = end_frame - start_frame
                for i in range(slice_len):
                    idx = start_frame + i
                    val = timeline_samples[idx] + seg_samples[i]
                    if val > 32767:
                        val = 32767
                    elif val < -32768:
                        val = -32768
                    timeline_samples[idx] = val

    # Write master WAV
    with wave.open(str(output_wav_path), "wb") as wf:
        wf.setnchannels(STANDARD_CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(STANDARD_SAMPLE_RATE)
        wf.writeframes(timeline_samples.tobytes())

    final_total_dur = get_audio_duration_ffprobe(output_wav_path)

    # Transcode WAV to MP3 (192kbps)
    cmd_mp3 = [
        "ffmpeg",
        "-y",
        "-i", str(output_wav_path),
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(output_mp3_path),
    ]
    res_mp3 = subprocess.run(cmd_mp3, capture_output=True, text=True, check=False)
    if res_mp3.returncode != 0:
        raise RuntimeError(f"FFmpeg MP3 transcoding failed: {res_mp3.stderr}")

    return output_wav_path, output_mp3_path, final_total_dur
