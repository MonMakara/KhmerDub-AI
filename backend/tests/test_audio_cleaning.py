import io
import json
import subprocess
import threading
import time
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.recovery import recover_interrupted_toolkit_tasks
from app.core.storage import get_toolkit_task_dir
from app.models.toolkit import ToolkitTask
from app.services import audio_cleaning
from app.services.video.cleaning import AudioCleaningProcessor, CleaningCancelled, PRESETS


@pytest.fixture(autouse=True)
def isolated_cleanup(monkeypatch, tmp_path, db_session):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path/"data")
    monkeypatch.setattr(settings, "MODEL_CACHE_DIR", tmp_path/"models")
    monkeypatch.setattr(audio_cleaning, "SessionLocal", sessionmaker(bind=db_session.get_bind()))


def wav_bytes(duration=1.2):
    rate = 48000
    t = np.arange(round(duration*rate))/rate
    # Known reference signal plus stationary hiss; not a perceptual speech fixture.
    noise = np.random.default_rng(42).normal(0, .004, len(t))
    speech_like = .15*np.sin(2*np.pi*300*t) * ((t>.25)&(t<duration-.2))
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((np.clip(speech_like+noise,-1,1)*32767).astype("<i2").tobytes())
    return out.getvalue()


def submit(client, **fields):
    return client.post("/api/toolkit/audio-cleaning/start", data={"mode":"noise", "strength":"balanced", **fields},
                       files={"file":("voice.wav", wav_bytes(), "audio/wav")})


def test_noise_filter_preserves_waveform_alignment(tmp_path):
    source = tmp_path / "reference.wav"
    output = tmp_path / "cleaned.wav"
    source.write_bytes(wav_bytes())
    AudioCleaningProcessor().denoise(source, output, "balanced", lambda: False, lambda _: None)
    def decode(path):
        data = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path),
                               "-f", "f32le", "-"], check=True, capture_output=True).stdout
        return np.frombuffer(data, dtype=np.float32)
    before, after = decode(source), decode(output)
    assert len(before) == len(after)
    # A 25 ms uncompensated filter delay flips this 300 Hz reference's phase.
    assert np.corrcoef(before, after)[0, 1] > .99


def test_upload_disk_full_leaves_no_task_or_partial_input(client, db_session, monkeypatch):
    from collections import namedtuple
    usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(audio_cleaning.shutil, "disk_usage", lambda _: usage(100, 100, 0))
    response = submit(client)
    assert response.status_code == 507
    assert db_session.query(ToolkitTask).count() == 0


@pytest.mark.parametrize("strength", list(PRESETS))
def test_strength_duration_preview_download_history_and_source_preservation(client, db_session, strength):
    response = submit(client, strength=strength)
    assert response.status_code == 202, response.text
    task_id = response.json()["id"]
    task = client.get(f"/api/toolkit/tasks/{task_id}").json()
    assert task["status"] == "completed", task
    meta = task["output_media_metadata"]
    assert meta["strength"] == strength
    assert abs(meta["duration_difference"]) <= .001
    assert get_toolkit_task_dir(task_id).joinpath("input/source.wav").read_bytes() == wav_bytes()
    for kind in ("original", "wav", "mp3"):
        res = client.get(f"/api/toolkit/audio-cleaning/{task_id}/files/{kind}")
        assert res.status_code == 200 and len(res.content)>1000
        download = client.get(f"/api/toolkit/audio-cleaning/{task_id}/files/{kind}?download=true")
        assert "attachment" in download.headers["content-disposition"]
    assert any(t["id"] == task_id for t in client.get("/api/toolkit/tasks").json())
    assert not get_toolkit_task_dir(task_id).joinpath(".cleaning-work").exists()
    assert client.get(f"/api/toolkit/audio-cleaning/{task_id}/files/video").status_code == 404


def test_reject_missing_music_model_invalid_options_and_bad_extensions(client):
    caps = client.get("/api/toolkit/audio-cleaning/capabilities").json()
    assert caps["noise_available"] and not caps["music_available"]
    assert submit(client, mode="music").status_code == 503
    assert submit(client, mode="unknown").status_code == 400
    assert submit(client, strength="extreme").status_code == 400
    assert client.post("/api/toolkit/audio-cleaning/start", files={"file":("x.exe", b"x")}).status_code == 400


def test_corrupted_media_failure_preserves_input_and_hides_output(client):
    response = client.post("/api/toolkit/audio-cleaning/start", files={"file":("bad.wav", b"invalid media")})
    assert response.status_code == 202
    task_id = response.json()["id"]
    task = client.get(f"/api/toolkit/tasks/{task_id}").json()
    assert task["status"] == "failed"
    assert get_toolkit_task_dir(task_id).joinpath("input/source.wav").read_bytes() == b"invalid media"
    assert client.get(f"/api/toolkit/audio-cleaning/{task_id}/files/wav").status_code == 409
    assert "/app/" not in task["error_message"]


def test_processing_failure_cleans_owned_temporary_files(client):
    with patch.object(AudioCleaningProcessor, "denoise", side_effect=RuntimeError("injected")):
        response = submit(client)
    task_id = response.json()["id"]
    assert client.get(f"/api/toolkit/tasks/{task_id}").json()["status"] == "failed"
    root = get_toolkit_task_dir(task_id)
    assert (root/"input/source.wav").exists()
    assert not (root/".cleaning-work").exists()
    assert not (root/"output").exists()


def test_queue_limit_cancel_and_active_deletion_guard(client):
    with patch("app.api.endpoints.audio_cleaning.process_cleaning"):
        responses = [submit(client) for _ in range(3)]
        assert all(r.status_code == 202 for r in responses)
        assert submit(client).status_code == 429
    task_id = responses[0].json()["id"]
    assert client.delete(f"/api/toolkit/tasks/{task_id}").status_code == 409
    assert client.post(f"/api/toolkit/audio-cleaning/{task_id}/cancel").json()["status"] == "cancelling"
    audio_cleaning.process_cleaning(task_id)
    assert client.get(f"/api/toolkit/tasks/{task_id}").json()["status"] == "cancelled"
    assert client.get(f"/api/toolkit/audio-cleaning/{task_id}/files/wav").status_code == 409


def test_subprocess_cancellation_is_bounded(tmp_path):
    processor = AudioCleaningProcessor()
    started = time.monotonic()
    with pytest.raises(CleaningCancelled):
        processor.run_pass(["-re", "-f", "lavfi", "-i", "sine=duration=10", "-f", "null", "-"],
                           10, lambda: True, lambda _: None)
    assert time.monotonic()-started < 4


def test_first_audio_stream_policy_and_no_audio_rejection(tmp_path):
    processor = AudioCleaningProcessor()
    source = tmp_path/"multi.mkv"
    subprocess.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","color=size=64x64:duration=1",
                    "-f","lavfi","-i","sine=frequency=300:duration=1", "-f","lavfi","-i","sine=frequency=900:duration=1",
                    "-map","0:v","-map","1:a","-map","2:a","-c:v","libx264",str(source)], check=True)
    info = processor.inspect(source)
    assert info["audio_stream_count"] == 2 and info["audio_stream_index"] == 1
    original = tmp_path/"selected.wav"
    processor.extract_original(source, original, info, lambda:False, lambda _:None)
    with wave.open(str(original)) as w:
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        frequency = np.argmax(abs(np.fft.rfft(samples)))*w.getframerate()/len(samples)
    assert abs(frequency-300)<3
    mute = tmp_path/"mute.mp4"
    subprocess.run(["ffmpeg","-v","error","-y","-i",str(source),"-an","-c:v","copy",str(mute)],check=True)
    with pytest.raises(Exception, match="no audio"):
        processor.inspect(mute)


def test_video_export_copy_and_full_decode(client, tmp_path):
    source = tmp_path/"video.mp4"
    subprocess.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","color=size=64x64:duration=1.2",
                    "-f","lavfi","-i","sine=frequency=300:duration=1.2","-c:v","libx264","-c:a","aac",str(source)], check=True)
    response = client.post("/api/toolkit/audio-cleaning/start",files={"file":("video.mp4",source.read_bytes(),"video/mp4")})
    task_id = response.json()["id"]
    task = client.get(f"/api/toolkit/tasks/{task_id}").json()
    assert task["status"] == "completed", task
    assert task["output_media_metadata"]["video_stream_copied"]
    assert client.get(f"/api/toolkit/audio-cleaning/{task_id}/files/video").status_code == 200


def test_upload_limit_path_safety_and_pending_output(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    assert client.post("/api/toolkit/audio-cleaning/start",files={"file":("x.wav",b"a"*(1024*1024+1))}).status_code == 413
    assert client.get("/api/toolkit/audio-cleaning/not-a-uuid/files/wav").status_code == 404
    with patch("app.api.endpoints.audio_cleaning.process_cleaning"):
        response = client.post("/api/toolkit/audio-cleaning/start",files={"file":("../../voice.wav",wav_bytes())})
    task_id = response.json()["id"]
    assert get_toolkit_task_dir(task_id).joinpath("input/source.wav").exists()
    assert client.get(f"/api/toolkit/audio-cleaning/{task_id}/files/wav").status_code == 409
    assert client.get(f"/api/toolkit/audio-cleaning/{task_id}/files/unknown").status_code == 404


def test_restart_recovery_preserves_original_and_cleans_owned_work(client, db_session):
    with patch("app.api.endpoints.audio_cleaning.process_cleaning"):
        response = submit(client)
    task_id = response.json()["id"]
    task = db_session.get(ToolkitTask, task_id)
    task.status = "cancelling"
    work = get_toolkit_task_dir(task_id)/".cleaning-work"
    work.mkdir()
    (work/"unfinished.wav").write_bytes(b"partial")
    db_session.commit()
    recover_interrupted_toolkit_tasks(db_session)
    assert task.status == "failed"
    assert not work.exists()
    assert get_toolkit_task_dir(task_id).joinpath("input/source.wav").exists()
