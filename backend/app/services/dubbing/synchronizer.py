import logging
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional

from app.core.storage import resolve_audio_file
from app.models.project import TranscriptSegment, TranslationSegment, GeneratedAudio
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
        sample_rate: int = 44100,
        channels: int = 2,
        ffmpeg_bin: str = "ffmpeg",
        video_processor: Optional[FFmpegVideoProcessor] = None,
    ):
        self.max_tempo_factor = max_tempo_factor
        self.safety_margin_seconds = max(0.0, float(safety_margin_seconds))
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
            if pipeline_version == "v2.1":
                # --- V2.1: Phrase-Group Scheduling with Non-Destructive Audio & Micro-Fades ---
                phrase_groups: List[List[dict]] = []
                curr_group: List[dict] = []
                max_group_gap = 1.5  # sentences within 1.5s share timing flexibility

                for idx, (t_seg, trans_seg, audio_rec) in enumerate(sorted_items):
                    start_time = max(0.0, float(t_seg.start_time))
                    end_time = max(start_time, float(t_seg.end_time))
                    orig_dur = max(0.1, end_time - start_time)

                    audio_path = resolve_audio_file(project_id, trans_seg.id, audio_rec.audio_path)
                    if not audio_path.exists() or audio_path.stat().st_size == 0:
                        raise FileNotFoundError(
                            f"Generated audio file missing for segment {t_seg.segment_order} at {audio_path}"
                        )

                    raw_dur = self.video_processor.get_audio_duration(audio_path)
                    if raw_dur <= 0.0:
                        raw_dur = float(audio_rec.duration_seconds or 1.0)

                    seg_info = {
                        "idx": idx,
                        "t_seg": t_seg,
                        "trans_seg": trans_seg,
                        "audio_rec": audio_rec,
                        "audio_path": audio_path,
                        "start_time": start_time,
                        "end_time": end_time,
                        "orig_dur": orig_dur,
                        "raw_dur": raw_dur,
                    }

                    if not curr_group:
                        curr_group.append(seg_info)
                    else:
                        prev_end = curr_group[-1]["end_time"]
                        if (start_time - prev_end) <= max_group_gap:
                            curr_group.append(seg_info)
                        else:
                            phrase_groups.append(curr_group)
                            curr_group = [seg_info]

                if curr_group:
                    phrase_groups.append(curr_group)

                analyzed_groups: List[dict] = []
                for g_idx, g_items in enumerate(phrase_groups):
                    g_start = g_items[0]["start_time"]
                    if g_idx < len(phrase_groups) - 1:
                        next_g_start = float(phrase_groups[g_idx + 1][0]["start_time"])
                        g_limit = min(next_g_start, target_duration)
                    else:
                        g_limit = target_duration

                    g_avail_window = max(0.1, g_limit - g_start)
                    k = len(g_items)
                    sum_raw = sum(s["raw_dur"] for s in g_items)
                    p_min = 0.12  # 120ms natural breath pause between sentences
                    p_total = (k - 1) * p_min
                    avail_speech = max(0.05, g_avail_window - p_total - self.safety_margin_seconds)
                    req_tempo = round(sum_raw / avail_speech, 3)

                    if (sum_raw + p_total) <= g_avail_window:
                        group_tempo = 1.0
                    elif req_tempo <= active_max_tempo:
                        group_tempo = round(req_tempo, 2)
                    else:
                        group_tempo = active_max_tempo
                        overflow = round((sum_raw / active_max_tempo) - avail_speech, 2)
                        if overflow > 0.05:
                            overflowing_segs = [s for s in g_items if (s["raw_dur"] / max(0.05, s["orig_dur"])) > active_max_tempo]
                            if not overflowing_segs:
                                overflowing_segs = [max(g_items, key=lambda s: s["raw_dur"] / max(0.1, s["orig_dur"]))]
                            for seg_c in overflowing_segs:
                                seg_overflow = round((seg_c["raw_dur"] / active_max_tempo) - max(0.05, seg_c["orig_dur"]), 2)
                                if seg_overflow <= 0.05:
                                    seg_overflow = overflow
                                est_words = max(1, math.ceil(seg_overflow / 0.35))
                                action = (
                                    f"Shorten the Khmer translation for Segment #{seg_c['t_seg'].segment_order} by approximately "
                                    f"{est_words} word(s) (~{seg_overflow:.1f}s), regenerate audio, and retry export."
                                )
                                conflicts.append(
                                    TimingConflict(
                                        segment_order=seg_c["t_seg"].segment_order,
                                        transcript_segment_id=seg_c["t_seg"].id,
                                        start_time=round(seg_c["start_time"], 2),
                                        end_time=round(seg_c["end_time"], 2),
                                        original_duration=round(seg_c["orig_dur"], 2),
                                        khmer_duration=round(seg_c["raw_dur"], 2),
                                        available_window=round(g_avail_window, 2),
                                        effective_window=round(avail_speech, 2),
                                        safety_margin_seconds=round(self.safety_margin_seconds, 3),
                                        required_tempo=round(req_tempo, 2),
                                        max_tempo_factor=active_max_tempo,
                                        tempo_factor=group_tempo,
                                        overflow_seconds=seg_overflow,
                                        suggested_action=action,
                                        message=(
                                            f"Phrase group starting at Segment #{g_items[0]['t_seg'].segment_order} ({sum_raw:.1f}s) "
                                            f"exceeds available window ({g_avail_window:.2f}s) by {seg_overflow:.1f}s even at {group_tempo}x speed. "
                                            f"{action}"
                                        ),
                                    )
                                )

                    analyzed_groups.append({
                        "items": g_items,
                        "tempo": group_tempo,
                        "p_min": p_min,
                    })

                if strict_validation and conflicts:
                    logger.warning(
                        "Strict duration validation blocked export: %d timing conflict(s) detected.",
                        len(conflicts),
                    )
                    raise TimingConflictError(conflicts=conflicts)

                # Second pass: render pieces with micro-fades and construct timeline
                current_time = 0.0
                for g_data in analyzed_groups:
                    g_items = g_data["items"]
                    tempo = g_data["tempo"]
                    p_min = g_data["p_min"]

                    for s_idx, item in enumerate(g_items):
                        desired_start = max(item["start_time"], current_time if s_idx == 0 else (current_time + p_min))
                        if desired_start > current_time:
                            gap_dur = desired_start - current_time
                            gap_path = work_dir / f"gap_{item['idx']}.wav"
                            self.generate_silence(gap_dur, gap_path)
                            timeline_pieces.append(gap_path)
                            current_time = desired_start

                        piece_path = work_dir / f"piece_{item['idx']}_order_{item['t_seg'].segment_order}.wav"
                        self.render_speech_piece(item["audio_path"], piece_path, tempo_factor=tempo, apply_micro_fade=True)
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
            if pipeline_version == "v2.1":
                # --- V2.1 Phrase-Group Scheduling for Timed Segments ---
                phrase_groups: List[List[dict]] = []
                curr_group: List[dict] = []
                max_group_gap = 1.5

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

                    seg_info = {
                        "idx": idx,
                        "seg_order": seg_order,
                        "seg_id": seg_id,
                        "audio_path": audio_path,
                        "start_time": start_time,
                        "end_time": end_time,
                        "orig_dur": orig_dur,
                        "raw_dur": raw_dur,
                    }

                    if not curr_group:
                        curr_group.append(seg_info)
                    else:
                        prev_end = curr_group[-1]["end_time"]
                        if (start_time - prev_end) <= max_group_gap:
                            curr_group.append(seg_info)
                        else:
                            phrase_groups.append(curr_group)
                            curr_group = [seg_info]

                if curr_group:
                    phrase_groups.append(curr_group)

                analyzed_groups: List[dict] = []
                for g_idx, g_items in enumerate(phrase_groups):
                    g_start = g_items[0]["start_time"]
                    if g_idx < len(phrase_groups) - 1:
                        next_g_start = float(phrase_groups[g_idx + 1][0]["start_time"])
                        g_limit = min(next_g_start, target_duration)
                    else:
                        g_limit = target_duration

                    g_avail_window = max(0.1, g_limit - g_start)
                    k = len(g_items)
                    sum_raw = sum(s["raw_dur"] for s in g_items)
                    p_min = 0.12  # 120ms natural breath pause between sentences
                    p_total = (k - 1) * p_min
                    avail_speech = max(0.05, g_avail_window - p_total - self.safety_margin_seconds)
                    req_tempo = round(sum_raw / avail_speech, 3)

                    if (sum_raw + p_total) <= g_avail_window:
                        group_tempo = 1.0
                    elif req_tempo <= active_max_tempo:
                        group_tempo = round(req_tempo, 2)
                    else:
                        group_tempo = active_max_tempo
                        overflow = round((sum_raw / active_max_tempo) - avail_speech, 2)
                        if overflow > 0.05:
                            overflowing_segs = [s for s in g_items if (s["raw_dur"] / max(0.05, s["orig_dur"])) > active_max_tempo]
                            if not overflowing_segs:
                                overflowing_segs = [max(g_items, key=lambda s: s["raw_dur"] / max(0.1, s["orig_dur"]))]
                            for seg_c in overflowing_segs:
                                seg_overflow = round((seg_c["raw_dur"] / active_max_tempo) - max(0.05, seg_c["orig_dur"]), 2)
                                if seg_overflow <= 0.05:
                                    seg_overflow = overflow
                                est_words = max(1, math.ceil(seg_overflow / 0.35))
                                action = (
                                    f"Shorten Segment #{seg_c['seg_order']} by approximately "
                                    f"{est_words} word(s) (~{seg_overflow:.1f}s), regenerate audio, or switch to Narration Mode."
                                )
                                conflicts.append(
                                    TimingConflict(
                                        segment_order=seg_c["seg_order"],
                                        transcript_segment_id=seg_c["seg_id"],
                                        start_time=round(seg_c["start_time"], 2),
                                        end_time=round(seg_c["end_time"], 2),
                                        original_duration=round(seg_c["orig_dur"], 2),
                                        khmer_duration=round(seg_c["raw_dur"], 2),
                                        available_window=round(g_avail_window, 2),
                                        effective_window=round(avail_speech, 2),
                                        safety_margin_seconds=round(self.safety_margin_seconds, 3),
                                        required_tempo=round(req_tempo, 2),
                                        max_tempo_factor=active_max_tempo,
                                        tempo_factor=group_tempo,
                                        overflow_seconds=seg_overflow,
                                        suggested_action=action,
                                        message=(
                                            f"Phrase group starting at Segment #{g_items[0]['seg_order']} ({sum_raw:.1f}s) "
                                            f"exceeds available window ({g_avail_window:.2f}s) by {seg_overflow:.1f}s even at {group_tempo}x speed. {action}"
                                        ),
                                    )
                                )

                    analyzed_groups.append({
                        "items": g_items,
                        "tempo": group_tempo,
                        "p_min": p_min,
                    })

                if strict_validation and conflicts:
                    raise TimingConflictError(conflicts=conflicts)

                # Render pieces and construct timeline
                current_time = 0.0
                for g_data in analyzed_groups:
                    g_items = g_data["items"]
                    tempo = g_data["tempo"]
                    p_min = g_data["p_min"]

                    for s_idx, item in enumerate(g_items):
                        desired_start = max(item["start_time"], current_time if s_idx == 0 else (current_time + p_min))
                        if desired_start > current_time:
                            gap_dur = desired_start - current_time
                            gap_path = work_dir / f"gap_{item['idx']}.wav"
                            self.generate_silence(gap_dur, gap_path)
                            timeline_pieces.append(gap_path)
                            current_time = desired_start

                        piece_path = work_dir / f"piece_{item['idx']}_order_{item['seg_order']}.wav"
                        self.render_speech_piece(item["audio_path"], piece_path, tempo_factor=tempo, apply_micro_fade=True)
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
