"""Unit and integration tests for Emotion & Acting Style Control (Drama / TVB, Storytelling, Explain, etc.)."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.services.tts.emotions import (
    EMOTION_STYLES,
    get_emotion_style,
    list_emotion_styles,
    resolve_prosody,
)
from app.services.translation.prompts import (
    build_single_translation_prompt,
    build_batch_translation_prompt,
    get_translation_style_info,
)
from app.services.tts.edge import EdgeTTSProvider


client = TestClient(app)


def test_emotion_styles_catalog_completeness():
    """Verify that all user-requested and essential acting styles exist in the catalog."""
    expected_styles = [
        "calm",
        "storytelling",
        "explain",
        "angry",
        "happy",
        "sad",
        "dramatic_tvb",
        "whisper",
        "excited",
        "fearful",
        "romantic",
        "humorous",
        "documentary",
        "news",
    ]
    styles = list_emotion_styles()
    style_ids = [s["id"] for s in styles]

    for expected in expected_styles:
        assert expected in style_ids, f"Expected emotion style '{expected}' missing from catalog"
        style_data = get_emotion_style(expected)
        assert style_data["id"] == expected
        assert len(style_data["label_km"]) > 0
        assert len(style_data["label_en"]) > 0
        assert "prosody" in style_data
        assert "rate" in style_data["prosody"]
        assert "pitch" in style_data["prosody"]
        assert "volume" in style_data["prosody"]
        assert "translation_guidance" in style_data


def test_resolve_prosody_presets_and_overrides():
    """Verify prosody resolution for presets, explicit parameters, and rate factor."""
    # 1. Preset check for storytelling
    rate, pitch, volume = resolve_prosody("storytelling")
    assert rate == "-10%"
    assert pitch == "-2Hz"
    assert volume == "+5%"

    # 2. Preset check for angry
    rate, pitch, volume = resolve_prosody("angry")
    assert rate == "+15%"
    assert pitch == "+15Hz"
    assert volume == "+30%"

    # 3. Explicit parameter override
    rate, pitch, volume = resolve_prosody("storytelling", rate="+20%", pitch="+10Hz", volume="+40%")
    assert rate == "+20%"
    assert pitch == "+10Hz"
    assert volume == "+40%"

    # 4. Rate factor conversion
    rate, pitch, volume = resolve_prosody("calm", rate_factor=1.25)
    assert rate == "+25%"


def test_translation_prompt_emotion_style_conditioning():
    """Verify that translation prompts inherit the correct Cambodian emotion register instructions."""
    # Storytelling
    prompt_story = build_single_translation_prompt("Once upon a time in a small village...", style="storytelling")
    assert "និទានរឿង" in prompt_story
    assert "Storytelling" in prompt_story

    # Dramatic TVB
    prompt_tvb = build_single_translation_prompt("You cannot defeat me today!", style="dramatic_tvb")
    assert "តួឯកកុន" in prompt_tvb or "TVB" in prompt_tvb

    # Angry
    prompt_angry = build_single_translation_prompt("Stop right there!", style="angry")
    assert "ខឹងសម្បារ" in prompt_angry

    # Batch prompt storytelling
    batch_prompt = build_batch_translation_prompt(["Hello world", "Long ago"], style="storytelling")
    assert "និទានរឿង" in batch_prompt


def test_get_emotions_api_endpoints():
    """Verify both /api/tts/emotions and /api/toolkit/tts/emotions endpoints return valid catalogues."""
    r1 = client.get("/api/tts/emotions")
    assert r1.status_code == 200
    data1 = r1.json()
    assert "emotions" in data1
    assert len(data1["emotions"]) >= 14
    ids1 = [e["id"] for e in data1["emotions"]]
    assert "storytelling" in ids1
    assert "dramatic_tvb" in ids1
    assert "angry" in ids1
    assert "explain" in ids1

    r2 = client.get("/api/toolkit/tts/emotions")
    assert r2.status_code == 200
    data2 = r2.json()
    assert len(data2) >= 14


def test_edge_tts_synthesize_prosody_forwarding(tmp_path):
    """Verify EdgeTTSProvider forwards emotion prosody to edge_tts.Communicate."""
    provider = EdgeTTSProvider()
    out_file = tmp_path / "test_prosody.mp3"

    with patch("edge_tts.Communicate") as mock_comm:
        mock_instance = MagicMock()
        mock_comm.return_value = mock_instance
        async def fake_save(dest):
            Path(dest).write_bytes(b"\xff\xfb\x90\x44" + b"\x00" * 200)
        mock_instance.save = fake_save

        with patch.object(provider.video_processor, "get_audio_duration", return_value=2.5):
            res = provider.synthesize(
                text="ឈប់ភ្លាម! ឯងចង់ទៅណា!",
                output_path=out_file,
                voice="km-KH-PisethNeural",
                emotion_style="angry",
            )
            assert res.duration_seconds == 2.5
            # Verify Communicate was called with angry prosody
            mock_comm.assert_called_once()
            args, kwargs = mock_comm.call_args
            assert args[0] == "ឈប់ភ្លាម! ឯងចង់ទៅណា!"
            assert args[1] == "km-KH-PisethNeural"
            assert kwargs.get("rate") == "+15%"
            assert kwargs.get("pitch") == "+15Hz"
            assert kwargs.get("volume") == "+30%"
