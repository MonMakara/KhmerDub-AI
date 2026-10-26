import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import httpx
import yt_dlp

from app.services.downloader.security import (
    safe_connection_guard,
    validate_and_classify_url,
    DownloaderSecurityError,
    InvalidURLError,
    UnsupportedSourceError,
)

logger = logging.getLogger(__name__)


class VideoMetadataError(Exception):
    """Raised when video metadata extraction fails."""
    pass


def _clean_title(title: Optional[str]) -> str:
    """Sanitize video title for display and storage."""
    if not title or not isinstance(title, str):
        return "Untitled Media"
    # Strip dangerous characters and excessive whitespace
    cleaned = re.sub(r'[\r\n\t]+', ' ', title).strip()
    return cleaned if cleaned else "Untitled Media"


def fetch_media_metadata(url: str) -> Dict[str, Any]:
    """Fetch video/audio metadata from a permitted URL without downloading media.

    Enforces SSRF validation, source classification, and returns normalized metadata.
    """
    normalized_url, platform = validate_and_classify_url(url)

    with safe_connection_guard():
        if platform in {"YouTube", "TikTok"}:
            return _fetch_yt_dlp_metadata(normalized_url, platform)
        elif platform == "Direct Media":
            return _fetch_direct_media_metadata(normalized_url)
        else:
            raise UnsupportedSourceError(f"Unsupported source platform '{platform}'.")


def _fetch_yt_dlp_metadata(url: str, platform: str) -> Dict[str, Any]:
    """Extract metadata using yt-dlp with strictly hardened security options."""
    ydl_opts = {
        "skip_download": True,
        "extract_flat": False,
        "noplaylist": True,
        "no_warnings": True,
        "quiet": True,
        "socket_timeout": 15,
        "no_color": True,
        "no_cookies": True,
        "max_downloads": 1,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        err_msg = str(e)
        logger.warning("yt-dlp metadata extraction failed for %s: %s", url, err_msg)
        if "Private video" in err_msg or "Sign in" in err_msg or "login" in err_msg.lower():
            raise VideoMetadataError("This video is private, restricted, or requires login credentials.")
        elif "copyright" in err_msg.lower():
            raise VideoMetadataError("This video is unavailable due to copyright or access restrictions.")
        elif "Video unavailable" in err_msg or "404" in err_msg:
            raise VideoMetadataError("The requested video was not found or is unavailable.")
        else:
            raise VideoMetadataError(f"Could not retrieve video information: {err_msg.split(';')[-1].strip()}")
    except Exception as e:
        logger.error("Unexpected error extracting metadata for %s: %s", url, e)
        raise VideoMetadataError(f"Failed to fetch metadata: {e}") from e

    if not info:
        raise VideoMetadataError("No metadata returned by extractor.")

    # Single video verification: disallow playlists
    if info.get("_type") == "playlist" or "entries" in info:
        raise VideoMetadataError("Playlists and channel-wide downloads are not supported. Please provide a single video link.")

    title = _clean_title(info.get("title"))
    uploader = info.get("uploader") or info.get("channel") or info.get("creator") or None
    duration = info.get("duration")
    if duration is not None:
        try:
            duration = float(duration)
        except (ValueError, TypeError):
            duration = None

    thumbnail = info.get("thumbnail") or None
    estimated_filesize = info.get("filesize") or info.get("filesize_approx")

    # Parse available formats into clean resolution choices
    formats = info.get("formats", [])
    available_heights = set()
    for f in formats:
        # Check for video streams
        height = f.get("height")
        vcodec = f.get("vcodec")
        if height and vcodec and vcodec != "none":
            available_heights.add(int(height))

    standard_resolutions = [1080, 720, 480, 360, 240]
    available_video_qualities: List[str] = []

    for res in standard_resolutions:
        if any(h >= res for h in available_heights):
            available_video_qualities.append(f"{res}p")

    # If no standard matched but some height exists, add the max available
    if not available_video_qualities and available_heights:
        max_h = max(available_heights)
        available_video_qualities.append(f"{max_h}p")

    if not available_video_qualities:
        available_video_qualities.append("best")
    elif "best" not in available_video_qualities:
        available_video_qualities.insert(0, "best")

    available_audio_formats = ["mp3", "m4a", "wav"]

    return {
        "url": url,
        "title": title,
        "source_platform": platform,
        "uploader": uploader or "Unavailable",
        "duration_seconds": duration,
        "thumbnail_url": thumbnail,
        "available_video_qualities": available_video_qualities,
        "available_audio_formats": available_audio_formats,
        "estimated_file_size_bytes": int(estimated_filesize) if estimated_filesize else None,
        "is_audio_only_source": False,
        "notice": "Download or import only media you own, have permission to use, or are otherwise permitted to download.",
    }


def _fetch_direct_media_metadata(url: str) -> Dict[str, Any]:
    """Inspect a direct media file URL via HTTP HEAD / partial range check."""
    parsed = urlparse(url)
    filename = parsed.path.split("/")[-1] if parsed.path else "direct_media"
    clean_name = _clean_title(filename.rsplit(".", 1)[0] if "." in filename else filename)

    is_audio_only = any(parsed.path.lower().endswith(ext) for ext in [".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"])

    estimated_size: Optional[int] = None
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
    }
    try:
        with httpx.Client(follow_redirects=True, timeout=10.0, headers=headers) as client:
            resp = client.head(url)
            if resp.status_code == 200:
                cl = resp.headers.get("content-length")
                if cl and cl.isdigit():
                    estimated_size = int(cl)
            elif resp.status_code in {403, 405}:
                # Some CDNs block HEAD requests; fallback to Range GET for 1 byte
                range_resp = client.get(url, headers={"Range": "bytes=0-0"})
                if range_resp.status_code in {200, 206}:
                    cr = range_resp.headers.get("content-range")
                    if cr and "/" in cr:
                        total_str = cr.split("/")[-1]
                        if total_str.isdigit():
                            estimated_size = int(total_str)
                    elif range_resp.headers.get("content-length"):
                        cl = range_resp.headers.get("content-length")
                        if cl and cl.isdigit() and range_resp.status_code == 200:
                            estimated_size = int(cl)
    except Exception as e:
        logger.warning("HEAD/Range request failed for %s, continuing with fallback: %s", url, e)

    video_qualities = ["best"] if not is_audio_only else []
    audio_formats = ["mp3", "m4a", "wav"]

    return {
        "url": url,
        "title": clean_name,
        "source_platform": "Direct Media",
        "uploader": parsed.hostname or "Direct Source",
        "duration_seconds": None,  # Will be extracted after partial or full probe
        "thumbnail_url": None,
        "available_video_qualities": video_qualities,
        "available_audio_formats": audio_formats,
        "estimated_file_size_bytes": estimated_size,
        "is_audio_only_source": is_audio_only,
        "notice": "Download or import only media you own, have permission to use, or are otherwise permitted to download.",
    }
