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
        sample_rate: int = 44100,
        channels: int = 2,
        ffmpeg_bin: str = "ffmpeg",
        video_processor: Optional[FFmpegVideoProcessor] = None,
    ):
        self.max_tempo_factor = max_tempo_factor
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

    def synchronize(
        self,
        project_id: str,
        segment_items: List[Tuple[TranscriptSegment, TranslationSegment, GeneratedAudio]],
        target_duration: float,
        output_timeline_path: Path,
        strict_validation: bool = True,
    ) -> SynchronizationResult:
        """Align speech segments onto a unified timeline WAV matching target video duration."""
        if not segment_items:
            raise ValueError("No speech segments provided for synchronization.")

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
            # 1. First pass: analyze timing windows and detect any unresolved conflicts
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
                        tempo = min(self.max_tempo_factor, max(1.0, round(raw_dur / target_dur, 2)))
                    else:
                        tempo = 1.0
                    required_tempo = 1.0
                else:
                    # raw_dur > avail_window: exceeds available interval
                    effective_window = max(0.1, avail_window - 0.05)
                    required_tempo = round(raw_dur / effective_window, 2)

                    if required_tempo <= self.max_tempo_factor:
                        tempo = required_tempo
                    else:
                        tempo = self.max_tempo_factor
                        adjusted_est = raw_dur / tempo
                        overflow = round(adjusted_est - avail_window, 2)
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
                                    required_tempo=required_tempo,
                                    max_tempo_factor=self.max_tempo_factor,
                                    tempo_factor=tempo,
                                    overflow_seconds=overflow,
                                    suggested_action=action,
                                    message=(
                                        f"Segment #{t_seg.segment_order} ({raw_dur:.1f}s) exceeds available window "
                                        f"({avail_window:.1f}s) by {overflow:.1f}s even at {tempo}x speed. "
                                        f"{action}"
                                    ),
                                )
                            )

                analyzed_segments.append({
                    "idx": idx,
                    "t_seg": t_seg,
                    "trans_seg": trans_seg,
                    "audio_rec": audio_rec,
                    "audio_path": audio_path,
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
