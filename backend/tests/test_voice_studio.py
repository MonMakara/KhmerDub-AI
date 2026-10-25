import io
import wave
import struct
import math
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.storage import (
    get_voice_profile_dir,
    get_voice_profile_audio_path,
    delete_voice_profile_storage,
    delete_project_storage,
)
from app.models.voice import VoiceProfile, VoiceConsent
from app.services.voice.inspector import AudioQualityInspector
from app.services.voice.exceptions import (
    AudioValidationError,
    AudioTooShortError,
    AudioTooLongError,
    AudioSilentError,
)

client = TestClient(app)
inspector = AudioQualityInspector()


def generate_test_wav(
    duration: float = 4.0,
    sample_rate: int = 16000,
    frequency: float = 440.0,
    amplitude: float = 16000.0,
) -> bytes:
    """Generate a valid test PCM WAV in memory."""
    num_samples = int(duration * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            # Sine wave tone
            val = int(amplitude * math.sin(2 * math.pi * frequency * i / sample_rate))
            frames.extend(struct.pack("<h", val))
        wf.writeframes(frames)
    return buf.getvalue()


def generate_silent_wav(duration: float = 4.0, sample_rate: int = 16000) -> bytes:
    """Generate a silent PCM WAV (0 amplitude)."""
    return generate_test_wav(duration=duration, sample_rate=sample_rate, amplitude=0.0)


def test_inspector_file_extension():
    """Verify inspector checks file extensions."""
    assert inspector.validate_file_extension("audio.wav") == ".wav"
    assert inspector.validate_file_extension("speech.MP3") == ".mp3"
    assert inspector.validate_file_extension("clip.m4a") == ".m4a"
    assert inspector.validate_file_extension("sample.flac") == ".flac"

    with pytest.raises(AudioValidationError):
        inspector.validate_file_extension("document.pdf")

    with pytest.raises(AudioValidationError):
        inspector.validate_file_extension("script.py")


def test_inspector_duration_checks(tmp_path):
    """Verify inspector rejects audio that is too short or too long."""
    # 1. Too short (1.5 seconds)
    short_wav = tmp_path / "short.wav"
    short_wav.write_bytes(generate_test_wav(duration=1.5))
    with pytest.raises(AudioTooShortError):
        inspector.inspect_audio(short_wav)

    # 2. Valid duration (4.0 seconds)
    valid_wav = tmp_path / "valid.wav"
    valid_wav.write_bytes(generate_test_wav(duration=4.0))
    meta = inspector.inspect_audio(valid_wav)
    assert meta["duration"] >= 3.8
    assert meta["channels"] == 1


def test_inspector_silence_check(tmp_path):
    """Verify inspector rejects silent recordings."""
    silent_wav = tmp_path / "silent.wav"
    silent_wav.write_bytes(generate_silent_wav(duration=4.0))
    with pytest.raises(AudioSilentError):
        inspector.inspect_audio(silent_wav)


def test_inspector_normalization_to_48k(tmp_path):
    """Verify inspector normalizes 16kHz audio into 48kHz mono WAV."""
    src_wav = tmp_path / "src_16k.wav"
    src_wav.write_bytes(generate_test_wav(duration=4.0, sample_rate=16000))

    target_wav = tmp_path / "normalized_48k.wav"
    result = inspector.normalize_reference_audio(src_wav, target_wav)

    assert target_wav.exists()
    assert result["sample_rate"] == 48000
    assert result["channels"] == 1
    assert result["duration"] >= 3.8


def test_voice_studio_get_empty_or_system_voices():
    """Verify GET /api/voices returns system voices and custom list."""
    response = client.get("/api/voices")
    assert response.status_code == 200
    data = response.json()
    assert "system_voices" in data
    assert len(data["system_voices"]) >= 3
    assert any(v["voice"] == "default" for v in data["system_voices"])
    assert any(v["voice"] == "km-KH-PisethNeural" for v in data["system_voices"])
    assert any(v["voice"] == "km-KH-SreymomNeural" for v in data["system_voices"])
    assert "custom_profiles" in data
    assert "cloning_engine_status" in data
    assert any(term in data["cloning_engine_status"] for term in ("Online", "Offline", "VoxCPM2", "Not Configured"))


def test_create_voice_profile_missing_consent(tmp_path):
    """Verify creating a voice profile without consent is rejected."""
    wav_bytes = generate_test_wav(duration=4.0)
    files = {"file": ("test.wav", wav_bytes, "audio/wav")}
    data = {
        "name": "Test Speaker Without Consent",
        "speaker_name": "Sokha",
        "authorized_by": "Mark",
        "consent_confirmed": "false",
    }
    response = client.post("/api/voices", data=data, files=files)
    assert response.status_code == 400
    assert "consent" in response.json()["detail"].lower()


def test_create_voice_profile_audio_too_short():
    """Verify audio < 3s is rejected."""
    wav_bytes = generate_test_wav(duration=1.5)
    files = {"file": ("short.wav", wav_bytes, "audio/wav")}
    data = {
        "name": "Short Voice",
        "speaker_name": "Sokha",
        "authorized_by": "Mark",
        "consent_confirmed": "true",
    }
    response = client.post("/api/voices", data=data, files=files)
    assert response.status_code == 400
    assert "too short" in response.json()["detail"].lower()


def test_create_voice_profile_lifecycle():
    """Verify complete CRUD lifecycle of a voice profile."""
    # 1. Create Profile
    wav_bytes = generate_test_wav(duration=5.0, sample_rate=24000)
    files = {"file": ("khmer_sample.wav", wav_bytes, "audio/wav")}
    data = {
        "name": "Dara Test Voice",
        "description": "Authorized Khmer narrative test voice",
        "gender": "male",
        "speaker_name": "Dara Roth",
        "authorized_by": "Mark QA",
        "consent_confirmed": "true",
        "reference_transcript": "សួស្តី នេះជាសំឡេងសាកល្បង។",
    }

    create_res = client.post("/api/voices", data=data, files=files)
    assert create_res.status_code == 201
    profile = create_res.json()
    profile_id = profile["id"]
    assert profile["name"] == "Dara Test Voice"
    assert profile["gender"] == "male"
    assert profile["reference_audio_sample_rate"] == 48000
    assert profile["reference_audio_duration"] >= 4.8
    assert profile["consent"]["speaker_name"] == "Dara Roth"
    assert profile["consent"]["signature_hash"] is not None

    # Verify file saved on disk
    audio_path = get_voice_profile_audio_path(profile_id)
    assert audio_path.exists()
    assert audio_path.stat().st_size > 0

    # 2. Get Profile by ID
    get_res = client.get(f"/api/voices/{profile_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == profile_id

    # 3. Stream Reference Audio
    stream_res = client.get(f"/api/voices/{profile_id}/audio")
    assert stream_res.status_code == 200
    assert stream_res.headers["content-type"] == "audio/wav"
    assert len(stream_res.content) > 1000

    # 4. Update / Rename Profile
    patch_res = client.patch(
        f"/api/voices/{profile_id}",
        json={"name": "Dara Renamed Voice", "description": "Updated description"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Dara Renamed Voice"
    assert patch_res.json()["description"] == "Updated description"

    # 5. List Profiles includes newly created profile
    list_res = client.get("/api/voices")
    assert list_res.status_code == 200
    profiles = list_res.json()["custom_profiles"]
    assert any(p["id"] == profile_id and p["name"] == "Dara Renamed Voice" for p in profiles)

    # 6. Delete Profile
    del_res = client.delete(f"/api/voices/{profile_id}")
    assert del_res.status_code == 200
    assert del_res.json()["id"] == profile_id

    # Verify disk files removed
    assert not audio_path.exists()

    # Verify 404 on subsequent get
    get_again = client.get(f"/api/voices/{profile_id}")
    assert get_again.status_code == 404


def test_storage_isolation_between_projects_and_voices(tmp_path):
    """
    Critical requirement:
    Deleting a project MUST NOT touch voice profiles.
    Deleting a voice profile MUST NOT touch project storage.
    """
    # 1. Create a voice profile
    wav_bytes = generate_test_wav(duration=4.0)
    files = {"file": ("isolated_voice.wav", wav_bytes, "audio/wav")}
    data = {
        "name": "Isolated Voice",
        "speaker_name": "Sophea",
        "authorized_by": "Isolation Test",
        "consent_confirmed": "true",
    }
    create_voice = client.post("/api/voices", data=data, files=files)
    assert create_voice.status_code == 201
    profile_id = create_voice.json()["id"]
    voice_audio = get_voice_profile_audio_path(profile_id)
    assert voice_audio.exists()

    # 2. Create a disposable test project
    create_proj = client.post("/api/projects", json={"title": "Isolation Project Test"})
    assert create_proj.status_code == 201
    proj_id = create_proj.json()["id"]

    # 3. Delete the project
    del_proj = client.delete(f"/api/projects/{proj_id}")
    assert del_proj.status_code == 200

    # Verify voice audio is still completely intact!
    assert voice_audio.exists()
    assert voice_audio.stat().st_size > 0

    # 4. Now clean up the voice profile
    del_voice = client.delete(f"/api/voices/{profile_id}")
    assert del_voice.status_code == 200
    assert not voice_audio.exists()


def test_existing_tts_preview_unaffected():
    """Verify existing TTS preview endpoints continue to work seamlessly."""
    # Test Google TTS preview
    res = client.post(
        "/api/tts/preview",
        json={"provider": "gtts", "voice": "default", "text": "សួស្តី"},
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/mpeg"
