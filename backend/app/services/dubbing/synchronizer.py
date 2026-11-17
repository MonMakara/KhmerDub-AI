import array
import logging
import math
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

try:
    import numpy as np
    has_numpy = True
except ImportError:
    has_numpy = False

from app.core.storage import resolve_audio_file
from app.models.project import TranscriptSegment, TranslationSegment, GeneratedAudio
from app.services.dubbing.scheduler import TimelineScheduler
from app.services.video.ffmpeg import FFmpegVideoProcessor

logger = logging.getLogger(__name__)


@dataclass
class TimingConflict:
    """Represents a speech segment where Khmer audio duration exceeds the available time window."""
    segment_order: int
    transcript_segment_id: str
    start_time: float
    end_time: float
    original_duration: float
    khmer_duration: float
    available_window: float
    effective_window: float
    safety_margin_seconds: float
    required_tempo: float
    max_tempo_factor: float
    tempo_factor: float
    overflow_seconds: float
    suggested_action: str
    message: str


class TimingConflictError(Exception):
    """Raised when one or more speech segments cannot fit within the available time window."""

    def __init__(self, conflicts: List[TimingConflict], message: Optional[str] = None):
        self.conflicts = conflicts
        count = len(conflicts)
        msg = message or (
            f"Cannot export dubbed video: {count} speech segment(s) exceed available timing window. "
            f"Maximum tempo adjustment of 1.25x is insufficient to prevent speech truncation."
        )
        super().__init__(msg)


@dataclass
class SynchronizationResult:
    """Result of the audio synchronization engine."""
    timeline_path: Path
    total_duration_seconds: float
    conflicts: List[TimingConflict] = field(default_factory=list)
    segments_count: int = 0


class AudioSynchronizationService:
    """Engine responsible for aligning Khmer speech segments against original video timestamps,
    applying modest tempo adjustment (up to 1.25x), detecting timing conflicts, and producing
    a continuous, gap-filled audio timeline WAV.
    """

    def __init__(
        self,
        max_tempo_factor: float = 1.25,
        safety_margin_seconds: float = 0.05,
        min_pause_seconds: float = 0.12,
        sample_rate: int = 44100,
        channels: int = 2,
        ffmpeg_bin: str = "ffmpeg",
        video_processor: Optional[FFmpegVideoProcessor] = None,
    ):
        self.max_tempo_factor = max_tempo_factor
        self.safety_margin_seconds = max(0.0, float(safety_margin_seconds))
        self.min_pause_seconds = max(0.0, float(min_pause_seconds))
        self.sample_rate = sample_rate
        self.channels = channels
        self.ffmpeg_bin = ffmpeg_bin
        self.video_processor = video_processor or FFmpegVideoProcessor()

    def generate_silence(self, duration_seconds: float, output_path: Path) -> Path:
        """Generate a silent PCM WAV file of specified duration."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sample_count = max(1, round(duration_seconds * self.sample_rate))

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r={self.sample_rate}:cl=stereo",
            "-af", f"atrim=end_sample={sample_count}",
            "-acodec", "pcm_s16le",
            "-ar", str(self.sample_rate),
            "-ac", str(self.channels),
            str(output_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg failed to generate silence: {res.stderr}")
        return output_path

    def convert_to_standard_wav(self, input_audio: Path, output_path: Path) -> Path:
        """Convert any input audio format (MP3, WAV) into standard 44.1kHz stereo 16-bit PCM WAV."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-i", str(input_audio),
            "-acodec", "pcm_s16le",
            "-ar", str(self.sample_rate),
            "-ac", str(self.channels),
            str(output_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg failed to standardize audio {input_audio}: {res.stderr}")
        return output_path

    def trim_audio_silence(self, input_audio: Path, output_path: Path) -> Path:
        """Trim excessive silence padding from start and end of generated TTS audio without clipping speech."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        is_same = (input_audio.resolve() == output_path.resolve())
        target_path = output_path.with_suffix(".trim_tmp.wav") if is_same else output_path

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-i", str(input_audio),
            "-af", "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-50dB:detection=peak,areverse,silenceremove=start_periods=1:start_duration=0.05:start_threshold=-50dB:detection=peak,areverse",
            "-acodec", "pcm_s16le",
            "-ar", str(self.sample_rate),
            "-ac", str(self.channels),
            str(target_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            if is_same and target_path.exists():
                target_path.unlink()
            return self.convert_to_standard_wav(input_audio, output_path)

        if is_same:
            target_path.replace(output_path)

        return output_path

    def adjust_tempo(self, input_audio: Path, output_path: Path, tempo_factor: float) -> Path:
        """Adjust speech tempo using FFmpeg's atempo filter without altering pitch."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        factor = max(0.5, min(2.0, tempo_factor))

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-i", str(input_audio),
            "-filter:a", f"atempo={factor:.3f}",
            "-acodec", "pcm_s16le",
            "-ar", str(self.sample_rate),
            "-ac", str(self.channels),
            str(output_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg atempo adjustment failed for {input_audio}: {res.stderr}")
        return output_path

    def render_speech_piece(
        self,
        input_audio: Path,
        output_path: Path,
        tempo_factor: float = 1.0,
        apply_micro_fade: bool = True,
        trim_start: Optional[float] = None,
        trim_end: Optional[float] = None,
    ) -> Path:
        """Render a speech piece with optional conservative boundary trimming,
        pitch-preserving tempo adjustment, and boundary micro-fades (8ms)
        to guarantee zero clicks and intact phonemes.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tempo = max(0.5, min(2.0, float(tempo_factor)))
        has_tempo = abs(tempo - 1.0) > 0.01

        cmd = [self.ffmpeg_bin, "-y"]
        if trim_start is not None and trim_end is not None and (trim_end - trim_start) > 0.05:
            cmd.extend(["-ss", f"{trim_start:.3f}", "-to", f"{trim_end:.3f}"])

        cmd.extend(["-i", str(input_audio)])

        filters = []
        if has_tempo:
            filters.append(f"atempo={tempo:.3f}")
        if apply_micro_fade:
            # 10ms smooth micro-fade at head and tail to guarantee zero clicks and intact phonemes
            filters.append("afade=t=in:ss=0:d=0.010,areverse,afade=t=in:ss=0:d=0.010,areverse")

        if filters:
            cmd.extend(["-af", ",".join(filters)])
        if output_path.suffix.lower() == ".mp3":
            cmd.extend([
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                "-ar", str(self.sample_rate),
                "-ac", str(self.channels),
                str(output_path),
            ])
        else:
            cmd.extend([
                "-c:a", "pcm_s16le",
                "-ar", str(self.sample_rate),
                "-ac", str(self.channels),
                str(output_path),
            ])

        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg failed to render speech piece {input_audio}: {res.stderr}")
        return output_path

    def assemble_timeline_pcm(
        self,
        pieces_with_timing: List[Tuple[Path, float]],
        target_duration: float,
        output_path: Path,
        overflow_policy: str = "allow_overlap",
        fit_to_target_duration: bool = False,
    ) -> float:
        """Assemble audio pieces onto a sample-accurate timeline WAV via in-memory PCM mixing.

        Guarantees:
        - Exact start offset per segment: round(start_time * sample_rate)
        - Exact total timeline duration: round(target_duration * sample_rate)
        - Fast in-memory mixing with zero FFmpeg temp silence gap files or concat demuxer drift.
        - Non-blocking overflow handling: clips/sums overlapping signals smoothly.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not pieces_with_timing and target_duration <= 0.0:
            raise ValueError("Cannot assemble timeline without audio pieces or valid target duration.")

        # Measure end time of all pieces
        max_piece_end = 0.0
        for p_path, st in pieces_with_timing:
            if p_path and p_path.exists():
                dur = self.video_processor.get_audio_duration(p_path)
                max_piece_end = max(max_piece_end, float(st) + dur)

        if fit_to_target_duration and target_duration > 0.0:
            total_dur = float(target_duration)
        else:
            total_dur = max(float(target_duration), max_piece_end)
        total_dur = max(0.05, total_dur)

        total_frames = max(1, round(total_dur * self.sample_rate))

        if has_numpy:
            timeline = np.zeros((total_frames, self.channels), dtype=np.int16)
        else:
            timeline = array.array("h", [0] * (total_frames * self.channels))

        # Sort pieces by start_time
        sorted_pieces = sorted(pieces_with_timing, key=lambda x: float(x[1]))

        for piece_path, start_sec in sorted_pieces:
            if not piece_path or not piece_path.exists():
                logger.warning("Timeline piece not found at %s; skipping.", piece_path)
                continue

            st = max(0.0, float(start_sec))
            start_frame = round(st * self.sample_rate)
            if start_frame >= total_frames:
                continue

            # Read audio frames
            with wave.open(str(piece_path), "rb") as wf:
                ch = wf.getnchannels()
                sw = wf.getsampwidth()
                fr = wf.getframerate()
                n_fr = wf.getnframes()
                raw_bytes = wf.readframes(n_fr)

            # Standardize if not matching target sample_rate, channels, and 16-bit
            if ch != self.channels or sw != 2 or fr != self.sample_rate:
                std_path = piece_path.parent / f"std_pcm_{piece_path.name}"
                self.convert_to_standard_wav(piece_path, std_path)
                with wave.open(str(std_path), "rb") as wf:
                    raw_bytes = wf.readframes(wf.getnframes())

            if has_numpy:
                piece_arr = np.frombuffer(raw_bytes, dtype=np.int16)
                if self.channels == 2:
                    if len(piece_arr) % 2 != 0:
                        piece_arr = piece_arr[:len(piece_arr) - (len(piece_arr) % 2)]
                    piece_arr = piece_arr.reshape(-1, 2)
                else:
                    piece_arr = piece_arr.reshape(-1, 1)

                end_frame = min(total_frames, start_frame + len(piece_arr))
                if end_frame > start_frame:
                    slice_len = end_frame - start_frame
                    # Mix signals with 16-bit clipping protection
                    mixed = (
                        timeline[start_frame:end_frame].astype(np.int32)
                        + piece_arr[:slice_len].astype(np.int32)
                    )
                    timeline[start_frame:end_frame] = np.clip(mixed, -32768, 32767).astype(np.int16)
            else:
                piece_samples = array.array("h")
                piece_samples.frombytes(raw_bytes)
                channels = self.channels
                num_frames = len(piece_samples) // channels
                end_frame = min(total_frames, start_frame + num_frames)
                if end_frame > start_frame:
                    slice_frames = end_frame - start_frame
                    for f in range(slice_frames):
                        for c in range(channels):
                            t_idx = (start_frame + f) * channels + c
                            p_idx = f * channels + c
                            val = timeline[t_idx] + piece_samples[p_idx]
                            timeline[t_idx] = max(-32768, min(32767, val))

        # Write output master WAV
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(timeline.tobytes())

        final_duration = self.video_processor.get_audio_duration(output_path)
        if final_duration <= 0.0:
            final_duration = total_frames / self.sample_rate
        return final_duration

    def synchronize(
        self,
        project_id: str,
        segment_items: List[Tuple[TranscriptSegment, TranslationSegment, GeneratedAudio]],
        target_duration: float,
        output_timeline_path: Path,
        strict_validation: bool = True,
        max_tempo_factor: Optional[float] = None,
        trim_silence: bool = False,
        pipeline_version: str = "v2.1",
        fill_mode: str = "natural",
        overflow_policy: str = "allow_overlap",
    ) -> SynchronizationResult:
        """Align speech segments onto a unified timeline WAV matching target video duration."""
        if not segment_items:
            raise ValueError("No speech segments provided for synchronization.")

        active_max_tempo = float(max_tempo_factor) if max_tempo_factor is not None else self.max_tempo_factor
        active_max_tempo = min(1.25, max(1.0, active_max_tempo))
        output_timeline_path.parent.mkdir(parents=True, exist_ok=True)
        work_dir = output_timeline_path.parent / f"sync_tmp_{project_id}"
        work_dir.mkdir(parents=True, exist_ok=True)

        # Sort items by transcript start time
        sorted_items = sorted(segment_items, key=lambda x: (x[0].start_time, x[0].segment_order))
        total_segments = len(sorted_items)

        pieces_with_timing: List[Tuple[Path, float]] = []
        conflicts: List[TimingConflict] = []

        try:
            if pipeline_version in ("v2.1", "v2.2", "v2.3"):
                # --- V2.1/V2.2/V2.3: Phrase-Group & Whole-Timeline Adaptive Scheduling with Non-Destructive Audio & Micro-Fades ---
                raw_items = []
                for idx, (t_seg, trans_seg, audio_rec) in enumerate(sorted_items):
                    start_time = max(0.0, float(trans_seg.start_time if trans_seg.start_time is not None else t_seg.start_time))
                    end_time = max(start_time, float(trans_seg.end_time if trans_seg.end_time is not None else t_seg.end_time))
                    orig_dur = max(0.1, end_time - start_time)
                    seg_order = trans_seg.segment_order
                    english_text = trans_seg.source_text or (t_seg.text if t_seg else "")

                    audio_path = resolve_audio_file(project_id, trans_seg.id, audio_rec.audio_path)
                    if not audio_path.exists() or audio_path.stat().st_size == 0:
                        raise FileNotFoundError(
                            f"Generated audio file missing for segment {seg_order} at {audio_path}"
                        )

                    raw_dur = self.video_processor.get_audio_duration(audio_path)
                    if raw_dur <= 0.0:
                        raw_dur = float(audio_rec.duration_seconds or 1.0)

                    raw_items.append({
                        "idx": idx,
                        "segment_order": seg_order,
                        "segment_id": t_seg.id if t_seg else f"trans_{trans_seg.id}",
                        "trans_seg_id": trans_seg.id,
                        "audio_path": audio_path,
                        "start_time": start_time,
                        "end_time": end_time,
                        "orig_duration": orig_dur,
                        "raw_duration": raw_dur,
                        "khmer_text": trans_seg.khmer_text or "",
                        "english_text": english_text,
                        "is_manually_edited": bool(trans_seg.is_manually_edited),
                        "is_outdated": bool(audio_rec.is_outdated or trans_seg.is_outdated),
                    })

                scheduler = TimelineScheduler(
                    max_tempo=active_max_tempo,
                    safety_margin_seconds=self.safety_margin_seconds,
                )
                scheduled_groups = scheduler.schedule_timeline(
                    raw_items,
                    target_duration=target_duration,
                    max_tempo=active_max_tempo,
                    fill_mode=fill_mode,
                )

                for g in scheduled_groups:
                    for p in g.pieces:
                        if p.status == "needs_optimization" and p.overflow_seconds > 0.05:
                            est_words = max(1, math.ceil(p.overflow_seconds / 0.35))
                            action = (
                                f"Shorten the Khmer translation for Segment #{p.segment_order} by approximately "
                                f"{est_words} word(s) (~{p.overflow_seconds:.1f}s), regenerate audio, and retry export."
                            )
                            conflicts.append(
                                TimingConflict(
                                    segment_order=p.segment_order,
                                    transcript_segment_id=p.segment_id,
                                    start_time=p.start_time,
                                    end_time=p.end_time,
                                    original_duration=p.orig_duration,
                                    khmer_duration=p.raw_duration,
                                    available_window=p.available_window,
                                    effective_window=p.effective_window,
                                    safety_margin_seconds=round(self.safety_margin_seconds, 3),
                                    required_tempo=p.required_tempo,
                                    max_tempo_factor=active_max_tempo,
                                    tempo_factor=p.applied_tempo,
                                    overflow_seconds=p.overflow_seconds,
                                    suggested_action=action,
                                    message=(
                                        f"Segment #{p.segment_order} ({p.raw_duration:.1f}s) "
                                        f"exceeds available window ({p.available_window:.2f}s) by {p.overflow_seconds:.1f}s even at {p.applied_tempo}x speed. "
                                        f"{action}"
                                    ),
                                )
                            )

                if strict_validation and conflicts:
                    logger.warning(
                        "Strict duration validation blocked export: %d timing conflict(s) detected.",
                        len(conflicts),
                    )
                    raise TimingConflictError(conflicts=conflicts)

                # Second pass: render pieces with micro-fades and collect timeline offsets
                for g in scheduled_groups:
                    for s_idx, piece in enumerate(g.pieces):
                        # Anchor desired start time cleanly according to authoritative schedule
                        desired_start = max(piece.allocated_start, 0.0)

                        piece_path = work_dir / f"piece_{piece.idx}_order_{piece.segment_order}.wav"
                        if piece.processed_audio_path:
                            piece_path = piece.processed_audio_path
                        elif piece.has_boundary_trim:
                            self.render_speech_piece(
                                piece.audio_path,
                                piece_path,
                                tempo_factor=piece.applied_tempo,
                                apply_micro_fade=True,
                                trim_start=piece.trim_start,
                                trim_end=piece.trim_end,
                            )
                        else:
                            self.render_speech_piece(
                                piece.audio_path,
                                piece_path,
                                tempo_factor=piece.applied_tempo,
                                apply_micro_fade=True,
                            )
                        piece_dur = self.video_processor.get_audio_duration(piece_path)
                        logger.info(
                            "[DubbingSync:V2] Segment #%d: slot=%.2fs, raw_dur=%.2fs, tempo=%.2fx, final_dur=%.2fs, start=%.2fs, fill_mode=%s",
                            piece.segment_order,
                            piece.orig_duration,
                            piece.raw_duration,
                            piece.applied_tempo,
                            piece_dur,
                            desired_start,
                            fill_mode,
                        )
                        pieces_with_timing.append((piece_path, desired_start))

            else:
                # 1. Legacy first pass: analyze timing windows and detect any unresolved conflicts
                analyzed_segments: List[dict] = []
                for idx, (t_seg, trans_seg, audio_rec) in enumerate(sorted_items):
                    start_time = max(0.0, float(t_seg.start_time))
                    end_time = max(start_time, float(t_seg.end_time))
                    orig_dur = max(0.1, end_time - start_time)

                    # Determine next boundary
                    if idx < total_segments - 1:
                        next_start = float(sorted_items[idx + 1][0].start_time)
                        if next_start > start_time:
                            avail_window = min(next_start - start_time, target_duration - start_time)
                        else:
                            avail_window = max(0.1, min(orig_dur, target_duration - start_time))
                    else:
                        avail_window = max(0.1, target_duration - start_time)

                    avail_window = max(0.1, avail_window)

                    # Resolve source audio file
                    audio_path = resolve_audio_file(project_id, trans_seg.id, audio_rec.audio_path)
                    if not audio_path.exists() or audio_path.stat().st_size == 0:
                        raise FileNotFoundError(
                            f"Generated audio file missing for segment {t_seg.segment_order} at {audio_path}"
                        )

                    if trim_silence:
                        trimmed_src = work_dir / f"trimmed_src_{idx}.wav"
                        self.trim_audio_silence(audio_path, trimmed_src)
                        source_for_piece = trimmed_src
                        raw_dur = self.video_processor.get_audio_duration(trimmed_src)
                    else:
                        source_for_piece = audio_path
                        raw_dur = self.video_processor.get_audio_duration(audio_path)

                    if raw_dur <= 0.0:
                        raw_dur = float(audio_rec.duration_seconds or 1.0)

                    # Timing strategy
                    tempo = 1.0
                    required_tempo = 1.0

                    if raw_dur <= orig_dur:
                        if fill_mode == "stretch" and orig_dur > 0.2:
                            tempo = max(0.50, min(1.0, round(raw_dur / orig_dur, 2)))
                        else:
                            tempo = 1.0
                        required_tempo = 1.0
                    elif raw_dur <= avail_window:
                        pause_left = avail_window - raw_dur
                        if pause_left < 0.2 and (raw_dur / orig_dur) > 1.1:
                            target_dur = max(orig_dur, avail_window - 0.2)
                            tempo = min(active_max_tempo, max(1.0, round(raw_dur / target_dur, 2)))
                        else:
                            tempo = 1.0
                        required_tempo = 1.0
                    else:
                        # raw_dur > avail_window: exceeds available interval
                        effective_window = max(0.05, round(avail_window - self.safety_margin_seconds, 3))
                        required_tempo = round(raw_dur / effective_window, 2)

                        if required_tempo <= active_max_tempo:
                            tempo = required_tempo
                        else:
                            tempo = active_max_tempo
                            adjusted_est = raw_dur / tempo
                            overflow = round(adjusted_est - effective_window, 2)
                            if overflow > 0.05:
                                est_words = max(1, math.ceil(overflow / 0.35))
                                action = (
                                    f"Shorten the Khmer translation for Segment #{t_seg.segment_order} by approximately "
                                    f"{est_words} word(s) (~{overflow:.1f}s), regenerate audio, and retry export."
                                )
                                conflicts.append(
                                    TimingConflict(
                                        segment_order=t_seg.segment_order,
                                        transcript_segment_id=t_seg.id,
                                        start_time=round(start_time, 2),
                                        end_time=round(end_time, 2),
                                        original_duration=round(orig_dur, 2),
                                        khmer_duration=round(raw_dur, 2),
                                        available_window=round(avail_window, 2),
                                        effective_window=round(effective_window, 2),
                                        safety_margin_seconds=round(self.safety_margin_seconds, 3),
                                        required_tempo=required_tempo,
                                        max_tempo_factor=active_max_tempo,
                                        tempo_factor=tempo,
                                        overflow_seconds=overflow,
                                        suggested_action=action,
                                        message=(
                                            f"Segment #{t_seg.segment_order} ({raw_dur:.1f}s) exceeds available window "
                                            f"({avail_window:.2f}s raw, {effective_window:.2f}s effective with {int(self.safety_margin_seconds * 1000)}ms safety margin) "
                                            f"by {overflow:.1f}s even at {tempo}x speed. "
                                            f"{action}"
                                        ),
                                    )
                                )

                    analyzed_segments.append({
                        "idx": idx,
                        "t_seg": t_seg,
                        "trans_seg": trans_seg,
                        "audio_rec": audio_rec,
                        "audio_path": source_for_piece,
                        "start_time": start_time,
                        "orig_dur": orig_dur,
                        "raw_dur": raw_dur,
                        "tempo": tempo,
                    })

                if strict_validation and conflicts:
                    logger.warning(
                        "Strict duration validation blocked export: %d timing conflict(s) detected.",
                        len(conflicts),
                    )
                    raise TimingConflictError(conflicts=conflicts)

                # 2. Second pass: render pieces and collect offsets
                for item in analyzed_segments:
                    idx = item["idx"]
                    t_seg = item["t_seg"]
                    audio_path = item["audio_path"]
                    start_time = item["start_time"]
                    orig_dur = item["orig_dur"]
                    raw_dur = item["raw_dur"]
                    tempo = item["tempo"]

                    piece_path = work_dir / f"piece_{idx}_order_{t_seg.segment_order}.wav"
                    if abs(tempo - 1.0) > 0.02:
                        self.adjust_tempo(audio_path, piece_path, tempo)
                    else:
                        self.convert_to_standard_wav(audio_path, piece_path)

                    piece_dur = self.video_processor.get_audio_duration(piece_path)
                    if piece_dur <= 0.0:
                        piece_dur = raw_dur / tempo

                    logger.info(
                        "[DubbingSync:Legacy] Segment #%d: slot=%.2fs, raw_dur=%.2fs, tempo=%.2fx, final_dur=%.2fs, start=%.2fs, fill_mode=%s",
                        t_seg.segment_order,
                        orig_dur,
                        raw_dur,
                        tempo,
                        piece_dur,
                        start_time,
                        fill_mode,
                    )
                    pieces_with_timing.append((piece_path, start_time))

            # Assemble master timeline WAV using sample-accurate PCM buffer
            final_duration = self.assemble_timeline_pcm(
                pieces_with_timing=pieces_with_timing,
                target_duration=target_duration,
                output_path=output_timeline_path,
                overflow_policy=overflow_policy,
            )

            if strict_validation and target_duration > 0 and (final_duration > target_duration + 0.150):
                overflow_amount = final_duration - target_duration
                logger.warning(
                    "Synchronized Khmer audio timeline (%.3fs) exceeds target video duration (%.3fs) by %.3fs.",
                    final_duration,
                    target_duration,
                    overflow_amount,
                )
                if not conflicts:
                    conflicts.append(
                        TimingConflict(
                            segment_order=total_segments,
                            transcript_segment_id="",
                            start_time=0.0,
                            end_time=target_duration,
                            original_duration=target_duration,
                            khmer_duration=final_duration,
                            available_window=target_duration,
                            effective_window=target_duration,
                            safety_margin_seconds=round(self.safety_margin_seconds, 3),
                            required_tempo=active_max_tempo,
                            max_tempo_factor=active_max_tempo,
                            tempo_factor=active_max_tempo,
                            overflow_seconds=round(overflow_amount, 2),
                            suggested_action="Shorten Khmer translations to fit within video duration.",
                            message=(
                                f"Synchronized Khmer audio timeline ({final_duration:.2f}s) exceeds target video duration "
                                f"({target_duration:.2f}s) by {overflow_amount:.2f}s even at {active_max_tempo}x speed. "
                                f"Shorten the Khmer translations to fit within the video duration."
                            ),
                        )
                    )
                raise TimingConflictError(conflicts=conflicts)

            logger.info(
                "Generated Khmer audio timeline %s: %.2fs (target=%.2fs, conflicts=%d)",
                output_timeline_path.name,
                final_duration,
                target_duration,
                len(conflicts),
            )

            return SynchronizationResult(
                timeline_path=output_timeline_path,
                total_duration_seconds=round(final_duration, 2),
                conflicts=conflicts,
                segments_count=total_segments,
            )

        finally:
            # Safely clean up intermediate temp files
            try:
                for f in work_dir.glob("*"):
                    try:
                        f.unlink()
                    except OSError:
                        pass
                work_dir.rmdir()
            except OSError as e:
                logger.warning("Could not completely remove sync work directory %s: %s", work_dir, e)

    def synchronize_timed_segments(
        self,
        task_id: str,
        segments: List[dict],
        output_timeline_path: Path,
        target_duration: Optional[float] = None,
        strict_validation: bool = False,
        max_tempo_factor: Optional[float] = None,
        trim_silence: bool = False,
        pipeline_version: str = "v2.1",
        fill_mode: str = "natural",
        overflow_policy: str = "allow_overlap",
    ) -> SynchronizationResult:
        """Align arbitrary timed audio segments onto a timeline WAV matching target timestamps.
        Applies up to max_tempo_factor tempo adjustment without silent truncation,
        places segments at exact sample offsets, detects timing overflows, and generates a unified timeline.
        """
        if not segments:
            raise ValueError("No speech segments provided for timed synchronization.")

        active_max_tempo = float(max_tempo_factor) if max_tempo_factor is not None else self.max_tempo_factor
        output_timeline_path.parent.mkdir(parents=True, exist_ok=True)
        work_dir = output_timeline_path.parent / f"sync_timed_{task_id}"
        work_dir.mkdir(parents=True, exist_ok=True)

        sorted_items = sorted(segments, key=lambda s: (float(s.get("start_time", 0.0)), int(s.get("segment_order", 0))))
        total_segments = len(sorted_items)

        if target_duration is None:
            max_end = max((float(s.get("end_time", 0.0)) for s in sorted_items), default=0.0)
            target_duration = max(max_end, 1.0)

        pieces_with_timing: List[Tuple[Path, float]] = []
        conflicts: List[TimingConflict] = []

        try:
            if pipeline_version in ("v2.1", "v2.2", "v2.3"):
                # --- V2.1/V2.2 Phrase-Group & Whole-Timeline Adaptive Scheduling for Timed Segments ---
                raw_items = []
                for idx, seg in enumerate(sorted_items):
                    start_time = max(0.0, float(seg.get("start_time", 0.0)))
                    end_time = max(start_time, float(seg.get("end_time", start_time + 1.0)))
                    orig_dur = max(0.1, end_time - start_time)
                    seg_order = int(seg.get("segment_order", idx + 1))
                    seg_id = str(seg.get("segment_id", seg_order))
                    audio_path = Path(seg["audio_path"])
                    if not audio_path.exists() or audio_path.stat().st_size == 0:
                        raise FileNotFoundError(f"Segment audio file missing at {audio_path}")

                    raw_dur = self.video_processor.get_audio_duration(audio_path)
                    if raw_dur <= 0.0:
                        raw_dur = float(seg.get("duration_seconds", 1.0))

                    raw_items.append({
                        "idx": idx,
                        "segment_order": seg_order,
                        "segment_id": seg_id,
                        "audio_path": audio_path,
                        "start_time": start_time,
                        "end_time": end_time,
                        "orig_duration": orig_dur,
                        "raw_duration": raw_dur,
                        "khmer_text": seg.get("text", "") or "",
                    })

                scheduler = TimelineScheduler(
                    max_tempo=active_max_tempo,
                    safety_margin_seconds=self.safety_margin_seconds,
                )
                scheduled_groups = scheduler.schedule_timeline(
                    raw_items,
                    target_duration=target_duration,
                    max_tempo=active_max_tempo,
                    fill_mode=fill_mode,
                )

                for g in scheduled_groups:
                    for p in g.pieces:
                        if p.status == "needs_optimization" and p.overflow_seconds > 0.05:
                            est_words = max(1, math.ceil(p.overflow_seconds / 0.35))
                            action = (
                                f"Shorten Segment #{p.segment_order} by approximately "
                                f"{est_words} word(s) (~{p.overflow_seconds:.1f}s), regenerate audio, or switch to Narration Mode."
                            )
                            conflicts.append(
                                TimingConflict(
                                    segment_order=p.segment_order,
                                    transcript_segment_id=p.segment_id,
                                    start_time=p.start_time,
                                    end_time=p.end_time,
                                    original_duration=p.orig_duration,
                                    khmer_duration=p.raw_duration,
                                    available_window=p.available_window,
                                    effective_window=p.effective_window,
                                    safety_margin_seconds=round(self.safety_margin_seconds, 3),
                                    required_tempo=p.required_tempo,
                                    max_tempo_factor=active_max_tempo,
                                    tempo_factor=p.applied_tempo,
                                    overflow_seconds=p.overflow_seconds,
                                    suggested_action=action,
                                    message=(
                                        f"Segment #{p.segment_order} ({p.raw_duration:.1f}s) "
                                        f"exceeds available window ({p.available_window:.2f}s) by {p.overflow_seconds:.1f}s even at {p.applied_tempo}x speed. {action}"
                                    ),
                                )
                            )

                if strict_validation and conflicts:
                    raise TimingConflictError(conflicts=conflicts)

                # Render pieces and collect offsets
                for g in scheduled_groups:
                    for s_idx, piece in enumerate(g.pieces):
                        desired_start = max(piece.allocated_start, 0.0)

                        piece_path = work_dir / f"piece_{piece.idx}_order_{piece.segment_order}.wav"
                        if piece.processed_audio_path:
                            piece_path = piece.processed_audio_path
                        elif piece.has_boundary_trim:
                            self.render_speech_piece(
                                piece.audio_path,
                                piece_path,
                                tempo_factor=piece.applied_tempo,
                                apply_micro_fade=True,
                                trim_start=piece.trim_start,
                                trim_end=piece.trim_end,
                            )
                        else:
                            self.render_speech_piece(
                                piece.audio_path,
                                piece_path,
                                tempo_factor=piece.applied_tempo,
                                apply_micro_fade=True,
                            )
                        piece_dur = self.video_processor.get_audio_duration(piece_path)
                        logger.info(
                            "[DubbingTimedSync:V2] Segment #%d: slot=%.2fs, raw_dur=%.2fs, tempo=%.2fx, final_dur=%.2fs, start=%.2fs, fill_mode=%s",
                            piece.segment_order,
                            piece.orig_duration,
                            piece.raw_duration,
                            piece.applied_tempo,
                            piece_dur,
                            desired_start,
                            fill_mode,
                        )
                        pieces_with_timing.append((piece_path, desired_start))

            else:
                # First pass: analyze windows, tempo, and detect overflows
                analyzed_segments: List[dict] = []
                for idx, seg in enumerate(sorted_items):
                    start_time = max(0.0, float(seg.get("start_time", 0.0)))
                    end_time = max(start_time, float(seg.get("end_time", start_time + 1.0)))
                    orig_dur = max(0.1, end_time - start_time)
                    seg_order = int(seg.get("segment_order", idx + 1))
                    seg_id = str(seg.get("segment_id", seg_order))

                    if idx < total_segments - 1:
                        next_start = float(sorted_items[idx + 1].get("start_time", 0.0))
                        if next_start > start_time:
                            avail_window = min(next_start - start_time, target_duration - start_time)
                        else:
                            avail_window = max(0.1, min(orig_dur, target_duration - start_time))
                    else:
                        avail_window = max(0.1, target_duration - start_time)

                    avail_window = max(0.1, avail_window)
                    audio_path = Path(seg["audio_path"])
                    if not audio_path.exists() or audio_path.stat().st_size == 0:
                        raise FileNotFoundError(f"Segment audio file missing at {audio_path}")

                    if trim_silence:
                        trimmed_src = work_dir / f"trimmed_timed_{idx}.wav"
                        self.trim_audio_silence(audio_path, trimmed_src)
                        source_for_piece = trimmed_src
                        raw_dur = self.video_processor.get_audio_duration(trimmed_src)
                    else:
                        source_for_piece = audio_path
                        raw_dur = self.video_processor.get_audio_duration(audio_path)

                    if raw_dur <= 0.0:
                        raw_dur = float(seg.get("duration_seconds", 1.0))

                    tempo = 1.0
                    required_tempo = 1.0

                    if raw_dur <= orig_dur:
                        if fill_mode == "stretch" and orig_dur > 0.2:
                            tempo = max(0.50, min(1.0, round(raw_dur / orig_dur, 2)))
                        else:
                            tempo = 1.0
                        required_tempo = 1.0
                    elif raw_dur <= avail_window:
                        pause_left = avail_window - raw_dur
                        if pause_left < 0.2 and (raw_dur / orig_dur) > 1.1:
                            target_dur = max(orig_dur, avail_window - 0.2)
                            tempo = min(active_max_tempo, max(1.0, round(raw_dur / target_dur, 2)))
                        else:
                            tempo = 1.0
                        required_tempo = 1.0
                    else:
                        effective_window = max(0.05, round(avail_window - self.safety_margin_seconds, 3))
                        required_tempo = round(raw_dur / effective_window, 2)
                        if required_tempo <= active_max_tempo:
                            tempo = required_tempo
                        else:
                            tempo = active_max_tempo
                            adjusted_est = raw_dur / tempo
                            overflow = round(adjusted_est - effective_window, 2)
                            if overflow > 0.05:
                                est_words = max(1, math.ceil(overflow / 0.35))
                                action = (
                                    f"Shorten Segment #{seg_order} by approximately "
                                    f"{est_words} word(s) (~{overflow:.1f}s), regenerate audio, or switch to Narration Mode."
                                )
                                conflicts.append(
                                    TimingConflict(
                                        segment_order=seg_order,
                                        transcript_segment_id=seg_id,
                                        start_time=round(start_time, 2),
                                        end_time=round(end_time, 2),
                                        original_duration=round(orig_dur, 2),
                                        khmer_duration=round(raw_dur, 2),
                                        available_window=round(avail_window, 2),
                                        effective_window=round(effective_window, 2),
                                        safety_margin_seconds=round(self.safety_margin_seconds, 3),
                                        required_tempo=required_tempo,
                                        max_tempo_factor=active_max_tempo,
                                        tempo_factor=tempo,
                                        overflow_seconds=overflow,
                                        suggested_action=action,
                                        message=(
                                            f"Segment #{seg_order} ({raw_dur:.1f}s) exceeds available window "
                                            f"({avail_window:.2f}s raw, {effective_window:.2f}s effective) "
                                            f"by {overflow:.1f}s even at {tempo}x speed. {action}"
                                        ),
                                    )
                                )

                    analyzed_segments.append({
                        "idx": idx,
                        "seg_order": seg_order,
                        "audio_path": source_for_piece,
                        "start_time": start_time,
                        "orig_dur": orig_dur,
                        "raw_dur": raw_dur,
                        "tempo": tempo,
                    })

                if strict_validation and conflicts:
                    raise TimingConflictError(conflicts=conflicts)

                # Second pass: render pieces and collect offsets
                for item in analyzed_segments:
                    idx = item["idx"]
                    seg_order = item["seg_order"]
                    audio_path = item["audio_path"]
                    start_time = item["start_time"]
                    orig_dur = item["orig_dur"]
                    raw_dur = item["raw_dur"]
                    tempo = item["tempo"]

                    piece_path = work_dir / f"piece_{idx}_order_{seg_order}.wav"
                    if abs(tempo - 1.0) > 0.02:
                        self.adjust_tempo(audio_path, piece_path, tempo)
                    else:
                        self.convert_to_standard_wav(audio_path, piece_path)

                    piece_dur = self.video_processor.get_audio_duration(piece_path)
                    if piece_dur <= 0.0:
                        piece_dur = raw_dur / tempo

                    logger.info(
                        "[DubbingTimedSync:Legacy] Segment #%d: slot=%.2fs, raw_dur=%.2fs, tempo=%.2fx, final_dur=%.2fs, start=%.2fs, fill_mode=%s",
                        seg_order,
                        orig_dur,
                        raw_dur,
                        tempo,
                        piece_dur,
                        start_time,
                        fill_mode,
                    )
                    pieces_with_timing.append((piece_path, start_time))

            # Assemble master timeline WAV using sample-accurate PCM buffer
            final_duration = self.assemble_timeline_pcm(
                pieces_with_timing=pieces_with_timing,
                target_duration=target_duration,
                output_path=output_timeline_path,
                overflow_policy=overflow_policy,
            )

            if strict_validation and target_duration > 0 and (final_duration > target_duration + 0.150):
                overflow_amount = final_duration - target_duration
                logger.warning(
                    "Synchronized Khmer audio timeline (%.3fs) exceeds target duration (%.3fs) by %.3fs.",
                    final_duration,
                    target_duration,
                    overflow_amount,
                )
                if not conflicts:
                    conflicts.append(
                        TimingConflict(
                            segment_order=total_segments,
                            transcript_segment_id="",
                            start_time=0.0,
                            end_time=target_duration,
                            original_duration=target_duration,
                            khmer_duration=final_duration,
                            available_window=target_duration,
                            effective_window=target_duration,
                            safety_margin_seconds=round(self.safety_margin_seconds, 3),
                            required_tempo=active_max_tempo,
                            max_tempo_factor=active_max_tempo,
                            tempo_factor=active_max_tempo,
                            overflow_seconds=round(overflow_amount, 2),
                            suggested_action="Shorten segments to fit within duration.",
                            message=f"Audio timeline exceeds duration by {overflow_amount:.2f}s.",
                        )
                    )
                raise TimingConflictError(conflicts=conflicts)

            return SynchronizationResult(
                timeline_path=output_timeline_path,
                total_duration_seconds=round(final_duration, 2),
                conflicts=conflicts,
                segments_count=total_segments,
            )

        finally:
            try:
                for f in work_dir.glob("*"):
                    try:
                        f.unlink()
                    except OSError:
                        pass
                work_dir.rmdir()
            except OSError as e:
                logger.warning("Could not completely remove timed sync work directory %s: %s", work_dir, e)
