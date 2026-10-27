import logging
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional

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
        dur = max(0.01, round(duration_seconds, 3))

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r={self.sample_rate}:cl=stereo",
            "-t", f"{dur:.3f}",
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
            "-af", "silenceremove=start_periods=1:start_duration=0.03:start_threshold=-40dB:detection=peak,areverse,silenceremove=start_periods=1:start_duration=0.03:start_threshold=-40dB:detection=peak,areverse",
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
    ) -> Path:
        """Render a speech piece with pitch-preserving tempo adjustment and
        boundary micro-fades (8ms) to guarantee zero clicks and intact phonemes.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tempo = max(0.5, min(2.0, float(tempo_factor)))
        has_tempo = abs(tempo - 1.0) > 0.01

        filters = []
        if has_tempo:
            filters.append(f"atempo={tempo:.3f}")
        if apply_micro_fade:
            # 8ms smooth cosine/linear micro-fade at head and tail
            filters.append("afade=t=in:ss=0:d=0.008,areverse,afade=t=in:ss=0:d=0.008,areverse")

        cmd = [self.ffmpeg_bin, "-y", "-i", str(input_audio)]
        if filters:
            cmd.extend(["-af", ",".join(filters)])
        cmd.extend([
            "-acodec", "pcm_s16le",
            "-ar", str(self.sample_rate),
            "-ac", str(self.channels),
            str(output_path),
        ])

        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg failed to render speech piece {input_audio}: {res.stderr}")
        return output_path

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
    ) -> SynchronizationResult:
        """Align speech segments onto a unified timeline WAV matching target video duration."""
        if not segment_items:
            raise ValueError("No speech segments provided for synchronization.")

        active_max_tempo = float(max_tempo_factor) if max_tempo_factor is not None else self.max_tempo_factor
        output_timeline_path.parent.mkdir(parents=True, exist_ok=True)
        work_dir = output_timeline_path.parent / f"sync_tmp_{project_id}"
        work_dir.mkdir(parents=True, exist_ok=True)

        # Sort items by transcript start time
        sorted_items = sorted(segment_items, key=lambda x: (x[0].start_time, x[0].segment_order))
        total_segments = len(sorted_items)

        timeline_pieces: List[Path] = []
        conflicts: List[TimingConflict] = []
        current_time = 0.0

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
                    })

                scheduler = TimelineScheduler(
                    max_tempo=active_max_tempo,
                    safety_margin_seconds=self.safety_margin_seconds,
                )
                scheduled_groups = scheduler.schedule_timeline(
                    raw_items,
                    target_duration=target_duration,
                    max_tempo=active_max_tempo,
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

                # Second pass: render pieces with micro-fades and construct timeline
                current_time = 0.0
                for g in scheduled_groups:
                    for s_idx, piece in enumerate(g.pieces):
                        # Anchor desired start time cleanly without overlap
                        desired_start = max(
                            piece.start_time,
                            current_time if s_idx == 0 else (current_time + self.min_pause_seconds)
                        )
                        if desired_start > current_time:
                            gap_dur = desired_start - current_time
                            gap_path = work_dir / f"gap_{piece.idx}.wav"
                            self.generate_silence(gap_dur, gap_path)
                            timeline_pieces.append(gap_path)
                            current_time = desired_start

                        piece_path = work_dir / f"piece_{piece.idx}_order_{piece.segment_order}.wav"
                        self.render_speech_piece(
                            piece.audio_path,
                            piece_path,
                            tempo_factor=piece.applied_tempo,
                            apply_micro_fade=True,
                        )
                        piece_dur = self.video_processor.get_audio_duration(piece_path)
                        timeline_pieces.append(piece_path)
                        current_time += piece_dur

                # Trailing silence
                if target_duration > current_time:
                    tail_dur = target_duration - current_time
                    tail_path = work_dir / "gap_tail.wav"
                    self.generate_silence(tail_dur, tail_path)
                    timeline_pieces.append(tail_path)
                    current_time = target_duration

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
                        "raw_dur": raw_dur,
                        "tempo": tempo,
                    })

                # In strict validation mode, halt immediately if there are conflicts to avoid
                # generating an invalid or truncated export.
                if strict_validation and conflicts:
                    logger.warning(
                        "Strict duration validation blocked export: %d timing conflict(s) detected.",
                        len(conflicts),
                    )
                    raise TimingConflictError(conflicts=conflicts)

                # 2. Second pass: render pieces and construct timeline
                for item in analyzed_segments:
                    idx = item["idx"]
                    t_seg = item["t_seg"]
                    audio_path = item["audio_path"]
                    start_time = item["start_time"]
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

                    # Insert silence gap before speech if needed
                    if start_time > current_time:
                        gap_dur = start_time - current_time
                        gap_path = work_dir / f"gap_{idx}.wav"
                        self.generate_silence(gap_dur, gap_path)
                        timeline_pieces.append(gap_path)
                        current_time = start_time
                    elif start_time < current_time:
                        logger.warning(
                            "Segment #%d start (%.2fs) precedes current timeline (%.2fs); appending without truncation.",
                            t_seg.segment_order,
                            start_time,
                            current_time,
                        )

                    # Append speech segment (never truncated)
                    timeline_pieces.append(piece_path)
                    current_time += piece_dur

                # Trailing silence to cover video target duration
                if target_duration > current_time:
                    tail_dur = target_duration - current_time
                    tail_path = work_dir / "gap_tail.wav"
                    self.generate_silence(tail_dur, tail_path)
                    timeline_pieces.append(tail_path)
                    current_time = target_duration

            # Concatenate all timeline pieces using FFmpeg concat demuxer
            concat_manifest = work_dir / "concat_list.txt"
            with open(concat_manifest, "w", encoding="utf-8") as f:
                for piece in timeline_pieces:
                    f.write(f"file '{piece.absolute()}'\n")

            cmd = [
                self.ffmpeg_bin,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_manifest),
                "-c", "copy",
                str(output_timeline_path),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg concat failed: {res.stderr}")

            # Verify and probe output duration
            final_duration = self.video_processor.get_audio_duration(output_timeline_path)
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
    ) -> SynchronizationResult:
        """Align arbitrary timed audio segments onto a timeline WAV matching target timestamps.
        Applies up to max_tempo_factor tempo adjustment without silent truncation,
        inserts precise silence gaps, detects timing overflows, and generates a unified timeline.
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

        timeline_pieces: List[Path] = []
        conflicts: List[TimingConflict] = []
        current_time = 0.0

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

                # Render pieces and construct timeline
                current_time = 0.0
                for g in scheduled_groups:
                    for s_idx, piece in enumerate(g.pieces):
                        desired_start = max(
                            piece.start_time,
                            current_time if s_idx == 0 else (current_time + self.min_pause_seconds)
                        )
                        if desired_start > current_time:
                            gap_dur = desired_start - current_time
                            gap_path = work_dir / f"gap_{piece.idx}.wav"
                            self.generate_silence(gap_dur, gap_path)
                            timeline_pieces.append(gap_path)
                            current_time = desired_start

                        piece_path = work_dir / f"piece_{piece.idx}_order_{piece.segment_order}.wav"
                        self.render_speech_piece(
                            piece.audio_path,
                            piece_path,
                            tempo_factor=piece.applied_tempo,
                            apply_micro_fade=True,
                        )
                        piece_dur = self.video_processor.get_audio_duration(piece_path)
                        timeline_pieces.append(piece_path)
                        current_time += piece_dur

                if target_duration > current_time:
                    tail_dur = target_duration - current_time
                    tail_path = work_dir / "gap_tail.wav"
                    self.generate_silence(tail_dur, tail_path)
                    timeline_pieces.append(tail_path)
                    current_time = target_duration

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
                        "raw_dur": raw_dur,
                        "tempo": tempo,
                    })

                if strict_validation and conflicts:
                    raise TimingConflictError(conflicts=conflicts)

                # Second pass: render pieces and construct timeline
                for item in analyzed_segments:
                    idx = item["idx"]
                    seg_order = item["seg_order"]
                    audio_path = item["audio_path"]
                    start_time = item["start_time"]
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

                    # Silence gap before speech if needed
                    if start_time > current_time:
                        gap_dur = start_time - current_time
                        gap_path = work_dir / f"gap_{idx}.wav"
                        self.generate_silence(gap_dur, gap_path)
                        timeline_pieces.append(gap_path)
                        current_time = start_time
                    elif start_time < current_time:
                        logger.warning(
                            "Segment #%d start (%.2fs) precedes current timeline (%.2fs); appending without truncation.",
                            seg_order,
                            start_time,
                            current_time,
                        )

                    timeline_pieces.append(piece_path)
                    current_time += piece_dur

                # Trailing silence if target_duration > current_time
                if target_duration > current_time:
                    tail_dur = target_duration - current_time
                    tail_path = work_dir / "gap_tail.wav"
                    self.generate_silence(tail_dur, tail_path)
                    timeline_pieces.append(tail_path)
                    current_time = target_duration

            # Concat demuxer
            concat_manifest = work_dir / "concat_list.txt"
            with open(concat_manifest, "w", encoding="utf-8") as f:
                for piece in timeline_pieces:
                    f.write(f"file '{piece.absolute()}'\n")

            cmd = [
                self.ffmpeg_bin,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_manifest),
                "-c", "copy",
                str(output_timeline_path),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg concat failed: {res.stderr}")

            final_duration = self.video_processor.get_audio_duration(output_timeline_path)
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
