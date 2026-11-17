"""Unit and integration tests for Viral Burn-In Subtitles
(Khmer Fonts & Styling, ASS generation, bilingual subtitles, and chained FFmpeg rendering).
"""
import json
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy.orm import Session

from app.models.project import (
    GeneratedAudio,
    Project,
    ProjectStatus,
    TranscriptSegment,
    TranslationSegment,
    Video,
)
from app.services.dubbing.exporter import VideoExportService
from app.services.dubbing.pipeline import DubbingPipeline
from app.services.subtitles.generator import (
    ASS_STYLE_PRESETS,
    SubtitleCue,
    format_timestamp_ass,
    generate_ass,
)


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

    cmd_vid = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate=25:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac",
        str(video_path),
    ]
    subprocess.run(cmd_vid, check=True, capture_output=True)

    rate = 48000
    t = np.linspace(0, duration, int(duration * rate), endpoint=False)
    sine = (0.2 * np.sin(2 * np.pi * 550 * t) * 32767).astype("<i2")
    with wave.open(str(audio_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(sine.tobytes())


def get_video_streams_info(video_path: Path) -> dict:
    """Inspect video and audio streams using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=width,height,codec_type,codec_name:format=duration,size",
        "-of", "json",
        str(video_path),
    ]
    res = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(res.stdout)


def test_format_timestamp_ass():
    """Verify millisecond to centisecond formatting for ASS timestamps (H:MM:SS.cs)."""
    assert format_timestamp_ass(0.0) == "0:00:00.00"
    assert format_timestamp_ass(1.5) == "0:00:01.50"
    assert format_timestamp_ass(65.73) == "0:01:05.73"
    assert format_timestamp_ass(3661.05) == "1:01:01.05"
    assert format_timestamp_ass(-5.0) == "0:00:00.00"


def test_generate_ass_presets():
    """Verify ASS subtitle generation with typography presets, safe margins, and Khmer Unicode."""
    cues = [
        SubtitleCue(sequence=1, start_time=0.0, end_time=1.5, text="ជំរាបសួរ អ្នកទាំងអស់គ្នា"),
        SubtitleCue(sequence=2, start_time=1.5, end_time=3.0, text="ស្វាគមន៍មកកាន់ KhmerDub AI"),
    ]

    # 1. TikTok Yellow Preset
    ass_yellow = generate_ass(cues, style_name="tiktok_yellow", play_res_x=1080, play_res_y=1920)
    assert "[Script Info]" in ass_yellow
    assert "PlayResX: 1080" in ass_yellow
    assert "PlayResY: 1920" in ass_yellow
    assert "Khmer OS Battambang" in ass_yellow
    assert "&H0000FFFF" in ass_yellow  # Yellow primary color
    assert "240" in ass_yellow  # Safe zone margin
    assert "Dialogue: 0,0:00:00.00,0:00:01.50,ViralSubtitle,,0,0,0,,ជំរាបសួរ អ្នកទាំងអស់គ្នា" in ass_yellow
    assert "Dialogue: 0,0:00:01.50,0:00:03.00,ViralSubtitle,,0,0,0,,ស្វាគមន៍មកកាន់ KhmerDub AI" in ass_yellow

    # 2. Headline Bold (Khmer OS Muol)
    ass_headline = generate_ass(cues, style_name="headline_bold", play_res_x=1080, play_res_y=1920)
    assert "Khmer OS Muol" in ass_headline
    assert "&H0020D7FF" in ass_headline  # Gold/amber

    # 3. Boxed Black
    ass_boxed = generate_ass(cues, style_name="boxed_black", play_res_x=1080, play_res_y=1920)
    assert ",3," in ass_boxed  # BorderStyle 3 = opaque box

    # 4. Empty cues return empty string
    assert generate_ass([], style_name="tiktok_yellow") == ""


def test_escape_filter_path():
    """Verify FFmpeg filtergraph path escaping for colons and backslashes."""
    p1 = Path("/tmp/video:subtitles.ass")
    escaped = VideoExportService.escape_filter_path(p1)
    assert r"\:" in escaped

    p2 = Path(r"C:\media\test.ass")
    escaped2 = VideoExportService.escape_filter_path(p2)
    assert "\\" not in escaped2.replace(r"\:", "")  # slashes normalized to forward slash


def test_export_with_burned_subtitles_native(tmp_path: Path):
    """Test exporting native video with burned-in stylized Khmer subtitles."""
    video_path = tmp_path / "original.mp4"
    audio_path = tmp_path / "khmer_timeline.wav"
    output_path = tmp_path / "dubbed_with_subs.mp4"
    ass_path = tmp_path / "subtitles.ass"

    make_test_media(video_path, audio_path, width=1280, height=720, duration=2.0)

    cues = [
        SubtitleCue(sequence=1, start_time=0.2, end_time=1.8, text="ជំរាបសួរពី KhmerDub AI"),
    ]
    ass_text = generate_ass(cues, style_name="tiktok_yellow", play_res_x=1280, play_res_y=720)
    ass_path.write_text(ass_text, encoding="utf-8")

    exporter = VideoExportService()
    result = exporter.export(
        video_path=video_path,
        audio_timeline_path=audio_path,
        output_video_path=output_path,
        expected_duration=2.0,
        tolerance_seconds=0.3,
        burn_subtitles=True,
        subtitle_path=ass_path,
    )

    assert output_path.exists()
    assert result.burn_subtitles is True
    assert result.duration_seconds > 0.0

    streams_info = get_video_streams_info(output_path)
    codecs = [s.get("codec_name") for s in streams_info.get("streams", [])]
    assert "h264" in codecs
    assert "aac" in codecs


def test_export_with_burned_subtitles_and_9_16_vertical_reframe(tmp_path: Path):
    """Test combined 9:16 vertical reframe + viral burned-in Khmer subtitles."""
    video_path = tmp_path / "landscape.mp4"
    audio_path = tmp_path / "audio.wav"
    output_path = tmp_path / "vertical_dubbed_with_subs.mp4"
    ass_path = tmp_path / "vertical_subs.ass"

    # 1280x720 16:9 input video
    make_test_media(video_path, audio_path, width=1280, height=720, duration=2.0)

    cues = [
        SubtitleCue(
            sequence=1,
            start_time=0.1,
            end_time=1.9,
            text="វីដេអូខ្លី TikTok ជាមួយ KhmerDub\\N{\\fs34\\i1}Viral TikTok Short with Subtitles",
        ),
    ]
    ass_text = generate_ass(cues, style_name="tiktok_yellow", play_res_x=1080, play_res_y=1920)
    ass_path.write_text(ass_text, encoding="utf-8")

    exporter = VideoExportService()
    result = exporter.export(
        video_path=video_path,
        audio_timeline_path=audio_path,
        output_video_path=output_path,
        expected_duration=2.0,
        tolerance_seconds=0.3,
        aspect_ratio="9:16",
        reframe_mode="blur_pillar",
        burn_subtitles=True,
        subtitle_path=ass_path,
    )

    assert output_path.exists()
    assert result.width == 1080
    assert result.height == 1920
    assert result.burn_subtitles is True

    # Validate output dimensions using ffprobe
    streams_info = get_video_streams_info(output_path)
    for s in streams_info.get("streams", []):
        if s.get("codec_type") == "video":
            assert int(s["width"]) == 1080
            assert int(s["height"]) == 1920


def test_pipeline_run_with_burn_subtitles_bilingual(db_session: Session, tmp_path: Path):
    """Integration test: pipeline end-to-end execution with bilingual subtitle burn-in."""
    proj = Project(
        id="proj_burnin_pipeline_test",
        title="Bilingual Subtitle Test",
        target_language="km",
        pipeline_version="v2",
        status=ProjectStatus.VOICE_GENERATED,
    )
    db_session.add(proj)
    db_session.commit()

    video_path = tmp_path / f"video_{proj.id}.mp4"
    audio_path = tmp_path / f"audio_{proj.id}.wav"
    make_test_media(video_path, audio_path, width=1280, height=720, duration=2.0)

    vid = Video(
        id=f"vid_{proj.id}",
        project_id=proj.id,
        filename="video.mp4",
        file_path=str(video_path),
        file_size_bytes=video_path.stat().st_size,
        duration_seconds=2.0,
        width=1280,
        height=720,
    )
    db_session.add(vid)

    # English transcript segment
    t_seg = TranscriptSegment(
        id=f"tseg_{proj.id}_1",
        project_id=proj.id,
        segment_order=1,
        start_time=0.2,
        end_time=1.8,
        text="Welcome to Phnom Penh.",
    )
    db_session.add(t_seg)
    db_session.flush()

    # Khmer translation segment
    trans_seg = TranslationSegment(
        id=f"tr_{proj.id}_1",
        project_id=proj.id,
        transcript_segment_id=t_seg.id,
        segment_order=1,
        khmer_text="សូមស្វាគមន៍មកកាន់រាជធានីភ្នំពេញ។",
        voice_revision=0,
        is_outdated=False,
    )
    db_session.add(trans_seg)
    db_session.flush()

    # Generated audio
    gen_audio = GeneratedAudio(
        id=f"ga_{proj.id}_1",
        project_id=proj.id,
        translation_segment_id=trans_seg.id,
        audio_path=str(audio_path),
        duration_seconds=1.6,
        provider="edge",
        voice="km-KH-PisethNeural",
        voice_revision=0,
        is_outdated=False,
    )
    db_session.add(gen_audio)
    db_session.commit()

    pipeline = DubbingPipeline()
    result = pipeline.run(
        project_id=proj.id,
        db=db_session,
        burn_subtitles=True,
        subtitle_style="tiktok_yellow",
        subtitle_language="bilingual",
        aspect_ratio="9:16",
        reframe_mode="blur_pillar",
    )

    assert result.export_result.burn_subtitles is True
    assert result.export_result.width == 1080
    assert result.export_result.height == 1920
    assert Path(vid.exported_video_path).exists()


def test_api_export_endpoint_accepts_subtitles(client, db_session: Session, tmp_path: Path):
    """Verify POST /api/projects/{id}/export accepts burn_subtitles, subtitle_style, and subtitle_language."""
    video_path = tmp_path / "endpoint_video.mp4"
    audio_path = tmp_path / "endpoint_audio.wav"
    make_test_media(video_path, audio_path, duration=2.0)

    proj = Project(
        id="proj_api_sub_test",
        title="API Subtitle Test",
        original_language="en",
        target_language="km",
        status=ProjectStatus.VOICE_GENERATED,
    )
    db_session.add(proj)

    video = Video(
        id="vid_api_sub",
        project_id=proj.id,
        filename="endpoint_video.mp4",
        file_path=str(video_path),
        file_size_bytes=video_path.stat().st_size,
        duration_seconds=2.0,
    )
    db_session.add(video)

    tseg = TranscriptSegment(
        id="tseg_api_sub_1",
        project_id=proj.id,
        segment_order=1,
        start_time=0.2,
        end_time=1.8,
        text="Testing social media subtitles API.",
    )
    db_session.add(tseg)

    trans = TranslationSegment(
        id="tr_api_sub_1",
        project_id=proj.id,
        transcript_segment_id=tseg.id,
        segment_order=1,
        khmer_text="សាកល្បង API អក្សររត់",
        voice_revision=0,
    )
    db_session.add(trans)

    gen_audio = GeneratedAudio(
        id="ga_api_sub_1",
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

    resp = client.post(
        f"/api/projects/{proj.id}/export",
        params={
            "burn_subtitles": "true",
            "subtitle_style": "tiktok_yellow",
            "subtitle_language": "bilingual",
            "subtitle_font": "Khmer OS Battambang",
            "aspect_ratio": "9:16",
            "reframe_mode": "blur_pillar",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_type"] == "dub"
    assert data["project_id"] == proj.id


def test_startup_prerequisite_check():
    """Verify startup check passes in valid environment and fails loudly if components are missing."""
    from unittest.mock import patch
    from app.services.subtitles.checker import verify_subtitle_system_prerequisites

    # 1. Normal environment: all prerequisites present
    assert verify_subtitle_system_prerequisites(force=True) is True

    # 2. Missing FFmpeg binary -> raises RuntimeError loudly
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="FFmpeg executable not found"):
            verify_subtitle_system_prerequisites(force=True)

    # 3. Missing HarfBuzz in libass -> raises RuntimeError loudly
    class MockProbeRes:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def mock_subprocess(cmd, *args, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)
        if "-filters" in cmd_str:
            return MockProbeRes(returncode=0, stdout=" ... ass ... V->V Render ASS", stderr="")
        if "lavfi" in cmd_str:
            return MockProbeRes(returncode=0, stdout="Shaper: FriBidi 1.0 (SIMPLE) only", stderr="")
        return MockProbeRes(returncode=0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=mock_subprocess):
        with pytest.raises(RuntimeError, match="HarfBuzz"):
            verify_subtitle_system_prerequisites(force=True)


def test_font_resolution_and_fallback(caplog):
    """Verify font resolution matches installed family names and safely falls back to Noto Sans Khmer."""
    import logging
    from app.services.subtitles.generator import resolve_khmer_font

    # Exact matches
    assert resolve_khmer_font("Khmer OS Battambang") == "Khmer OS Battambang"
    assert resolve_khmer_font("Khmer OS Muol") == "Khmer OS Muol"
    assert resolve_khmer_font("Khmer OS Content") == "Khmer OS Content"

    # Missing or unsupported font -> logs warning and falls back to Noto Sans Khmer
    with caplog.at_level(logging.WARNING):
        resolved = resolve_khmer_font("NonExistentFont123")
        assert resolved == "Noto Sans Khmer"
        assert "lacks verified Khmer coverage" in caplog.text or "not installed" in caplog.text


def test_khmer_text_handling_and_icu_word_wrapping():
    """Verify Khmer text handling: UTF-8 intact, no cluster splitting, ICU word boundary wrapping."""
    from app.services.subtitles.generator import wrap_khmer_cue_text

    # Target sentence with complex subscript consonants (coeng) and vowel marks
    target_sentence = "គណិតវិទ្យាជាភាសាមនុស្សដូចអង់គ្លេសដែរ"

    # Contains coeng clusters: ទ្យា, ស្ស, គ្លេ
    assert "ទ្យា" in target_sentence
    assert "ស្ស" in target_sentence
    assert "គ្លេ" in target_sentence

    # Short sentence should stay intact on one line if <= max_chars
    wrapped_short = wrap_khmer_cue_text(target_sentence, max_chars=40)
    assert r"\N" not in wrapped_short
    assert wrapped_short == target_sentence

    # Long two-line sentence wraps only at word boundaries
    long_sentence = "វិស្វករប្រើគណិតវិទ្យាដើម្បីសាងសង់ហេដ្ឋារចនាសម្ព័ន្ធ និងទូរគមនាគមន៍សម្រាប់បម្រើដល់មនុស្សជាតិ។"
    wrapped_long = wrap_khmer_cue_text(long_sentence, max_chars=38)

    assert r"\N" in wrapped_long
    lines = wrapped_long.split(r"\N")
    assert len(lines) >= 2

    # Verify no cluster was split: each line must be valid UTF-8 and not start with combining mark
    for line in lines:
        stripped = line.strip()
        assert stripped
        # Khmer combining vowels (U+17B6..U+17D3) and signs cannot appear as leading char
        assert ord(stripped[0]) not in range(0x17B6, 0x17D4), f"Line started with combining character: {stripped}"
        # No dotted circle placeholder (U+25CC)
        assert "\u25cc" not in stripped


def test_render_all_presets_and_modes_no_broken_glyphs(tmp_path: Path):
    """Render a frame for each preset (tiktok_yellow, classic_white, boxed_black, headline_bold)
    in km, bilingual, and en modes. Check PNG generation and ensure no dotted-circle glyphs.
    """
    from app.services.subtitles.generator import SubtitleCue, generate_ass
    from app.services.subtitles.checker import get_fonts_dir

    presets = ["tiktok_yellow", "classic_white", "boxed_black", "headline_bold"]
    modes = ["km", "bilingual", "en"]
    fonts_dir = get_fonts_dir()

    s_km = "គណិតវិទ្យាជាភាសាមនុស្សដូចអង់គ្លេសដែរ"
    s_km_long = "វិស្វករប្រើគណិតវិទ្យាដើម្បីសាងសង់ហេដ្ឋារចនាសម្ព័ន្ធ និងទូរគមនាគមន៍សម្រាប់បម្រើដល់មនុស្សជាតិ។"
    s_en = "Mathematics is a human language like English."
    s_en_long = "Engineers use mathematics to construct infrastructure and telecommunications to serve humanity."

    render_dir = tmp_path / "renders"
    render_dir.mkdir(parents=True, exist_ok=True)

    for preset in presets:
        for mode in modes:
            if mode == "km":
                text = s_km + r"\N" + s_km_long
            elif mode == "bilingual":
                text = s_km + r"\N{\i1}" + s_en + r"{\i0}"
            else:
                text = s_en + r"\N" + s_en_long

            # Never include dotted circle in input text
            assert "\u25cc" not in text

            cues = [SubtitleCue(sequence=1, start_time=0.0, end_time=2.0, text=text)]
            ass_content = generate_ass(cues, style_name=preset, play_res_x=1920, play_res_y=1080)
            assert "\u25cc" not in ass_content

            ass_file = render_dir / f"{preset}_{mode}.ass"
            ass_file.write_text(ass_content, encoding="utf-8")
            png_file = render_dir / f"{preset}_{mode}.png"

            # Render single frame with FFmpeg ass filter + fontsdir
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "color=c=black:s=1920x1080:d=0.04",
                "-vf", f"ass={ass_file}:fontsdir={fonts_dir}",
                "-frames:v", "1",
                str(png_file),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            assert res.returncode == 0, f"FFmpeg render failed for {preset} ({mode}): {res.stderr}"
            assert png_file.exists()
            assert png_file.stat().st_size > 5000, f"Rendered frame {png_file} is suspiciously small"

            # Verify image content has visible non-black text pixels via FFmpeg rawvideo and numpy
            rgb_cmd = [
                "ffmpeg", "-v", "error",
                "-i", str(png_file),
                "-f", "rawvideo",
                "-pix_fmt", "rgb24",
                "-",
            ]
            raw_res = subprocess.run(rgb_cmd, capture_output=True, check=True)
            arr = np.frombuffer(raw_res.stdout, dtype=np.uint8).reshape((1080, 1920, 3))
            # Find non-black text pixels (R > 40 or G > 40 or B > 40)
            text_pixels = np.sum((arr[:, :, 0] > 40) | (arr[:, :, 1] > 40) | (arr[:, :, 2] > 40))
            assert text_pixels > 200, f"No subtitle text rendered in {preset} ({mode})"


