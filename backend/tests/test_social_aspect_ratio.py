"""Unit and integration tests for Social Media Aspect Ratio conversion & Reframing
(9:16 Vertical for TikTok/Shorts/Reels, 1:1 Square, 16:9, and Blurred Pillarbox / Center Crop).
"""
import io
import json
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.project import (
    GeneratedAudio,
    ProcessingJob,
    Project,
    ProjectStatus,
    TranscriptSegment,
    TranslationSegment,
    Video,
)
from app.services.dubbing.exporter import VideoExportService, ASPECT_RATIO_PRESETS


def make_test_media(
    video_path: Path,
    audio_path: Path,
    width: int = 1280,
    height: int = 720,
    duration: float = 2.0,
) -> None:
    """Create a synthetic MP4 video and separate WAV audio timeline."""
    video_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Generate synthetic video
    cmd_vid = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate=25:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac",
        str(video_path),
    ]
    subprocess.run(cmd_vid, check=True, capture_output=True)

    # 2. Generate synthetic audio timeline (48kHz mono WAV)
    rate = 48000
    t = np.linspace(0, duration, int(duration * rate), endpoint=False)
    sine = (0.2 * np.sin(2 * np.pi * 550 * t) * 32767).astype("<i2")
    with wave.open(str(audio_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(sine.tobytes())


def get_video_dimensions(video_path: Path) -> tuple[int, int]:
    """Inspect video width and height using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=width,height",
        "-of", "json",
        str(video_path),
    ]
    res = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(res.stdout)
    for s in data.get("streams", []):
        if "width" in s and "height" in s and s["width"] and s["height"]:
            return int(s["width"]), int(s["height"])
    raise ValueError(f"Could not find video dimensions in {video_path}")


def test_build_reframe_filter_presets():
    """Verify filtergraph construction for all supported social media presets."""
    service = VideoExportService()

    # 1. Original ratio returns None (stream copy or native transcode)
    assert service.build_reframe_filter("original") is None
    assert service.build_reframe_filter("") is None
    assert service.build_reframe_filter("unknown") is None

    # 2. 9:16 Vertical (1080x1920)
    rf_blur = service.build_reframe_filter("9:16", "blur_pillar")
    assert rf_blur is not None
    filter_str, w, h = rf_blur
    assert (w, h) == (1080, 1920)
    assert "boxblur=20:2" in filter_str
    assert "overlay=(W-w)/2:(H-h)/2" in filter_str

    rf_crop = service.build_reframe_filter("9:16", "center_crop")
    assert rf_crop is not None
    filter_str_crop, w, h = rf_crop
    assert (w, h) == (1080, 1920)
    assert "crop=1080:1920" in filter_str_crop

    rf_black = service.build_reframe_filter("9:16", "fit_black")
    assert rf_black is not None
    filter_str_black, w, h = rf_black
    assert (w, h) == (1080, 1920)
    assert "pad=1080:1920" in filter_str_black

    # 3. 1:1 Square (1080x1080)
    rf_sq = service.build_reframe_filter("1:1", "blur_pillar")
    assert rf_sq is not None
    _, w_sq, h_sq = rf_sq
    assert (w_sq, h_sq) == (1080, 1080)

    # 4. 16:9 Widescreen (1920x1080)
    rf_wide = service.build_reframe_filter("16:9", "blur_pillar")
    assert rf_wide is not None
    _, w_wide, h_wide = rf_wide
    assert (w_wide, h_wide) == (1920, 1080)


def test_export_9_16_blurred_pillarbox(tmp_path: Path):
    """Verify exporting 16:9 source into 9:16 vertical video with blurred background."""
    video_path = tmp_path / "orig_16_9.mp4"
    audio_path = tmp_path / "timeline.wav"
    out_video = tmp_path / "exported_9_16_blur.mp4"

    make_test_media(video_path, audio_path, width=1280, height=720, duration=2.0)

    service = VideoExportService()
    result = service.export(
        video_path=video_path,
        audio_timeline_path=audio_path,
        output_video_path=out_video,
        expected_duration=2.0,
        aspect_ratio="9:16",
        reframe_mode="blur_pillar",
    )

    assert result.video_path.exists()
    assert result.width == 1080
    assert result.height == 1920
    assert result.aspect_ratio == "9:16"
    assert result.reframe_mode == "blur_pillar"

    # Verify physical file dimensions match 1080x1920
    w, h = get_video_dimensions(out_video)
    assert (w, h) == (1080, 1920)


def test_export_9_16_center_crop(tmp_path: Path):
    """Verify exporting 16:9 source into 9:16 vertical video with center crop."""
    video_path = tmp_path / "orig_16_9.mp4"
    audio_path = tmp_path / "timeline.wav"
    out_video = tmp_path / "exported_9_16_crop.mp4"

    make_test_media(video_path, audio_path, width=1280, height=720, duration=2.0)

    service = VideoExportService()
    result = service.export(
        video_path=video_path,
        audio_timeline_path=audio_path,
        output_video_path=out_video,
        expected_duration=2.0,
        aspect_ratio="9:16",
        reframe_mode="center_crop",
    )

    assert result.video_path.exists()
    assert result.width == 1080
    assert result.height == 1920
    assert result.aspect_ratio == "9:16"

    w, h = get_video_dimensions(out_video)
    assert (w, h) == (1080, 1920)


def test_export_1_1_square(tmp_path: Path):
    """Verify exporting 16:9 source into 1:1 square video with blurred background."""
    video_path = tmp_path / "orig_16_9.mp4"
    audio_path = tmp_path / "timeline.wav"
    out_video = tmp_path / "exported_1_1_sq.mp4"

    make_test_media(video_path, audio_path, width=1280, height=720, duration=2.0)

    service = VideoExportService()
    result = service.export(
        video_path=video_path,
        audio_timeline_path=audio_path,
        output_video_path=out_video,
        expected_duration=2.0,
        aspect_ratio="1:1",
        reframe_mode="blur_pillar",
    )

    assert result.video_path.exists()
    assert result.width == 1080
    assert result.height == 1080
    assert result.aspect_ratio == "1:1"

    w, h = get_video_dimensions(out_video)
    assert (w, h) == (1080, 1080)


def test_export_original_ratio_preserves_dimensions(tmp_path: Path):
    """Verify original aspect ratio retains source video dimensions."""
    video_path = tmp_path / "orig_16_9.mp4"
    audio_path = tmp_path / "timeline.wav"
    out_video = tmp_path / "exported_orig.mp4"

    make_test_media(video_path, audio_path, width=1280, height=720, duration=2.0)

    service = VideoExportService()
    result = service.export(
        video_path=video_path,
        audio_timeline_path=audio_path,
        output_video_path=out_video,
        expected_duration=2.0,
        aspect_ratio="original",
    )

    assert result.video_path.exists()
    assert result.aspect_ratio == "original"

    w, h = get_video_dimensions(out_video)
    assert (w, h) == (1280, 720)


def test_api_export_endpoint_accepts_aspect_ratio_and_reframe(client: TestClient, db_session: Session, tmp_path: Path):
    """Verify POST /api/projects/{id}/export accepts aspect_ratio and reframe_mode parameters."""
    video_path = tmp_path / "proj_video.mp4"
    audio_path = tmp_path / "proj_audio.wav"
    make_test_media(video_path, audio_path, duration=2.0)

    proj = Project(
        id="proj_aspect_ratio_test",
        title="Social Media Reframe Test",
        original_language="en",
        target_language="km",
        status=ProjectStatus.VOICE_GENERATED,
    )
    db_session.add(proj)

    video = Video(
        id="vid_aspect_test",
        project_id=proj.id,
        filename="proj_video.mp4",
        file_path=str(video_path),
        file_size_bytes=video_path.stat().st_size,
        duration_seconds=2.0,
    )
    db_session.add(video)

    tseg = TranscriptSegment(
        id="tseg_ar_1",
        project_id=proj.id,
        segment_order=1,
        start_time=0.2,
        end_time=1.8,
        text="Testing social media reframing for TikTok and Shorts.",
    )
    db_session.add(tseg)

    trans = TranslationSegment(
        id="tr_ar_1",
        project_id=proj.id,
        transcript_segment_id=tseg.id,
        segment_order=1,
        khmer_text="សាកល្បងបម្លែងទម្រង់វីដេអូសម្រាប់ TikTok",
        voice_revision=0,
    )
    db_session.add(trans)

    gen_audio = GeneratedAudio(
        id="ga_ar_1",
        project_id=proj.id,
        translation_segment_id=trans.id,
        audio_path=str(audio_path),
        duration_seconds=1.5,
        provider="edge",
        voice="km-KH-PisethNeural",
        voice_revision=0,
        is_outdated=False,
    )
    db_session.add(gen_audio)
    db_session.commit()

    # Trigger export with aspect_ratio=9:16 and reframe_mode=blur_pillar
    res = client.post(
        f"/api/projects/{proj.id}/export?aspect_ratio=9:16&reframe_mode=blur_pillar"
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["job_type"] == "dub"
    assert data["status"] in ("pending", "running")


def test_export_9_16_combined_with_bgm_ducking(tmp_path: Path):
    """Verify combining background music ducking and 9:16 vertical blurred pillarbox reframing."""
    video_path = tmp_path / "orig_16_9_bgm.mp4"
    audio_path = tmp_path / "timeline_khmer.wav"
    out_video = tmp_path / "exported_9_16_ducked.mp4"

    make_test_media(video_path, audio_path, width=1280, height=720, duration=2.5)

    service = VideoExportService()
    result = service.export(
        video_path=video_path,
        audio_timeline_path=audio_path,
        output_video_path=out_video,
        expected_duration=2.5,
        preserve_bgm=True,
        ducking_preset="balanced",
        bgm_volume=0.30,
        aspect_ratio="9:16",
        reframe_mode="blur_pillar",
    )

    assert result.video_path.exists()
    assert result.width == 1080
    assert result.height == 1920
    assert result.aspect_ratio == "9:16"
    assert result.reframe_mode == "blur_pillar"

    w, h = get_video_dimensions(out_video)
    assert (w, h) == (1080, 1920)
