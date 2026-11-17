import logging
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SpeechInspectionResult:
    """Detailed completeness and quality assessment of synthesized speech audio."""
    audio_path: str
    duration_seconds: float
    file_size_bytes: int
    is_decodable: bool
    is_silent: bool
    has_abrupt_cutoff: bool
    char_count: int
    chars_per_second: float
    completeness_status: str  # "plausibly_complete", "requires_review", "invalid"
    lexical_status: str  # Always "unverified_human_listening_required" for automated checks
    warning_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audio_path": self.audio_path,
            "duration_seconds": round(self.duration_seconds, 3),
            "file_size_bytes": self.file_size_bytes,
            "is_decodable": self.is_decodable,
            "is_silent": self.is_silent,
            "has_abrupt_cutoff": self.has_abrupt_cutoff,
            "char_count": self.char_count,
            "chars_per_second": round(self.chars_per_second, 2),
            "completeness_status": self.completeness_status,
            "lexical_status": self.lexical_status,
            "warning_message": self.warning_message,
        }


@dataclass
class SafeSilenceBoundary:
    """Conservative boundary trimming bounds that preserve soft consonants and phonemes."""
    raw_duration: float
    trim_start: float
    trim_end: float
    trimmed_duration: float
    leading_padding_seconds: float
    trailing_padding_seconds: float
    safety_margin_seconds: float

    @property
    def has_trimming(self) -> bool:
        return (self.raw_duration - self.trimmed_duration) > 0.03


class SpeechGuardService:
    """Quality-first audio DSP service providing conservative speech boundary trimming
    and non-destructive speech completeness verification for KhmerDub AI.
    """

    _boundary_cache: Dict[Tuple[str, int, float, float, float, float], SafeSilenceBoundary] = {}
    _inspection_cache: Dict[Tuple[str, int, float, str], SpeechInspectionResult] = {}

    def __init__(
        self,
        ffmpeg_bin: str = "ffmpeg",
        ffprobe_bin: str = "ffprobe",
        noise_threshold_db: float = -48.0,
        min_silence_dur: float = 0.06,
        safety_margin_seconds: float = 0.06,
    ):
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin
        self.noise_threshold_db = noise_threshold_db
        self.min_silence_dur = min_silence_dur
        self.safety_margin_seconds = max(0.03, float(safety_margin_seconds))

    def inspect_speech_audio(
        self,
        audio_path: Path,
        expected_text: str = "",
    ) -> SpeechInspectionResult:
        """Inspect synthesized audio for decodability, non-silence energy, abrupt EOF truncation,
        and speech rate plausibility. Never reports 100% lexical completeness without human listening.
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            return SpeechInspectionResult(
                audio_path=str(audio_path),
                duration_seconds=0.0,
                file_size_bytes=0,
                is_decodable=False,
                is_silent=True,
                has_abrupt_cutoff=False,
                char_count=len(expected_text),
                chars_per_second=0.0,
                completeness_status="invalid",
                lexical_status="unverified_human_listening_required",
                warning_message="Audio file does not exist on disk.",
            )

        try:
            st = audio_path.stat()
            file_size = st.st_size
            insp_key = (str(audio_path.resolve()), file_size, st.st_mtime, expected_text)
            if insp_key in self._inspection_cache:
                return self._inspection_cache[insp_key]
        except OSError:
            insp_key = None
            file_size = 0

        if file_size < 44:
            return SpeechInspectionResult(
                audio_path=str(audio_path),
                duration_seconds=0.0,
                file_size_bytes=file_size,
                is_decodable=False,
                is_silent=True,
                has_abrupt_cutoff=False,
                char_count=len(expected_text),
                chars_per_second=0.0,
                completeness_status="invalid",
                lexical_status="unverified_human_listening_required",
                warning_message="Audio file is empty or corrupted (under 44 bytes).",
            )

        # Probe duration and audio stream
        cmd_probe = [
            self.ffprobe_bin,
            "-v", "error",
            "-show_entries", "stream=codec_type,duration,sample_rate,channels:format=duration",
            "-of", "json",
            str(audio_path),
        ]
        res_probe = subprocess.run(cmd_probe, capture_output=True, text=True, check=False)
        if res_probe.returncode != 0:
            return SpeechInspectionResult(
                audio_path=str(audio_path),
                duration_seconds=0.0,
                file_size_bytes=file_size,
                is_decodable=False,
                is_silent=True,
                has_abrupt_cutoff=False,
                char_count=len(expected_text),
                chars_per_second=0.0,
                completeness_status="invalid",
                lexical_status="unverified_human_listening_required",
                warning_message=f"Audio probe failed: {res_probe.stderr.strip()}",
            )

        import json
        try:
            probe_data = json.loads(res_probe.stdout)
            format_info = probe_data.get("format", {})
            duration = float(format_info.get("duration", 0.0))
        except Exception:
            duration = 0.0

        if duration <= 0.0:
            return SpeechInspectionResult(
                audio_path=str(audio_path),
                duration_seconds=0.0,
                file_size_bytes=file_size,
                is_decodable=False,
                is_silent=True,
                has_abrupt_cutoff=False,
                char_count=len(expected_text),
                chars_per_second=0.0,
                completeness_status="invalid",
                lexical_status="unverified_human_listening_required",
                warning_message="Audio duration is zero or unreadable.",
            )

        # Audio energy analysis: check if file is completely silent or has clipping
        cmd_stats = [
            self.ffmpeg_bin,
            "-xerror",
            "-i", str(audio_path),
            "-af", "astats",
            "-f", "null", "-",
        ]
        res_stats = subprocess.run(cmd_stats, capture_output=True, text=True, check=False)
        
        # Check overall peak and RMS levels
        is_silent = False
        overall_text = ""
        if "Overall" in res_stats.stderr:
            overall_text = res_stats.stderr.split("Overall", 1)[1]

        m_rms = re.search(r"RMS level dB:\s*(-?inf|[-\d.]+)", overall_text)
        if m_rms:
            try:
                rms_val = float(m_rms.group(1))
                if rms_val <= -55.0:
                    is_silent = True
            except ValueError:
                pass

        # Abrupt cutoff detection: check amplitude in the trailing 40ms of speech
        has_abrupt_cutoff = False
        if duration > 0.20:
            cmd_tail = [
                self.ffmpeg_bin,
                "-i", str(audio_path),
                "-af", "areverse,atrim=start=0:end=0.04,astats",
                "-f", "null", "-",
            ]
            res_tail = subprocess.run(cmd_tail, capture_output=True, text=True, check=False)
            tail_overall = res_tail.stderr.split("Overall", 1)[1] if "Overall" in res_tail.stderr else res_tail.stderr
            m_tail_peak = re.search(r"Peak level dB:\s*([-\d.]+)", tail_overall)
            if m_tail_peak:
                try:
                    tail_peak = float(m_tail_peak.group(1))
                    # If peak level right at EOF is loud (>-10 dBFS), waveform terminates abruptly mid-syllable
                    if tail_peak > -10.0:
                        has_abrupt_cutoff = True
                except ValueError:
                    pass

        # Character rate plausibility check for Khmer
        clean_text = expected_text.strip()
        char_count = len(clean_text)
        chars_per_sec = (char_count / duration) if duration > 0 else 0.0

        completeness_status = "plausibly_complete"
        warnings = []

        decode_success = res_stats.returncode == 0
        if not decode_success or m_rms is None:
            completeness_status = "invalid"
            warnings.append("Audio could not be fully decoded or its energy could not be measured.")
        elif is_silent:
            completeness_status = "invalid"
            warnings.append("Audio is completely silent (RMS below -60dBFS).")
        elif has_abrupt_cutoff:
            completeness_status = "requires_review"
            warnings.append("Audio terminates abruptly at EOF (possible mid-phoneme cutoff).")
        elif char_count > 0:
            if chars_per_sec > 26.0 and char_count > 20:
                completeness_status = "requires_review"
                warnings.append(f"Speech rate suspiciously rapid ({chars_per_sec:.1f} chars/s > 26 chars/s).")
            elif chars_per_sec < 2.5 and char_count > 10 and duration > 5.0:
                completeness_status = "requires_review"
                warnings.append(f"Speech rate suspiciously sluggish ({chars_per_sec:.1f} chars/s < 2.5 chars/s).")

        result = SpeechInspectionResult(
            audio_path=str(audio_path),
            duration_seconds=duration,
            file_size_bytes=file_size,
            is_decodable=decode_success,
            is_silent=is_silent,
            has_abrupt_cutoff=has_abrupt_cutoff,
            char_count=char_count,
            chars_per_second=chars_per_sec,
            completeness_status=completeness_status,
            lexical_status="unverified_human_listening_required",
            warning_message="; ".join(warnings) if warnings else None,
        )
        if insp_key is not None:
            self._inspection_cache[insp_key] = result
        return result

    def detect_speech_boundaries(
        self,
        audio_path: Path,
        noise_threshold_db: Optional[float] = None,
        min_silence_dur: Optional[float] = None,
        safety_margin_seconds: Optional[float] = None,
    ) -> SafeSilenceBoundary:
        """Detect genuine non-speech silence padding at start and end of utterance.
        Strictly preserves internal sentence pauses and weak consonants by applying a
        speech-safe margin (default 60ms). Original audio files are never modified.
        """
        thresh = noise_threshold_db if noise_threshold_db is not None else self.noise_threshold_db
        min_d = min_silence_dur if min_silence_dur is not None else self.min_silence_dur
        margin = safety_margin_seconds if safety_margin_seconds is not None else self.safety_margin_seconds

        audio_path = Path(audio_path)
        if not audio_path.exists():
            return SafeSilenceBoundary(
                raw_duration=0.0,
                trim_start=0.0,
                trim_end=0.0,
                trimmed_duration=0.0,
                leading_padding_seconds=0.0,
                trailing_padding_seconds=0.0,
                safety_margin_seconds=margin,
            )

        try:
            st = audio_path.stat()
            cache_key = (str(audio_path.resolve()), st.st_size, st.st_mtime, thresh, min_d, margin)
            if cache_key in self._boundary_cache:
                return self._boundary_cache[cache_key]
        except OSError:
            cache_key = None

        # Probe total audio duration
        cmd_probe = [
            self.ffprobe_bin,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        res_probe = subprocess.run(cmd_probe, capture_output=True, text=True, check=False)
        try:
            total_dur = float(res_probe.stdout.strip())
        except (ValueError, TypeError):
            total_dur = 0.0

        if total_dur <= 0.1:
            return SafeSilenceBoundary(
                raw_duration=total_dur,
                trim_start=0.0,
                trim_end=total_dur,
                trimmed_duration=total_dur,
                leading_padding_seconds=0.0,
                trailing_padding_seconds=0.0,
                safety_margin_seconds=margin,
            )

        cmd = [
            self.ffmpeg_bin,
            "-i", str(audio_path),
            "-af", f"silencedetect=noise={thresh}dB:d={min_d}",
            "-f", "null", "-",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)

        silence_starts = []
        silence_ends = []
        for line in res.stderr.splitlines():
            if "silence_start:" in line:
                m = re.search(r"silence_start:\s*([0-9.]+)", line)
                if m:
                    silence_starts.append(float(m.group(1)))
            elif "silence_end:" in line:
                m = re.search(r"silence_end:\s*([0-9.]+)", line)
                if m:
                    silence_ends.append(float(m.group(1)))

        trim_start = 0.0
        trim_end = total_dur
        lead_pad = 0.0
        trail_pad = 0.0

        # Leading silence boundary: check if initial silence is at start of file
        if silence_starts and silence_starts[0] <= 0.04 and silence_ends:
            end_lead = silence_ends[0]
            if end_lead > margin:
                trim_start = max(0.0, end_lead - margin)
                lead_pad = round(end_lead, 3)

        # Trailing silence boundary: check if silence extends through the end of file
        if silence_starts:
            last_start = silence_starts[-1]
            if last_start < total_dur and (total_dur - last_start) >= min_d:
                # Silence extends to end if either last silence_end is at end or no trailing silence_end logged
                if not silence_ends or silence_ends[-1] >= (total_dur - 0.06) or len(silence_starts) > len(silence_ends):
                    if (total_dur - last_start) > margin:
                        trim_end = min(total_dur, last_start + margin)
                        trail_pad = round(total_dur - last_start, 3)

        # Discard microscopic adjustments under 30ms to avoid unnecessary sub-sample resampling
        if trim_start <= 0.03:
            trim_start = 0.0
            lead_pad = 0.0
        if trim_end >= (total_dur - 0.03):
            trim_end = total_dur
            trail_pad = 0.0

        # If detected silence covers entire audio or boundaries cross, do not apply trimming
        if (trim_end - trim_start) < 0.20 or (trim_start >= trim_end):
            trim_start = 0.0
            trim_end = total_dur
            lead_pad = 0.0
            trail_pad = 0.0

        trimmed_dur = max(0.1, round(trim_end - trim_start, 3))

        res = SafeSilenceBoundary(
            raw_duration=round(total_dur, 3),
            trim_start=round(trim_start, 3),
            trim_end=round(trim_end, 3),
            trimmed_duration=trimmed_dur,
            leading_padding_seconds=lead_pad,
            trailing_padding_seconds=trail_pad,
            safety_margin_seconds=margin,
        )
        if cache_key is not None:
            self._boundary_cache[cache_key] = res
        return res

    def render_safe_boundary_trimmed_audio(
        self,
        input_audio: Path,
        output_path: Path,
        boundary: SafeSilenceBoundary,
        sample_rate: int = 44100,
        channels: int = 2,
    ) -> Path:
        """Render non-destructive boundary-trimmed audio with 6ms micro-fades at boundaries
        to eliminate transient clicks. The original raw audio is never overwritten.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not boundary.has_trimming:
            # If no boundary silence to trim, simply standardize format
            cmd = [
                self.ffmpeg_bin,
                "-y",
                "-i", str(input_audio),
                "-acodec", "pcm_s16le",
                "-ar", str(sample_rate),
                "-ac", str(channels),
                str(output_path),
            ]
        else:
            micro_fade_d = 0.006  # 6ms micro-fade
            cmd = [
                self.ffmpeg_bin,
                "-y",
                "-ss", f"{boundary.trim_start:.3f}",
                "-to", f"{boundary.trim_end:.3f}",
                "-i", str(input_audio),
                "-filter_complex", (
                    f"[0:a]afade=t=in:ss=0:d={micro_fade_d:.3f},"
                    f"areverse,afade=t=in:ss=0:d={micro_fade_d:.3f},areverse[outa]"
                ),
                "-map", "[outa]",
                "-acodec", "pcm_s16le",
                "-ar", str(sample_rate),
                "-ac", str(channels),
                str(output_path),
            ]

        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            logger.warning("Safe boundary trim render failed (%s); falling back to direct copy", res.stderr.strip())
            # Fallback to direct standardization
            cmd_fallback = [
                self.ffmpeg_bin,
                "-y",
                "-i", str(input_audio),
                "-acodec", "pcm_s16le",
                "-ar", str(sample_rate),
                "-ac", str(channels),
                str(output_path),
            ]
            subprocess.run(cmd_fallback, capture_output=True, text=True, check=True)

        return output_path
