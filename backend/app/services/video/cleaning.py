"""Streaming, cancellable audio cleanup behind the existing video interface."""
import json
import math
import logging
import subprocess
import tempfile
import time
import os
import sys
from pathlib import Path
from typing import Callable

from app.services.video.ffmpeg import FFmpegVideoProcessor

PRESETS = {"light": 6, "balanced": 10, "strong": 16}
FORMATS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".mp4", ".mov", ".mkv", ".webm"}
logger = logging.getLogger(__name__)


class CleaningCancelled(Exception):
    pass


class CleaningError(Exception):
    pass


class AudioCleaningProcessor(FFmpegVideoProcessor):
    """No silence removal, gating, tempo change or pitch change is performed."""

    def probe(self, path: Path) -> dict:
        try:
            result = subprocess.run(
                [self.ffprobe_bin, "-v", "error", "-show_streams", "-show_format",
                 "-protocol_whitelist", "file,pipe", "-format_whitelist", "wav,mp3,mov,flac,ogg,matroska,webm", "-of", "json", str(path)], capture_output=True, text=True,
                timeout=30, check=True,
            )
            return json.loads(result.stdout)
        except (subprocess.SubprocessError, ValueError) as exc:
            raise CleaningError("The media is incomplete, corrupted or unsupported.") from exc

    def inspect(self, path: Path) -> dict:
        data = self.probe(path)
        audios = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
        videos = [s for s in data.get("streams", []) if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")]
        if not audios:
            raise CleaningError("This file has no audio stream to clean.")
        audio = audios[0]
        try:
            duration = float(audio.get("duration") or data.get("format", {}).get("duration", 0))
        except (TypeError, ValueError) as exc:
            raise CleaningError("The audio duration could not be measured.") from exc
        if not math.isfinite(duration) or not 0 < duration <= 21600:
            raise CleaningError("Audio duration must be measurable and no longer than six hours.")
        return {
            "input_duration": duration, "audio_stream_index": audio["index"],
            "audio_stream_count": len(audios), "stream_policy": "First audio stream in file order",
            "sample_rate": int(audio.get("sample_rate") or 48000),
            "channels": int(audio.get("channels") or 1), "has_video": bool(videos),
            "video_stream_index": videos[0]["index"] if videos else None,
            "video_duration": float(videos[0].get("duration") or data.get("format", {}).get("duration", duration)) if videos else None,
            "audio_start": float(audio.get("start_time") or 0),
            "video_start": float(videos[0].get("start_time") or 0) if videos else 0,
        }

    def run_pass(self, args: list[str], duration: float,
                 cancelled: Callable[[], bool], progress: Callable[[int], None]) -> None:
        """Bound stdout/stderr storage and terminate the child on cancellation."""
        with tempfile.TemporaryFile(mode="w+") as errors, tempfile.TemporaryFile(mode="w+") as times:
            command = [self.ffmpeg_bin, "-v", "error", "-nostdin", "-y",
                       "-threads", "2", "-filter_threads", "2", "-protocol_whitelist", "file,pipe",
                       "-format_whitelist", "wav,mp3,mov,flac,ogg,matroska,webm", "-progress", "pipe:1", "-nostats", *args]
            process = subprocess.Popen(command, stdout=times, stderr=errors)
            deadline = time.monotonic() + min(43200, max(120, duration * 4))
            position = 0
            last_check = 0.0
            try:
                while process.poll() is None:
                    if time.monotonic() - last_check > .25:
                        last_check = time.monotonic()
                        if cancelled():
                            raise CleaningCancelled("Processing cancelled; original file preserved.")
                        if time.monotonic() > deadline:
                            raise CleaningError("Processing exceeded its time limit. Try a shorter file.")
                        times.seek(position)
                        lines = times.read()
                        position = times.tell()
                        for line in lines.splitlines():
                            if line.startswith("out_time_us="):
                                try:
                                    progress(min(99, int(float(line.split("=", 1)[1]) / 1e6 / duration * 100)))
                                except ValueError:
                                    continue
                    time.sleep(.05)
                if cancelled():
                    raise CleaningCancelled("Processing cancelled; original file preserved.")
                if process.returncode:
                    errors.seek(0)
                    detail = errors.read(2000)
                    logger.error("Cleanup FFmpeg failure: %s", detail)
                    raise CleaningError("The media could not be fully decoded or encoded. Try a different supported source file.")
                progress(100)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)

    def extract_original(self, source: Path, output: Path, info: dict,
                         cancelled: Callable, progress: Callable) -> None:
        self.run_pass(["-xerror", "-err_detect", "explode", "-i", str(source),
                       "-map", f"0:{info['audio_stream_index']}", "-vn", "-ar", "48000",
                       "-ac", str(min(2, info["channels"])), "-c:a", "pcm_s16le", str(output)],
                      info["input_duration"], cancelled, progress)

    def denoise(self, source: Path, output: Path, strength: str,
                cancelled: Callable, progress: Callable) -> None:
        if strength not in PRESETS:
            raise CleaningError("Unknown noise-reduction strength.")
        duration = self.get_audio_duration(source)
        # Fixed conservative noise floor; do not learn quiet words as noise.
        # afftdn delays audio by 25 ms. Flush its tail and compensate that
        # algorithmic delay, preserving the final word and original timeline.
        filters = (f"apad=pad_dur=0.025,afftdn=nr={PRESETS[strength]}:nf=-50:tn=0:gs=5,"
                   f"atrim=start=0.025:end={duration + .025:.9f},asetpts=PTS-STARTPTS")
        self.run_pass(["-xerror", "-i", str(source), "-af", filters,
                       "-c:a", "pcm_s24le", str(output)], duration, cancelled, progress)

    def validate_audio(self, path: Path, expected: float, cancelled: Callable) -> float:
        duration = self.get_audio_duration(path)
        if duration <= 0 or abs(duration - expected) > .08:
            raise CleaningError("Output duration changed unexpectedly; no cleaned output was published.")
        self.run_pass(["-xerror", "-i", str(path), "-map", "0:a:0", "-f", "null", "-"],
                      expected, cancelled, lambda _: None)
        return duration

    def encode_mp3(self, source: Path, output: Path, duration: float,
                   cancelled: Callable, progress: Callable) -> None:
        self.run_pass(["-i", str(source), "-c:a", "libmp3lame", "-b:a", "192k", str(output)],
                      duration, cancelled, progress)

    def separate_music(self, source: Path, output: Path, background: Path,
                       work: Path, strength: str, repo: Path, executable: Path,
                       cancelled: Callable, progress: Callable) -> dict:
        """Run the isolated model environment, using local weights only."""
        raw_voice, raw_background = work / "voice-float.wav", work / "background-float.wav"
        result = work / "separation.json"
        script = Path(__file__).parents[1] / "separation_engine.py"
        duration = self.get_audio_duration(source)
        device = os.environ.get("AUDIO_CLEANING_DEVICE", "cpu")
        if device not in ("cpu", "auto", "cuda"):
            device = "cpu"
        env = {**os.environ, "OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2",
               "HF_HUB_OFFLINE": "1"}
        with tempfile.TemporaryFile(mode="w+") as events, tempfile.TemporaryFile(mode="w+") as errors:
            process = subprocess.Popen([str(executable), str(script), str(source), str(raw_voice),
                str(raw_background), str(result), "--repo", str(repo), "--device", device,
                "--strength", strength], stdout=events, stderr=errors, env=env)
            position = 0
            deadline = time.monotonic() + min(43200, max(180, duration*40))
            try:
                while process.poll() is None:
                    if cancelled():
                        raise CleaningCancelled()
                    if time.monotonic() > deadline:
                        raise CleaningError("Music separation exceeded its time limit. Try a shorter file.")
                    events.seek(position)
                    for line in events.read().splitlines():
                        try:
                            event = json.loads(line)
                            progress(int(event.get("progress", 0)))
                        except (ValueError, TypeError):
                            continue
                    position = events.tell()
                    time.sleep(.25)
                if cancelled():
                    raise CleaningCancelled()
                if process.returncode or not result.is_file():
                    errors.seek(0)
                    logger.error("Separation process failed: %s", errors.read(4000))
                    raise CleaningError("Music separation could not finish. Original preserved; try a shorter recording.")
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(timeout=3)
        meta = json.loads(result.read_text())
        for raw, destination in ((raw_voice, output), (raw_background, background)):
            self.run_pass(["-i", str(raw), "-af", f"volume={meta['output_gain']:.12f}",
                           "-c:a", "pcm_s24le", str(destination)], duration, cancelled, lambda _: None)
            self.validate_audio(destination, duration, cancelled)
        return meta

    def export_clean_video(self, source: Path, audio: Path, output: Path,
                           info: dict, cancelled: Callable, progress: Callable) -> dict:
        duration = info["video_duration"]
        if abs(info["audio_start"] - info["video_start"]) > .05:
            return {"video_warning": "Audio/video start times differ. Clean audio is available; video export requires timing review."}
        if self.get_audio_duration(audio) > duration + .08:
            return {"video_warning": "Audio extends beyond the video. Clean audio is available; speech was not truncated for video export."}
        common = ["-i", str(source), "-i", str(audio), "-map", f"0:{info['video_stream_index']}", "-map", "1:a:0",
                  "-af", f"apad=whole_dur={duration}", "-c:a", "aac", "-b:a", "192k",
                  "-movflags", "+faststart"]
        copied = True
        try:
            self.run_pass([*common, "-c:v", "copy", str(output)], duration, cancelled, progress)
        except CleaningError:
            copied = False
            self.run_pass([*common, "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                           "-pix_fmt", "yuv420p", str(output)], duration, cancelled, progress)
        from app.services.dubbing.exporter import VideoExportService
        VideoExportService(video_processor=self).verify_exported_video(
            output, expected_duration=duration, original_video_path=source)
        self.run_pass(["-xerror", "-i", str(output), "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
                      duration, cancelled, lambda _: None)
        return {"video_stream_copied": copied, "video_duration": self.probe(output)["format"]["duration"]}
