import json
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional
import httpx
import yt_dlp

from app.core.storage import (
    get_toolkit_task_dir,
    get_toolkit_task_input_dir,
    get_toolkit_task_output_dir,
)
from app.services.downloader.security import (
    safe_connection_guard,
    validate_and_classify_url,
    SSRFSecurityError,
    DownloaderSecurityError,
)
from app.services.video.ffmpeg import FFmpegVideoProcessor

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB limit
MAX_DURATION_SECONDS = 7200  # 2 hours limit
MAX_CONCURRENT_DOWNLOADS = 2

_download_semaphore = threading.Semaphore(MAX_CONCURRENT_DOWNLOADS)
_active_cancellations: Dict[str, threading.Event] = {}
_active_lock = threading.Lock()
_video_processor = FFmpegVideoProcessor()


class DownloadCancelledException(Exception):
    """Raised when a download task has been cancelled by the user."""
    pass


class DownloadLimitExceededError(Exception):
    """Raised when media exceeds size or duration limits."""
    pass


class VideoDownloadError(Exception):
    """Raised when download execution or post-processing fails."""
    pass


def request_download_cancellation(task_id: str) -> bool:
    """Signal an active download task to cancel."""
    with _active_lock:
        event = _active_cancellations.get(task_id)
        if event:
            event.set()
            logger.info("Cancellation requested for download task %s", task_id)
            return True
    return False


def is_cancellation_requested(task_id: str) -> bool:
    """Check if task_id has been signaled for cancellation."""
    with _active_lock:
        event = _active_cancellations.get(task_id)
        return event.is_set() if event else False


def execute_download_job(
    task_id: str,
    url: str,
    output_type: str,  # "video" or "audio"
    quality: str,  # "1080p", "720p", "480p", "360p", "best"
    audio_format: str,  # "mp3", "m4a", "wav"
    progress_callback: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    """Execute media download with progress tracking, cancellation support, and FFmpeg transcoding.

    Guarantees thread-level SSRF isolation and resource limits.
    """
    cancel_event = threading.Event()
    with _active_lock:
        _active_cancellations[task_id] = cancel_event

    acquired = _download_semaphore.acquire(timeout=60)
    if not acquired:
        raise VideoDownloadError("Server download queue is full. Please try again shortly.")

    try:
        return _run_download_process(
            task_id=task_id,
            url=url,
            output_type=output_type,
            quality=quality,
            audio_format=audio_format,
            cancel_event=cancel_event,
            progress_callback=progress_callback,
        )
    finally:
        _download_semaphore.release()
        with _active_lock:
            _active_cancellations.pop(task_id, None)


def _cleanup_partial_files(task_dir: Path):
    """Remove partial download artifacts (.part, .ytdl, .tmp)."""
    try:
        if not task_dir.exists():
            return
        for item in task_dir.rglob("*"):
            if item.is_file() and (item.suffix in {".part", ".ytdl", ".tmp"} or "temp" in item.name):
                try:
                    item.unlink(missing_ok=True)
                except Exception:
                    pass
    except Exception as e:
        logger.warning("Error cleaning partial download files in %s: %s", task_dir, e)


def _run_download_process(
    task_id: str,
    url: str,
    output_type: str,
    quality: str,
    audio_format: str,
    cancel_event: threading.Event,
    progress_callback: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    """Internal download processor."""
    normalized_url, platform = validate_and_classify_url(url)
    input_dir = get_toolkit_task_input_dir(task_id)
    output_dir = get_toolkit_task_output_dir(task_id)
    task_dir = get_toolkit_task_dir(task_id)

    progress_callback({
        "status": "processing",
        "stage": "fetching_metadata",
        "progress_percentage": 5,
        "detail": "Initializing secure download connection...",
    })

    if cancel_event.is_set():
        raise DownloadCancelledException("Download cancelled by user.")

    raw_download_path: Optional[Path] = None

    with safe_connection_guard():
        if platform in {"YouTube", "TikTok"}:
            raw_download_path = _download_yt_dlp(
                task_id=task_id,
                url=normalized_url,
                output_type=output_type,
                quality=quality,
                dest_dir=input_dir,
                cancel_event=cancel_event,
                progress_callback=progress_callback,
            )
        else:
            raw_download_path = _download_direct_media(
                task_id=task_id,
                url=normalized_url,
                dest_dir=input_dir,
                cancel_event=cancel_event,
                progress_callback=progress_callback,
            )

    if cancel_event.is_set():
        _cleanup_partial_files(task_dir)
        raise DownloadCancelledException("Download cancelled by user.")

    if not raw_download_path or not raw_download_path.exists() or raw_download_path.stat().st_size == 0:
        raise VideoDownloadError("Download failed: No output file was produced.")

    # Size limit verification
    file_size = raw_download_path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        _cleanup_partial_files(task_dir)
        raise DownloadLimitExceededError(
            f"Downloaded file size ({file_size // (1024*1024)}MB) exceeds maximum limit of {MAX_FILE_SIZE_BYTES // (1024*1024)}MB."
        )

    # Transcoding & Normalization
    progress_callback({
        "status": "processing",
        "stage": "transcoding",
        "progress_percentage": 90,
        "detail": "Optimizing media container for playback and dubbing...",
    })

    final_output_path = _transcode_and_normalize(
        raw_path=raw_download_path,
        output_dir=output_dir,
        task_id=task_id,
        output_type=output_type,
        audio_format=audio_format,
        cancel_event=cancel_event,
    )

    if cancel_event.is_set():
        _cleanup_partial_files(task_dir)
        raise DownloadCancelledException("Download cancelled by user.")

    # Probe final output metadata via ffprobe
    duration_seconds: Optional[float] = None
    media_metadata: Dict[str, Any] = {}
    try:
        probe_meta = _video_processor.get_metadata(final_output_path)
        duration_seconds = probe_meta.duration
        media_metadata = {
            "format": probe_meta.format,
            "width": probe_meta.width,
            "height": probe_meta.height,
            "video_codec": probe_meta.video_codec,
            "has_audio": probe_meta.has_audio,
            "audio_codec": probe_meta.audio_codec,
            "sample_rate": probe_meta.audio_sample_rate,
            "channels": probe_meta.audio_channels,
        }
    except Exception as e:
        logger.warning("Could not probe output file metadata: %s", e)

    # Duration limit check
    if duration_seconds and duration_seconds > MAX_DURATION_SECONDS:
        _cleanup_partial_files(task_dir)
        raise DownloadLimitExceededError(
            f"Media duration ({int(duration_seconds)}s) exceeds maximum allowed duration ({MAX_DURATION_SECONDS}s)."
        )

    # Clean intermediate input files to save disk space
    try:
        shutil.rmtree(input_dir, ignore_errors=True)
    except Exception:
        pass

    final_size = final_output_path.stat().st_size

    progress_callback({
        "status": "completed",
        "stage": "completed",
        "progress_percentage": 100,
        "detail": "Download and processing completed successfully.",
        "output_file_path": str(final_output_path),
        "output_filename": final_output_path.name,
        "output_duration_seconds": duration_seconds,
        "output_file_size_bytes": final_size,
        "output_media_metadata": json.dumps(media_metadata),
    })

    return {
        "output_file_path": str(final_output_path),
        "output_filename": final_output_path.name,
        "output_duration_seconds": duration_seconds,
        "output_file_size_bytes": final_size,
        "media_metadata": media_metadata,
    }


def _download_yt_dlp(
    task_id: str,
    url: str,
    output_type: str,
    quality: str,
    dest_dir: Path,
    cancel_event: threading.Event,
    progress_callback: Callable[[Dict[str, Any]], None],
) -> Path:
    """Download using yt-dlp with progress callback and cancel hook."""
    output_template = str(dest_dir / f"raw_download_{task_id}.%(ext)s")

    # Format selector based on requested quality and output_type
    format_spec = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    if output_type == "audio":
        format_spec = "bestaudio/best"
    elif quality != "best":
        # Extract numeric height (e.g., '720p' -> 720)
        m = re.match(r"^(\d+)", quality)
        if m:
            height = m.group(1)
            format_spec = f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}]/best"

    last_update_time = [0.0]

    def _hook(d):
        if cancel_event.is_set():
            raise DownloadCancelledException("Download cancelled by user.")

        if d.get("status") == "downloading":
            now = time.time()
            if now - last_update_time[0] >= 0.5:  # Throttle updates to 2 Hz
                last_update_time[0] = now
                downloaded = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                speed = d.get("speed")
                eta = d.get("eta")

                pct = 10
                if total and total > 0:
                    pct = min(85, int(10 + (downloaded / total) * 75))

                progress_callback({
                    "status": "processing",
                    "stage": "downloading",
                    "progress_percentage": pct,
                    "downloaded_bytes": downloaded,
                    "total_bytes": total if total > 0 else None,
                    "speed_bytes_per_sec": speed,
                    "eta_seconds": eta,
                    "detail": f"Downloading media ({downloaded // (1024*1024)} MB)...",
                })

    ydl_opts = {
        "format": format_spec,
        "outtmpl": output_template,
        "noplaylist": True,
        "no_warnings": True,
        "quiet": True,
        "socket_timeout": 30,
        "max_downloads": 1,
        "no_cookies": True,
        "progress_hooks": [_hook],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except DownloadCancelledException:
        raise
    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        logger.warning("yt-dlp download failed for %s: %s", url, err)
        raise VideoDownloadError(f"Download failed: {err.split(';')[-1].strip()}")
    except Exception as e:
        logger.error("Unexpected yt-dlp failure: %s", e)
        raise VideoDownloadError(f"Download engine error: {e}") from e

    # Find the downloaded file
    candidates = list(dest_dir.glob(f"raw_download_{task_id}.*"))
    valid_candidates = [c for c in candidates if c.is_file() and not c.name.endswith(".part") and not c.name.endswith(".ytdl")]
    if not valid_candidates:
        raise VideoDownloadError("Expected download output file was not found.")

    return valid_candidates[0]


def _download_direct_media(
    task_id: str,
    url: str,
    dest_dir: Path,
    cancel_event: threading.Event,
    progress_callback: Callable[[Dict[str, Any]], None],
) -> Path:
    """Download direct media file via streaming HTTP client."""
    ext = url.split("?")[0].rsplit(".", 1)[-1].lower() if "." in url else "mp4"
    if ext not in {"mp4", "mov", "webm", "m4a", "mp3", "wav", "ogg", "aac", "flac"}:
        ext = "mp4"

    target_path = dest_dir / f"raw_direct_{task_id}.{ext}"
    downloaded_bytes = 0
    total_bytes: Optional[int] = None
    start_time = time.time()
    last_update = 0.0

    try:
        with httpx.Client(follow_redirects=True, timeout=30.0) as client:
            with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise VideoDownloadError(f"HTTP request failed with status code {response.status_code}")

                cl = response.headers.get("content-length")
                if cl and cl.isdigit():
                    total_bytes = int(cl)
                    if total_bytes > MAX_FILE_SIZE_BYTES:
                        raise DownloadLimitExceededError(
                            f"Remote file size ({total_bytes // (1024*1024)}MB) exceeds limit of {MAX_FILE_SIZE_BYTES // (1024*1024)}MB."
                        )

                with open(target_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=65536):
                        if cancel_event.is_set():
                            raise DownloadCancelledException("Download cancelled by user.")

                        f.write(chunk)
                        downloaded_bytes += len(chunk)

                        if downloaded_bytes > MAX_FILE_SIZE_BYTES:
                            raise DownloadLimitExceededError("Download exceeded maximum file size limit.")

                        now = time.time()
                        if now - last_update >= 0.5:
                            last_update = now
                            elapsed = max(0.1, now - start_time)
                            speed = downloaded_bytes / elapsed
                            eta = int((total_bytes - downloaded_bytes) / speed) if (total_bytes and speed > 0) else None
                            pct = 10
                            if total_bytes and total_bytes > 0:
                                pct = min(85, int(10 + (downloaded_bytes / total_bytes) * 75))

                            progress_callback({
                                "status": "processing",
                                "stage": "downloading",
                                "progress_percentage": pct,
                                "downloaded_bytes": downloaded_bytes,
                                "total_bytes": total_bytes,
                                "speed_bytes_per_sec": speed,
                                "eta_seconds": eta,
                                "detail": f"Downloading direct media ({downloaded_bytes // (1024*1024)} MB)...",
                            })
    except DownloadCancelledException:
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        raise
    except Exception as e:
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        logger.error("Direct media download failed for %s: %s", url, e)
        raise VideoDownloadError(f"Failed to download direct media: {e}") from e

    return target_path


def _transcode_and_normalize(
    raw_path: Path,
    output_dir: Path,
    task_id: str,
    output_type: str,
    audio_format: str,
    cancel_event: threading.Event,
) -> Path:
    """Normalize output container and codecs using FFmpeg."""
    if cancel_event.is_set():
        raise DownloadCancelledException("Cancelled before transcoding.")

    if output_type == "audio":
        fmt = audio_format.lower() if audio_format in {"mp3", "m4a", "wav"} else "mp3"
        out_file = output_dir / f"downloaded_audio_{task_id}.{fmt}"

        if fmt == "mp3":
            cmd = ["ffmpeg", "-y", "-i", str(raw_path), "-vn", "-c:a", "libmp3lame", "-b:a", "192k", str(out_file)]
        elif fmt == "m4a":
            cmd = ["ffmpeg", "-y", "-i", str(raw_path), "-vn", "-c:a", "aac", "-b:a", "192k", str(out_file)]
        else:  # wav
            cmd = ["ffmpeg", "-y", "-i", str(raw_path), "-vn", "-c:a", "pcm_s16le", "-ar", "44100", str(out_file)]
    else:
        # Standardize video to web-ready MP4 (H.264 + AAC)
        out_file = output_dir / f"downloaded_video_{task_id}.mp4"
        cmd = [
            "ffmpeg", "-y", "-i", str(raw_path),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(out_file),
        ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while proc.poll() is None:
            if cancel_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                if out_file.exists():
                    out_file.unlink(missing_ok=True)
                raise DownloadCancelledException("Transcoding cancelled by user.")
            time.sleep(0.3)

        if proc.returncode != 0:
            stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else "Unknown error"
            logger.error("FFmpeg transcoding failed: %s", stderr)
            raise VideoDownloadError(f"Transcoding failed: {stderr[-200:]}")
    except DownloadCancelledException:
        raise
    except Exception as e:
        if out_file.exists():
            out_file.unlink(missing_ok=True)
        raise VideoDownloadError(f"Error during media normalization: {e}") from e

    return out_file
