import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.services.video.ffmpeg import FFmpegVideoProcessor
from app.services.video.exceptions import VideoProcessingError
from app.services.subtitles.checker import get_fonts_dir

logger = logging.getLogger(__name__)


@dataclass
class ExportResult:
    video_path: Path
    duration_seconds: float
    file_size_bytes: int
    video_codec: str
    audio_codec: str
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: str = "original"
    reframe_mode: str = "none"
    burn_subtitles: bool = False


ASPECT_RATIO_PRESETS = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}


class VideoExportService:
    """Combines original video stream with the synchronized Khmer audio timeline into a final MP4."""

    def __init__(
        self,
        ffmpeg_bin: str = "ffmpeg",
        ffprobe_bin: str = "ffprobe",
        video_processor: Optional[FFmpegVideoProcessor] = None,
    ):
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin
        self.video_processor = video_processor or FFmpegVideoProcessor()

    @staticmethod
    def escape_filter_path(path: Path) -> str:
        """Escape file path for FFmpeg libavfilter filter arguments."""
        p_str = str(path).replace("\\", "/")
        p_str = p_str.replace(":", r"\:")
        p_str = p_str.replace("'", r"\'")
        return p_str

    @staticmethod
    def build_reframe_filter(
        aspect_ratio: str,
        reframe_mode: str = "blur_pillar",
    ) -> Optional[tuple[str, int, int]]:
        """Construct an FFmpeg complex filtergraph string and target resolution (w, h)
        for aspect ratio conversion and social media reframing.
        Returns None if aspect_ratio is 'original' or unsupported.
        """
        if not aspect_ratio or aspect_ratio == "original" or aspect_ratio not in ASPECT_RATIO_PRESETS:
            return None

        tw, th = ASPECT_RATIO_PRESETS[aspect_ratio]
        mode = (reframe_mode or "blur_pillar").lower()

        if mode == "center_crop":
            # Scale so image fills frame completely, crop overflow equally
            filter_str = (
                f"[0:v]scale={tw}:{th}:force_original_aspect_ratio=increase,"
                f"crop={tw}:{th},setsar=1[v_out]"
            )
        elif mode == "fit_black":
            # Scale inside frame, pad borders with black
            filter_str = (
                f"[0:v]scale={tw}:{th}:force_original_aspect_ratio=decrease,"
                f"pad={tw}:{th}:({tw}-iw)/2:({th}-ih)/2:black,setsar=1[v_out]"
            )
        else:
            # blur_pillar (default): cinematic blurred background + crisp centered foreground
            filter_str = (
                f"[0:v]split=2[bg_raw][fg_raw];"
                f"[bg_raw]scale={tw}:{th}:force_original_aspect_ratio=increase,"
                f"crop={tw}:{th},boxblur=20:2,setsar=1[bg];"
                f"[fg_raw]scale={tw}:{th}:force_original_aspect_ratio=decrease,setsar=1[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v_out]"
            )

        return (filter_str, tw, th)

    def verify_exported_video(
        self,
        video_path: Path,
        expected_duration: Optional[float] = None,
        tolerance_seconds: float = 0.15,
        original_video_path: Optional[Path] = None,
        expected_width: Optional[int] = None,
        expected_height: Optional[int] = None,
        aspect_ratio: str = "original",
        reframe_mode: str = "none",
        burn_subtitles: bool = False,
    ) -> ExportResult:
        """Inspect and verify that exported MP4 contains valid video and audio streams,
        duration within tolerance, and correct video frame dimensions.
        """
        if not video_path.exists() or video_path.stat().st_size == 0:
            raise VideoProcessingError(f"Exported video missing or empty at {video_path}")

        cmd = [
            self.ffprobe_bin,
            "-v", "error",
            "-show_entries", "stream=index,codec_type,codec_name,duration,width,height:format=duration,size",
            "-of", "json",
            str(video_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise VideoProcessingError(f"FFprobe failed to inspect exported video: {res.stderr}")

        try:
            data = json.loads(res.stdout)
        except json.JSONDecodeError as e:
            raise VideoProcessingError(f"Invalid JSON from ffprobe: {e}") from e

        streams = data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        if not video_stream:
            raise VideoProcessingError("Exported MP4 is missing a video stream.")
        if not audio_stream:
            raise VideoProcessingError("Exported MP4 is missing an audio stream.")

        format_info = data.get("format", {})
        try:
            duration = float(format_info.get("duration", 0.0))
        except (ValueError, TypeError):
            duration = 0.0

        try:
            video_dur = float(video_stream.get("duration", 0.0))
        except (ValueError, TypeError):
            video_dur = 0.0

        try:
            audio_dur = float(audio_stream.get("duration", 0.0))
        except (ValueError, TypeError):
            audio_dur = 0.0

        if duration <= 0.0:
            duration = video_dur if video_dur > 0.0 else audio_dur

        # Strict duration validation against expected target video duration
        if expected_duration is not None and expected_duration > 0.0:
            diff_audio = abs(audio_dur - expected_duration) if audio_dur > 0.0 else 0.0
            diff_video = abs(video_dur - expected_duration) if video_dur > 0.0 else 0.0

            if diff_audio > tolerance_seconds:
                raise VideoProcessingError(
                    f"Exported audio duration mismatch: audio stream is {audio_dur:.3f}s, expected {expected_duration:.3f}s "
                    f"(difference: {diff_audio:.3f}s exceeds {tolerance_seconds:.2f}s tolerance)."
                )

            video_matches = (diff_video <= tolerance_seconds)
            # If video track length differs slightly from container expected duration,
            # verify against source video's actual video track duration to ensure 100% fidelity
            if not video_matches and original_video_path and original_video_path.exists():
                try:
                    cmd_orig = [
                        self.ffprobe_bin,
                        "-v", "error",
                        "-show_entries", "stream=codec_type,duration",
                        "-of", "json",
                        str(original_video_path),
                    ]
                    res_orig = subprocess.run(cmd_orig, capture_output=True, text=True, check=False)
                    if res_orig.returncode == 0:
                        data_orig = json.loads(res_orig.stdout)
                        for s in data_orig.get("streams", []):
                            if s.get("codec_type") == "video":
                                orig_vdur = float(s.get("duration", 0.0))
                                if orig_vdur > 0.0 and abs(video_dur - orig_vdur) <= tolerance_seconds:
                                    video_matches = True
                                    break
                except Exception:
                    pass

            if not video_matches:
                raise VideoProcessingError(
                    f"Exported video duration mismatch: video stream is {video_dur:.3f}s, expected {expected_duration:.3f}s "
                    f"(difference: {diff_video:.3f}s exceeds {tolerance_seconds:.2f}s tolerance)."
                )

        # Validate dimensions if requested
        width = int(video_stream.get("width", 0)) if video_stream.get("width") else None
        height = int(video_stream.get("height", 0)) if video_stream.get("height") else None

        if expected_width is not None and width is not None and width != expected_width:
            raise VideoProcessingError(
                f"Exported video width mismatch: got {width}px, expected {expected_width}px for aspect ratio {aspect_ratio}."
            )
        if expected_height is not None and height is not None and height != expected_height:
            raise VideoProcessingError(
                f"Exported video height mismatch: got {height}px, expected {expected_height}px for aspect ratio {aspect_ratio}."
            )

        file_size = video_path.stat().st_size

        return ExportResult(
            video_path=video_path,
            duration_seconds=round(duration, 2),
            file_size_bytes=file_size,
            video_codec=video_stream.get("codec_name", "unknown"),
            audio_codec=audio_stream.get("codec_name", "unknown"),
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            reframe_mode=reframe_mode,
            burn_subtitles=burn_subtitles,
        )

    def export(
        self,
        video_path: Path,
        audio_timeline_path: Path,
        output_video_path: Path,
        expected_duration: Optional[float] = None,
        tolerance_seconds: float = 0.15,
        preserve_bgm: bool = False,
        ducking_preset: str = "balanced",
        bgm_volume: float = 0.35,
        attenuate_center_vocals: bool = True,
        source_audio_path: Optional[Path] = None,
        aspect_ratio: str = "original",
        reframe_mode: str = "blur_pillar",
        burn_subtitles: bool = False,
        subtitle_path: Optional[Path] = None,
        fonts_dir: Optional[Path] = None,
    ) -> ExportResult:
        """Remux original video and new Khmer audio timeline into MP4 with atomic publishing.
        Optionally mixes and ducks background music from original video audio,
        optionally converts aspect ratio (e.g. 9:16 vertical for TikTok/Shorts), and
        optionally burns styled subtitles directly onto video canvas using libass with HarfBuzz.
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Original video not found: {video_path}")
        if not audio_timeline_path.exists() or audio_timeline_path.stat().st_size == 0:
            raise FileNotFoundError(f"Audio timeline missing or empty: {audio_timeline_path}")

        output_video_path.parent.mkdir(parents=True, exist_ok=True)
        temp_output_path = output_video_path.with_suffix(".tmp.mp4")
        temp_ducked_audio: Optional[Path] = None
        effective_audio_timeline = audio_timeline_path
        active_fonts_dir = fonts_dir or get_fonts_dir()
        escaped_fontsdir = self.escape_filter_path(active_fonts_dir)

        try:
            if preserve_bgm:
                from app.services.dubbing.audio_mixer import AudioDuckingMixer, DuckingConfig
                bg_src = source_audio_path if (source_audio_path and source_audio_path.exists()) else video_path
                temp_ducked_audio = output_video_path.with_suffix(".ducked.tmp.wav")
                mixer = AudioDuckingMixer(ffmpeg_bin=self.ffmpeg_bin, ffprobe_bin=self.ffprobe_bin)
                cfg = DuckingConfig(
                    preset=ducking_preset,
                    bgm_volume=bgm_volume,
                    speech_volume=1.0,
                    attenuate_center_vocals=attenuate_center_vocals,
                )
                mixer.mix_and_duck(
                    background_audio_path=bg_src,
                    speech_audio_path=audio_timeline_path,
                    output_path=temp_ducked_audio,
                    expected_duration=expected_duration,
                    config=cfg,
                    tolerance_seconds=tolerance_seconds,
                )
                effective_audio_timeline = temp_ducked_audio

            # Check if aspect ratio reframe is requested
            reframe_info = self.build_reframe_filter(aspect_ratio, reframe_mode)
            target_w: Optional[int] = None
            target_h: Optional[int] = None

            if reframe_info is not None:
                filter_complex_str, target_w, target_h = reframe_info
                if burn_subtitles and subtitle_path and subtitle_path.exists():
                    escaped_sub = self.escape_filter_path(subtitle_path)
                    filter_complex_str = (
                        filter_complex_str.replace("[v_out]", "[v_reframe]")
                        + f";[v_reframe]ass='{escaped_sub}':fontsdir='{escaped_fontsdir}'[v_out]"
                    )
                cmd_reframe = [
                    self.ffmpeg_bin,
                    "-y",
                    "-i", str(video_path),
                    "-i", str(effective_audio_timeline),
                    "-filter_complex", filter_complex_str,
                    "-map", "[v_out]",
                    "-map", "1:a:0",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "22",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-movflags", "+faststart",
                    str(temp_output_path),
                ]
                logger.info(
                    "Executing video export with reframe to %s (%s, %dx%d, subtitles=%s)...",
                    aspect_ratio, reframe_mode, target_w, target_h, burn_subtitles,
                )
                res_rf = subprocess.run(cmd_reframe, capture_output=True, text=True, check=False)
                if res_rf.returncode != 0:
                    if temp_output_path.exists():
                        temp_output_path.unlink()
                    raise VideoProcessingError(f"Video export failed during aspect ratio reframe: {res_rf.stderr}")
            elif burn_subtitles and subtitle_path and subtitle_path.exists():
                # Original aspect ratio with subtitle burn-in via libass with HarfBuzz
                escaped_sub = self.escape_filter_path(subtitle_path)
                cmd_sub = [
                    self.ffmpeg_bin,
                    "-y",
                    "-i", str(video_path),
                    "-i", str(effective_audio_timeline),
                    "-vf", f"ass='{escaped_sub}':fontsdir='{escaped_fontsdir}'",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "22",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-movflags", "+faststart",
                    str(temp_output_path),
                ]
                logger.info("Executing video export with burned subtitles via libass (original aspect ratio)...")
                res_sub = subprocess.run(cmd_sub, capture_output=True, text=True, check=False)
                if res_sub.returncode != 0:
                    if temp_output_path.exists():
                        temp_output_path.unlink()
                    raise VideoProcessingError(f"Video export failed during subtitle burn-in: {res_sub.stderr}")
            else:
                # Original aspect ratio without subtitle burn-in: attempt fast remux first with stream copy (-c:v copy)
                cmd_copy = [
                    self.ffmpeg_bin,
                    "-y",
                    "-i", str(video_path),
                    "-i", str(effective_audio_timeline),
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-movflags", "+faststart",
                ]
                cmd_copy.append(str(temp_output_path))

                logger.info("Executing video remux via stream copy (preserve_bgm=%s)...", preserve_bgm)
                res = subprocess.run(cmd_copy, capture_output=True, text=True, check=False)

                # Fallback to H.264 encode if stream copy fails
                if res.returncode != 0:
                    logger.warning("Stream copy failed (%s). Retrying with H.264 transcode fallback...", res.stderr.strip())
                    cmd_transcode = [
                        self.ffmpeg_bin,
                        "-y",
                        "-i", str(video_path),
                        "-i", str(effective_audio_timeline),
                        "-map", "0:v:0",
                        "-map", "1:a:0",
                        "-c:v", "libx264",
                        "-preset", "fast",
                        "-crf", "22",
                        "-pix_fmt", "yuv420p",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        "-movflags", "+faststart",
                    ]
                    cmd_transcode.append(str(temp_output_path))
                    res_tc = subprocess.run(cmd_transcode, capture_output=True, text=True, check=False)
                    if res_tc.returncode != 0:
                        if temp_output_path.exists():
                            temp_output_path.unlink()
                        raise VideoProcessingError(f"Video export failed in transcode fallback: {res_tc.stderr}")

            # Verify exported video before publishing
            result = self.verify_exported_video(
                temp_output_path,
                expected_duration=expected_duration,
                tolerance_seconds=tolerance_seconds,
                original_video_path=video_path,
                expected_width=target_w,
                expected_height=target_h,
                aspect_ratio=aspect_ratio,
                reframe_mode=reframe_mode if reframe_info else "none",
                burn_subtitles=burn_subtitles,
            )
            # Atomically publish to final destination
            shutil.move(str(temp_output_path), str(output_video_path))
            result.video_path = output_video_path
            logger.info("Successfully exported dubbed MP4: %s (%.2fs)", output_video_path.name, result.duration_seconds)
            return result
        except Exception as e:
            if temp_output_path.exists():
                temp_output_path.unlink()
            raise
        finally:
            if temp_ducked_audio and temp_ducked_audio.exists():
                try:
                    temp_ducked_audio.unlink()
                except OSError:
                    pass
