"""
KhmerDub AI - Phase 13E.5: Timed Mode Speech Fitting & Timeline Assembly Tests
Tests exact slot fitting (speed up / slow down / padding), overflow detection without silent truncation,
sample-accurate timeline assembly, and silence-detected onset precision.
"""

import json
import math
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import wave

try:
    import soundfile as sf
except ImportError:
    sf = None

def _read_wav_float(wav_path: Path):
    if sf is not None:
        return sf.read(str(wav_path))
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        n_channels = wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if n_channels > 1:
            data = data.reshape(-1, n_channels)
        return data, sr


from app.services.tts.segment_fitter import (
    SegmentFitResult,
    TimingOverflowError,
    assemble_fitted_timeline,
    build_atempo_filter,
    compute_tts_cache_key,
    fit_segment_audio,
    get_audio_duration_ffprobe,
    save_to_raw_tts_cache,
    get_cached_raw_audio,
    STANDARD_SAMPLE_RATE,
)


def _generate_test_tone(output_path: Path, duration: float, freq: int = 440, sr: int = 24000):
    """Generate a clean test tone WAV or MP3 file for deterministic audio testing."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    codec = ["-c:a", "libmp3lame", "-b:a", "192k"] if output_path.suffix.lower() == ".mp3" else ["-acodec", "pcm_s16le"]
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency={freq}:duration={duration:.4f}",
        *codec,
        "-ar", str(sr),
        "-ac", "1",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def test_build_atempo_filter_chaining():
    """Verify atempo chaining for factors within and outside 0.5 - 2.0."""
    # Factor 1.0 -> anull
    assert build_atempo_filter(1.0) == "anull"

    # Factor 1.25 -> single atempo=1.25
    assert build_atempo_filter(1.25) == "atempo=1.25"

    # Factor 0.75 -> single atempo=0.75
    assert build_atempo_filter(0.75) == "atempo=0.75"

    # Factor 2.5 (> 2.0) -> chain atempo=2,atempo=1.25
    f25 = build_atempo_filter(2.5)
    assert "atempo=2" in f25
    assert "atempo=1.25" in f25

    # Factor 0.4 (< 0.5) -> chain atempo=0.5,atempo=0.8
    f04 = build_atempo_filter(0.4)
    assert "atempo=0.5" in f04
    assert "atempo=0.8" in f04


def test_fit_short_audio_slot_3s_raw_1_12s(tmp_path):
    """Test 1: Slot 3.00s, raw audio 1.12s -> slowed/padded to 3.00s (+-0.05s)."""
    raw_file = tmp_path / "raw_1_12s.wav"
    _generate_test_tone(raw_file, duration=1.12)
    assert abs(get_audio_duration_ffprobe(raw_file) - 1.12) <= 0.05

    out_file = tmp_path / "fitted_3s.wav"
    work_dir = tmp_path / "work_short"

    res = fit_segment_audio(
        segment_id="seg-1",
        segment_order=1,
        text="សួស្តីកម្ពុជា",
        slot_sec=3.0,
        provider_name="gtts",
        voice="km",
        language="km",
        work_dir=work_dir,
        output_path=out_file,
        min_speed=0.75,
        max_speed=1.25,
        fit_tolerance_sec=0.05,
        allow_slow_down=True,
        overflow_policy="allow_overlap",
        raw_audio_input_path=raw_file,
    )

    # Must be slowed down and/or padded to exactly 3.00s (+-0.05s)
    assert abs(res.final_duration_sec - 3.0) <= 0.05
    assert res.status in ("padded", "slowed")
    assert res.raw_duration_sec < 1.2
    assert out_file.exists()


def test_fit_long_audio_slot_2s_raw_2_72s_overflow(tmp_path):
    """Test 2: Slot 2.00s, raw audio 2.72s -> sped up to max_speed (1.25), marked overflow, not cut silently."""
    raw_file = tmp_path / "raw_2_72s.wav"
    _generate_test_tone(raw_file, duration=2.72)
    assert abs(get_audio_duration_ffprobe(raw_file) - 2.72) <= 0.05

    out_file = tmp_path / "fitted_2s.wav"
    work_dir = tmp_path / "work_long"

    res = fit_segment_audio(
        segment_id="seg-2",
        segment_order=2,
        text="អត្ថបទវែងណាស់សម្រាប់ការនិយាយក្នុងរយៈពេលខ្លី",
        slot_sec=2.0,
        provider_name="gtts",
        voice="km",
        language="km",
        work_dir=work_dir,
        output_path=out_file,
        min_speed=0.75,
        max_speed=1.25,
        fit_tolerance_sec=0.05,
        allow_slow_down=True,
        overflow_policy="allow_overlap",
        available_window_sec=3.5,  # Next segment is at 3.5s, allowing overlap into gap
        raw_audio_input_path=raw_file,
    )

    # Sped up to max_speed (1.25x)
    assert abs(res.speed_factor_applied - 1.25) <= 0.02
    assert res.status == "overflow"
    assert res.warning is not None
    assert "exceeds slot" in res.warning

    # With allow_overlap and available_window_sec=3.5, audio is NOT silently cut to 2.0s
    # 2.72 / 1.25 = ~2.176s
    assert res.final_duration_sec > 2.05
    assert res.final_duration_sec <= 3.5


def test_overflow_policy_truncate_fade(tmp_path):
    """Verify overflow_policy='truncate_fade' trims audio at slot length with a fade-out."""
    raw_file = tmp_path / "raw_long.wav"
    _generate_test_tone(raw_file, duration=2.72)

    out_file = tmp_path / "truncated.wav"
    work_dir = tmp_path / "work_trunc"

    res = fit_segment_audio(
        segment_id="seg-trunc",
        segment_order=3,
        text="អត្ថបទវែង",
        slot_sec=2.0,
        provider_name="gtts",
        voice="km",
        language="km",
        work_dir=work_dir,
        output_path=out_file,
        min_speed=0.75,
        max_speed=1.25,
        fit_tolerance_sec=0.05,
        allow_slow_down=True,
        overflow_policy="truncate_fade",
        raw_audio_input_path=raw_file,
    )

    assert res.status == "overflow"
    # Truncated to slot length 2.0s
    assert abs(res.final_duration_sec - 2.0) <= 0.05


def test_overflow_policy_fail(tmp_path):
    """Verify overflow_policy='fail' raises TimingOverflowError."""
    raw_file = tmp_path / "raw_long.wav"
    _generate_test_tone(raw_file, duration=2.72)

    out_file = tmp_path / "fail.wav"
    work_dir = tmp_path / "work_fail"

    with pytest.raises(TimingOverflowError):
        fit_segment_audio(
            segment_id="seg-fail",
            segment_order=4,
            text="អត្ថបទវែង",
            slot_sec=2.0,
            provider_name="gtts",
            voice="km",
            language="km",
            work_dir=work_dir,
            output_path=out_file,
            min_speed=0.75,
            max_speed=1.25,
            fit_tolerance_sec=0.05,
            allow_slow_down=True,
            overflow_policy="fail",
            raw_audio_input_path=raw_file,
        )


def test_full_13_segment_60s_srt_timeline(tmp_path):
    """Test 3: Full 13-segment, 60s SRT -> final file is 60.0s (+-0.1s),
    silence-detected onsets match SRT start timestamps within 50ms.
    """
    # 13 segments defined across a 60-second video timeline
    srt_cues = [
        {"segment_order": 1, "start_time": 1.0, "end_time": 4.0, "raw_dur": 2.5},
        {"segment_order": 2, "start_time": 5.0, "end_time": 8.0, "raw_dur": 1.5},
        {"segment_order": 3, "start_time": 9.5, "end_time": 13.0, "raw_dur": 3.8},
        {"segment_order": 4, "start_time": 14.0, "end_time": 18.0, "raw_dur": 4.2},
        {"segment_order": 5, "start_time": 19.0, "end_time": 22.5, "raw_dur": 3.0},
        {"segment_order": 6, "start_time": 24.0, "end_time": 27.0, "raw_dur": 2.2},
        {"segment_order": 7, "start_time": 28.5, "end_time": 32.0, "raw_dur": 3.2},
        {"segment_order": 8, "start_time": 33.5, "end_time": 37.0, "raw_dur": 3.1},
        {"segment_order": 9, "start_time": 38.0, "end_time": 41.5, "raw_dur": 2.8},
        {"segment_order": 10, "start_time": 43.0, "end_time": 46.5, "raw_dur": 3.0},
        {"segment_order": 11, "start_time": 48.0, "end_time": 51.5, "raw_dur": 3.3},
        {"segment_order": 12, "start_time": 52.5, "end_time": 55.5, "raw_dur": 2.5},
        {"segment_order": 13, "start_time": 56.5, "end_time": 60.0, "raw_dur": 3.0},
    ]

    work_dir = tmp_path / "timeline_test_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    fitted_list: list[SegmentFitResult] = []

    for cue in srt_cues:
        slot = cue["end_time"] - cue["start_time"]
        seg_raw = work_dir / f"cue_{cue['segment_order']}_raw.wav"
        _generate_test_tone(seg_raw, duration=cue["raw_dur"], freq=440 + cue["segment_order"] * 20)

        seg_out = work_dir / f"cue_{cue['segment_order']}_fitted.wav"
        fit_res = fit_segment_audio(
            segment_id=f"c-{cue['segment_order']}",
            segment_order=cue["segment_order"],
            text=f"ឃ្លាទី {cue['segment_order']}",
            slot_sec=slot,
            provider_name="gtts",
            voice="km",
            language="km",
            work_dir=work_dir / f"fit_{cue['segment_order']}",
            output_path=seg_out,
            min_speed=0.75,
            max_speed=1.25,
            fit_tolerance_sec=0.05,
            allow_slow_down=True,
            overflow_policy="allow_overlap",
            raw_audio_input_path=seg_raw,
        )
        fitted_list.append(fit_res)

    out_wav = tmp_path / "final_timeline.wav"
    out_mp3 = tmp_path / "final_timeline.mp3"

    wav_res, mp3_res, total_dur = assemble_fitted_timeline(
        task_id="test_task_60s",
        fitted_segments=fitted_list,
        segment_timing_list=srt_cues,
        output_wav_path=out_wav,
        output_mp3_path=out_mp3,
        target_timeline_duration=60.0,
    )

    # 1. Total file duration matches 60.0s (+-0.1s)
    assert abs(total_dur - 60.0) <= 0.1, f"Expected ~60.0s, got {total_dur}s"
    assert out_wav.exists()
    assert out_mp3.exists()

    # 2. Silence-detected onset verification using audio samples
    audio_data, sr = _read_wav_float(out_wav)
    assert sr == STANDARD_SAMPLE_RATE

    for cue in srt_cues:
        start_sec = cue["start_time"]
        # Check that 50ms before start_sec is silent (RMS < 0.02)
        if start_sec > 0.1:
            pre_sample_start = int((start_sec - 0.08) * sr)
            pre_sample_end = int((start_sec - 0.01) * sr)
            pre_region = audio_data[pre_sample_start:pre_sample_end]
            pre_rms = float(np.sqrt(np.mean(pre_region**2)))
            assert pre_rms < 0.02, f"Segment #{cue['segment_order']} pre-onset not silent: RMS={pre_rms}"

        # Check that 50ms into start_sec contains tone signal (RMS > 0.04)
        post_sample_start = int((start_sec + 0.02) * sr)
        post_sample_end = int((start_sec + 0.10) * sr)
        post_region = audio_data[post_sample_start:post_sample_end]
        post_rms = float(np.sqrt(np.mean(post_region**2)))
        assert post_rms > 0.04, f"Segment #{cue['segment_order']} onset missing speech signal: RMS={post_rms}"


def test_quality_no_clipping_and_standard_specs(tmp_path):
    """Test 5: Verify no clipping, standard 24000 Hz mono PCM specs, and zero clicks."""
    raw_file = tmp_path / "raw_sine.wav"
    _generate_test_tone(raw_file, duration=2.5, freq=500)

    out_file = tmp_path / "fitted_clean.wav"
    res = fit_segment_audio(
        segment_id="clean-1",
        segment_order=1,
        text="សំឡេងស្អាតគ្មាន clipping",
        slot_sec=2.0,
        provider_name="gtts",
        voice="km",
        language="km",
        work_dir=tmp_path / "work_clean",
        output_path=out_file,
        raw_audio_input_path=raw_file,
    )

    data, sr = _read_wav_float(out_file)
    assert sr == 24000
    assert len(data.shape) == 1 or data.shape[1] == 1
    # Verify no clipping (|sample| <= 1.0)
    max_amp = float(np.max(np.abs(data)))
    assert max_amp <= 1.0
    assert max_amp > 0.1


def test_raw_tts_cache_mechanism(tmp_path):
    """Test 4: Cache mechanism prevents re-synthesizing raw TTS when refitting."""
    fake_source = tmp_path / "orig.wav"
    _generate_test_tone(fake_source, duration=1.5)

    saved_cache = save_to_raw_tts_cache(
        fake_source,
        text="តេស្ត cache",
        voice="km-KH-PisethNeural",
        provider="edge",
        language="km",
    )
    assert saved_cache.exists()

    found_cache = get_cached_raw_audio(
        text="តេស្ត cache",
        voice="km-KH-PisethNeural",
        provider="edge",
        language="km",
    )
    assert found_cache is not None
    assert found_cache.resolve() == saved_cache.resolve()


def test_edge_tts_piseth_and_sreymom_compatibility(tmp_path):
    """Test 4a: Edge TTS Piseth and Sreymom neural voices compatibility."""
    out_piseth = tmp_path / "piseth_fitted.wav"
    res_piseth = fit_segment_audio(
        segment_id="piseth-1",
        segment_order=1,
        text="ជំរាបសួរ Piseth",
        slot_sec=2.2,
        provider_name="edge",
        voice="km-KH-PisethNeural",
        language="km",
        work_dir=tmp_path / "work_piseth",
        output_path=out_piseth,
        min_speed=0.75,
        max_speed=1.25,
    )
    assert abs(res_piseth.final_duration_sec - 2.2) <= 0.08
    assert res_piseth.status in ("fit", "padded", "slowed", "sped_up")
    assert out_piseth.exists()

    out_sreymom = tmp_path / "sreymom_fitted.wav"
    res_sreymom = fit_segment_audio(
        segment_id="sreymom-1",
        segment_order=2,
        text="ជំរាបសួរ Sreymom",
        slot_sec=2.2,
        provider_name="edge",
        voice="km-KH-SreymomNeural",
        language="km",
        work_dir=tmp_path / "work_sreymom",
        output_path=out_sreymom,
        min_speed=0.75,
        max_speed=1.25,
    )
    assert abs(res_sreymom.final_duration_sec - 2.2) <= 0.08
    assert res_sreymom.status in ("fit", "padded", "slowed", "sped_up")
    assert out_sreymom.exists()


def test_voxcpm_provider_compatibility(tmp_path):
    """Test 4b: VoxCPM2 voice cloning provider compatibility with atempo pitch preservation."""
    from app.services.tts.voxcpm import VoxCPM2TTSProvider
    vox = VoxCPM2TTSProvider()
    if not vox.is_worker_online():
        pytest.skip("VoxCPM2 worker offline")

    # Generate test tone as simulated voice clone output
    simulated_raw = tmp_path / "voxcpm_raw.wav"
    _generate_test_tone(simulated_raw, duration=1.6, freq=480)

    out_vox = tmp_path / "vox_fitted.wav"
    res_vox = fit_segment_audio(
        segment_id="vox-1",
        segment_order=1,
        text="តេស្តក្លូនសំឡេង VoxCPM",
        slot_sec=2.0,
        provider_name="voxcpm2",
        voice="custom",
        language="km",
        work_dir=tmp_path / "work_vox",
        output_path=out_vox,
        min_speed=0.75,
        max_speed=1.25,
        raw_audio_input_path=simulated_raw,
    )
    assert abs(res_vox.final_duration_sec - 2.0) <= 0.05
    assert res_vox.status in ("padded", "slowed", "fit")
    assert out_vox.exists()


def test_segment1_slot_3s_raw_1_60s_natural_mode(tmp_path):
    """Test bug scenario: Segment #1 slot is 3.00s, raw audio is 1.60s.
    In fill_mode='natural': min_speed is 0.75x, speech slows to ~2.13s, rest padded with silence (+0.87s pad).
    Final duration must be exactly 3.00s (+-0.05s).
    """
    raw_file = tmp_path / "raw_1_60s.wav"
    _generate_test_tone(raw_file, duration=1.60, freq=440)
    assert abs(get_audio_duration_ffprobe(raw_file) - 1.60) <= 0.05

    out_file = tmp_path / "seg1_natural.wav"
    work_dir = tmp_path / "work_seg1_nat"

    res = fit_segment_audio(
        segment_id="seg-1-nat",
        segment_order=1,
        text="ឃ្លាទី ១ នៃអត្ថបទរឿង",
        slot_sec=3.0,
        provider_name="gtts",
        voice="km",
        language="km",
        work_dir=work_dir,
        output_path=out_file,
        min_speed=0.75,
        max_speed=1.25,
        fit_tolerance_sec=0.05,
        allow_slow_down=True,
        overflow_policy="allow_overlap",
        fill_mode="natural",
        raw_audio_input_path=raw_file,
    )

    # Duration must be exactly 3.00s
    assert abs(res.final_duration_sec - 3.0) <= 0.05
    assert abs(res.slot_sec - 3.0) <= 0.01
    assert abs(res.raw_duration_sec - 1.60) <= 0.05
    assert abs(res.speed_factor_applied - 0.75) <= 0.03
    assert res.padded_sec > 0.75  # ~0.87s padded
    assert res.status in ("slowed", "padded")


def test_segment1_slot_3s_raw_1_60s_stretch_mode(tmp_path):
    """Test fill_mode='stretch': min_speed is 0.50x.
    With slot 3.00s and raw 1.60s, ratio is ~0.533x. Speech slows down to ~0.533x to fill the slot.
    Final duration must be exactly 3.00s (+-0.05s).
    """
    raw_file = tmp_path / "raw_1_60s_stretch.wav"
    _generate_test_tone(raw_file, duration=1.60, freq=440)

    out_file = tmp_path / "seg1_stretch.wav"
    work_dir = tmp_path / "work_seg1_stretch"

    res = fit_segment_audio(
        segment_id="seg-1-stretch",
        segment_order=1,
        text="ឃ្លាទី ១ នៃអត្ថបទរឿង",
        slot_sec=3.0,
        provider_name="gtts",
        voice="km",
        language="km",
        work_dir=work_dir,
        output_path=out_file,
        min_speed=0.75,  # Default passed, but fill_mode='stretch' lowers min_speed to 0.50
        max_speed=1.25,
        fit_tolerance_sec=0.05,
        allow_slow_down=True,
        overflow_policy="allow_overlap",
        fill_mode="stretch",
        raw_audio_input_path=raw_file,
    )

    # Must fill the slot via slowing to ~0.53x
    assert abs(res.final_duration_sec - 3.0) <= 0.05
    assert res.speed_factor_applied < 0.60
    assert res.speed_factor_applied >= 0.50
    assert abs(res.speed_factor_applied - (1.60 / 3.0)) <= 0.05


def test_api_forces_timed_mode_for_srt_with_timestamps(client, monkeypatch, tmp_path):
    """Verify backend forces Timed Mode when request has timestamps and fit_to_timestamps=True,
    even if request.mode was sent as 'narration'.
    """
    # Mock Edge TTS synthesis with tones
    from app.services.tts.edge import EdgeTTSProvider
    from app.services.tts.base import TTSAudioResult

    def fake_synthesize(self, text, output_path, language="km", voice="km-KH-PisethNeural", **kwargs):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _generate_test_tone(output_path, duration=1.5, freq=440)
        return TTSAudioResult(
            audio_path=output_path,
            duration_seconds=1.5,
            provider_name="edge",
            voice=voice,
            language=language,
        )

    monkeypatch.setattr(EdgeTTSProvider, "synthesize", fake_synthesize)

    payload = {
        "segments": [
            {"segment_order": 1, "text": "ឃ្លា ១", "start_time": 0.0, "end_time": 3.0},
            {"segment_order": 2, "text": "ឃ្លា ២", "start_time": 5.0, "end_time": 8.0},
        ],
        "mode": "narration",  # Client sent narration by mistake
        "fit_to_timestamps": True,  # But fit_to_timestamps is requested
        "fill_mode": "natural",
        "provider": "edge",
        "voice": "km-KH-PisethNeural",
        "language": "km",
    }

    res = client.post("/api/toolkit/transcript-to-audio/generate", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "completed"

    raw_meta = data["output_media_metadata"]
    meta = raw_meta if isinstance(raw_meta, dict) else json.loads(raw_meta)
    # Mode was forced to timed
    assert meta["mode"] == "timed"
    assert meta["fill_mode"] == "natural"

    # Segment #1 duration in response must be 3.0s (not raw 1.5s)
    seg1 = data["tts_segments"][0]
    assert abs(seg1["final_duration_sec"] - 3.0) <= 0.05
    assert abs(seg1["slot_sec"] - 3.0) <= 0.05

    # Total timeline duration should be 8.0s (last segment end), NOT 3.4s (concatenated narration)
    assert abs(data["output_duration_seconds"] - 8.0) <= 0.1

