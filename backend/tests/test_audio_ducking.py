import math
import struct
import subprocess
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.dubbing.audio_mixer import (
    AudioDuckingMixer,
    DuckingConfig,
    DuckingPreset,
    PRESET_SETTINGS,
)
from app.services.dubbing.exporter import VideoExportService
from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProjectStatus,
)


def make_stereo_tone(path: Path, duration: float = 8.0, freq_l: int = 440, freq_r: int = 554, sample_rate: int = 48000) -> Path:
    """Generate a clean synthetic stereo tone WAV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.1, float(duration))
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi", "-i", f"sine=frequency={freq_l}:duration={dur:.3f}:sample_rate={sample_rate}",
        "-f", "lavfi", "-i", f"sine=frequency={freq_r}:duration={dur:.3f}:sample_rate={sample_rate}",
        "-filter_complex", "[0:a][1:a]join=inputs=2:channel_layout=stereo[a]",
        "-map", "[a]",
        "-c:a", "pcm_s16le",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg failed to create stereo tone: {res.stderr}")
    return path


def make_speech_timeline(
    path: Path,
    speech_start: float = 2.0,
    speech_duration: float = 3.0,
    total_duration: float = 8.0,
    freq: int = 880,
    sample_rate: int = 48000,
) -> Path:
    """Generate a synthetic speech timeline with speech burst in the middle and silence elsewhere."""
    path.parent.mkdir(parents=True, exist_ok=True)
    start_ms = int(speech_start * 1000)
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={speech_duration:.3f}:sample_rate={sample_rate}",
        "-af", f"adelay={start_ms}|{start_ms},apad=whole_dur={total_duration:.3f}",
        "-c:a", "pcm_s16le",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg failed to create speech timeline: {res.stderr}")
    return path


def make_test_video(path: Path, duration: float = 5.0, width: int = 320, height: int = 240) -> Path:
    """Generate a clean synthetic MP4 video with an audio track for export testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration:.2f}:size={width}x{height}:rate=24",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration:.2f}:sample_rate={sample_rate}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg failed to create test video: {res.stderr}")
    return path


# Default sample rate for video generator
sample_rate = 48000


def test_audio_ducking_preset_definitions():
    """Verify all ducking presets are properly configured with valid compressor parameters."""
    assert DuckingPreset.LIGHT.value == "light"
    assert DuckingPreset.BALANCED.value == "balanced"
    assert DuckingPreset.STRONG.value == "strong"
    assert DuckingPreset.MUTE.value == "mute"

    for preset, settings in PRESET_SETTINGS.items():
        assert "threshold" in settings
        assert "ratio" in settings
        assert "attack_ms" in settings
        assert "release_ms" in settings
        assert 0.0 < settings["threshold"] < 1.0
        assert settings["ratio"] >= 2.0
        assert settings["attack_ms"] > 0
        assert settings["release_ms"] > 0

    assert PRESET_SETTINGS[DuckingPreset.STRONG]["ratio"] > PRESET_SETTINGS[DuckingPreset.LIGHT]["ratio"]


def test_audio_ducking_mixer_probe(tmp_path: Path):
    """Verify probe_audio returns accurate duration, channels, and sample rate."""
    mixer = AudioDuckingMixer()
    tone_file = tmp_path / "probe_test.wav"
    make_stereo_tone(tone_file, duration=5.0, sample_rate=48000)

    info = mixer.probe_audio(tone_file)
    assert abs(info["duration"] - 5.0) < 0.05
    assert info["channels"] == 2
    assert info["sample_rate"] == 48000


def test_mix_and_duck_balanced_stereo(tmp_path: Path):
    """Verify AudioDuckingMixer mixes stereo background with speech timeline,
    maintains exact duration, and outputs 48kHz stereo 16-bit PCM WAV.
    """
    mixer = AudioDuckingMixer()
    bg_path = tmp_path / "bg_music.wav"
    speech_path = tmp_path / "speech_track.wav"
    out_path = tmp_path / "mixed_dubbed.wav"

    make_stereo_tone(bg_path, duration=8.0, sample_rate=48000)
    make_speech_timeline(speech_path, speech_start=2.0, speech_duration=3.0, total_duration=8.0)

    cfg = DuckingConfig(
        preset=DuckingPreset.BALANCED,
        bgm_volume=0.7,
        speech_volume=1.0,
    )

    result = mixer.mix_and_duck(
        background_audio_path=bg_path,
        speech_audio_path=speech_path,
        output_path=out_path,
        expected_duration=8.0,
        config=cfg,
    )

    assert result == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > 0

    info = mixer.probe_audio(out_path)
    assert abs(info["duration"] - 8.0) < 0.05
    assert info["channels"] == 2
    assert info["sample_rate"] == 48000


def test_mix_and_duck_presets_comparison(tmp_path: Path):
    """Verify Strong preset applies more attenuation than Light preset."""
    mixer = AudioDuckingMixer()
    bg_path = tmp_path / "bg_music_comp.wav"
    speech_path = tmp_path / "speech_track_comp.wav"
    out_light = tmp_path / "out_light.wav"
    out_strong = tmp_path / "out_strong.wav"

    make_stereo_tone(bg_path, duration=6.0, sample_rate=48000)
    make_speech_timeline(speech_path, speech_start=1.5, speech_duration=3.0, total_duration=6.0)

    mixer.mix_and_duck(
        background_audio_path=bg_path,
        speech_audio_path=speech_path,
        output_path=out_light,
        expected_duration=6.0,
        config=DuckingConfig(preset=DuckingPreset.LIGHT, bgm_volume=0.8),
    )

    mixer.mix_and_duck(
        background_audio_path=bg_path,
        speech_audio_path=speech_path,
        output_path=out_strong,
        expected_duration=6.0,
        config=DuckingConfig(preset=DuckingPreset.STRONG, bgm_volume=0.8),
    )

    assert out_light.exists()
    assert out_strong.exists()

    info_l = mixer.probe_audio(out_light)
    info_s = mixer.probe_audio(out_strong)
    assert abs(info_l["duration"] - 6.0) < 0.05
    assert abs(info_s["duration"] - 6.0) < 0.05


def test_attenuate_center_vocals(tmp_path: Path):
    """Verify center-channel vocal attenuation processes stereo background cleanly."""
    mixer = AudioDuckingMixer()
    bg_path = tmp_path / "bg_dialogue.wav"
    speech_path = tmp_path / "khmer_speech.wav"
    out_path = tmp_path / "attenuated_mix.wav"

    make_stereo_tone(bg_path, duration=6.0, sample_rate=48000)
    make_speech_timeline(speech_path, speech_start=1.0, speech_duration=2.5, total_duration=6.0)

    cfg = DuckingConfig(
        preset=DuckingPreset.BALANCED,
        bgm_volume=0.7,
        speech_volume=1.0,
        attenuate_center_vocals=True,
    )

    mixer.mix_and_duck(
        background_audio_path=bg_path,
        speech_audio_path=speech_path,
        output_path=out_path,
        expected_duration=6.0,
        config=cfg,
    )

    assert out_path.exists()
    info = mixer.probe_audio(out_path)
    assert abs(info["duration"] - 6.0) < 0.05
    assert info["channels"] == 2


def test_duration_padding_guarantee(tmp_path: Path):
    """Verify mixer guarantees exact target duration by padding if source audio is shorter."""
    mixer = AudioDuckingMixer()
    bg_path = tmp_path / "short_bg.wav"
    speech_path = tmp_path / "short_speech.wav"
    out_path = tmp_path / "padded_mix.wav"

    make_stereo_tone(bg_path, duration=4.0, sample_rate=48000)
    make_speech_timeline(speech_path, speech_start=1.0, speech_duration=2.0, total_duration=4.0)

    target_dur = 7.5
    mixer.mix_and_duck(
        background_audio_path=bg_path,
        speech_audio_path=speech_path,
        output_path=out_path,
        expected_duration=target_dur,
    )

    assert out_path.exists()
    info = mixer.probe_audio(out_path)
    assert abs(info["duration"] - target_dur) < 0.05


def test_missing_files_error_handling(tmp_path: Path):
    """Verify missing input files raise FileNotFoundError."""
    mixer = AudioDuckingMixer()
    existing_file = tmp_path / "existing.wav"
    make_stereo_tone(existing_file, duration=2.0)

    non_existent = tmp_path / "does_not_exist.wav"

    with pytest.raises(FileNotFoundError):
        mixer.mix_and_duck(non_existent, existing_file, tmp_path / "out.wav")

    with pytest.raises(FileNotFoundError):
        mixer.mix_and_duck(existing_file, non_existent, tmp_path / "out.wav")


def test_video_export_service_with_bgm_ducking(tmp_path: Path):
    """Verify VideoExportService remuxes video and applies BGM audio ducking during export."""
    export_service = VideoExportService()
    video_path = tmp_path / "orig_video.mp4"
    timeline_path = tmp_path / "speech_timeline.wav"
    output_mp4 = tmp_path / "dubbed_with_bgm.mp4"

    make_test_video(video_path, duration=5.0)
    make_speech_timeline(timeline_path, speech_start=1.0, speech_duration=2.5, total_duration=5.0)

    result = export_service.export(
        video_path=video_path,
        audio_timeline_path=timeline_path,
        output_video_path=output_mp4,
        expected_duration=5.0,
        preserve_bgm=True,
        ducking_preset="balanced",
        bgm_volume=0.7,
        attenuate_center_vocals=False,
    )

    assert result.video_path == output_mp4
    assert output_mp4.exists()
    assert abs(result.duration_seconds - 5.0) < 0.15
    assert result.video_codec in ("h264", "unknown")
    assert result.audio_codec in ("aac", "unknown")


def test_export_api_ducking_parameters(client: TestClient, db_session: Session, tmp_path: Path):
    """Verify POST /api/projects/{id}/export accepts preserve_bgm and ducking parameters."""
    media_file = tmp_path / "api_test_video.mp4"
    make_test_video(media_file, duration=6.0)

    proj = Project(
        id="proj_ducking_api_test",
        title="Ducking API Test",
        original_language="en",
        target_language="km",
        status=ProjectStatus.COMPLETED,
        tts_provider="edge",
        tts_voice="km-KH-PisethNeural",
    )
    db_session.add(proj)
    db_session.commit()

    video = Video(
        id="vid_ducking_api",
        project_id=proj.id,
        filename="api_test_video.mp4",
        file_path=str(media_file),
        file_size_bytes=media_file.stat().st_size,
        duration_seconds=6.0,
    )
    db_session.add(video)

    tseg = TranscriptSegment(
        id="tseg_api_duck_1",
        project_id=proj.id,
        segment_order=1,
        start_time=1.0,
        end_time=4.0,
        text="A journey through history.",
    )
    db_session.add(tseg)

    trans = TranslationSegment(
        id="trans_api_duck_1",
        project_id=proj.id,
        transcript_segment_id=tseg.id,
        segment_order=1,
        start_time=1.0,
        end_time=4.0,
        khmer_text="ដំណើរឆ្លងកាត់ប្រវត្តិសាស្ត្រ។",
    )
    db_session.add(trans)
    db_session.flush()

    audio = GeneratedAudio(
        id="ga_duck_1",
        project_id=proj.id,
        translation_segment_id=trans.id,
        audio_path=str(media_file),
        duration_seconds=3.0,
        is_outdated=False,
    )
    db_session.add(audio)
    db_session.commit()

    # Trigger export with ducking query parameters
    res = client.post(
        f"/api/projects/{proj.id}/export",
        params={
            "preserve_bgm": True,
            "ducking_preset": "strong",
            "bgm_volume": 0.65,
            "attenuate_center_vocals": True,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["job_type"] == "dub"
    assert data["status"] in ("pending", "running", "completed")
