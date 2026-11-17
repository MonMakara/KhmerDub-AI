import subprocess
import wave
import struct
import math
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import get_voice_profile_audio_path
from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProjectStatus,
)
from app.models.voice import VoiceConsent, VoiceProfile
from app.services.voice.extractor import VideoVoiceExtractor, CloneCandidate
from app.services.tts.registry import is_valid_voice_combination


def make_test_audio(path: Path, duration: float = 6.0, sample_rate: int = 48000, freq: int = 440) -> Path:
    """Generate a clean synthetic PCM WAV tone file for audio testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.1, float(duration))
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency={freq}:duration={dur:.3f}:sample_rate={sample_rate}",
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", "1",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg failed to create test tone: {res.stderr}")
    return path


def test_candidate_selection_ranking():
    """Verify VideoVoiceExtractor finds and ranks candidate speech segments according to
    optimal duration (4.0s - 7.0s), natural word rate, and merged short segments.
    """
    extractor = VideoVoiceExtractor()

    project = Project(
        id="proj_candidate_test",
        title="Candidate Selection Test Video",
        transcript_segments=[
            TranscriptSegment(
                id="seg_short",
                segment_order=1,
                start_time=0.0,
                end_time=0.8,
                text="Hi.",
            ),
            TranscriptSegment(
                id="seg_optimal",
                segment_order=2,
                start_time=1.0,
                end_time=6.0,
                text="Welcome to our Khmer dubbing documentary about ancient temples in Siem Reap.",
            ),
            TranscriptSegment(
                id="seg_long",
                segment_order=3,
                start_time=7.0,
                end_time=25.0,
                text="This is an excessively long continuous sentence that exceeds normal reference audio duration limits for neural voice cloning models.",
            ),
            TranscriptSegment(
                id="seg_part_a",
                segment_order=4,
                start_time=26.0,
                end_time=28.2,
                text="The morning light illuminates the stone faces,",
            ),
            TranscriptSegment(
                id="seg_part_b",
                segment_order=5,
                start_time=28.3,
                end_time=31.0,
                text="revealing intricate carvings from a thousand years ago.",
            ),
        ],
    )

    candidates = extractor.find_candidates(project, max_candidates=5)

    assert len(candidates) >= 2
    # seg_short (<1.0s or <2 words) should be excluded
    candidate_ids = [c.candidate_id for c in candidates]
    assert "seg_1" not in candidate_ids

    # seg_2 (optimal 5.0s, high lexical quality) should have high score
    seg2_cand = next(c for c in candidates if c.candidate_id == "seg_2")
    assert seg2_cand.duration == 5.0
    assert seg2_cand.score >= 90.0
    assert seg2_cand.segment_ids == ["seg_optimal"]

    # Merged window (seg 4 + seg 5) should be detected because gap is 0.1s and combined duration is ~5.0s
    merged_cands = [c for c in candidates if c.candidate_id.startswith("merged_")]
    assert len(merged_cands) == 1
    m = merged_cands[0]
    assert m.duration >= 4.5
    assert m.segment_ids == ["seg_part_a", "seg_part_b"]

    # Candidates should be sorted descending by score
    scores = [c.score for c in candidates]
    assert scores == sorted(scores, reverse=True)


def test_extract_speech_slice_padding_and_microfades(tmp_path: Path):
    """Verify speech slice extraction pads short segments symmetrically to at least min_duration
    and generates 48kHz mono 16-bit PCM WAV with micro-fades.
    """
    extractor = VideoVoiceExtractor()
    src_audio = tmp_path / "long_source.wav"
    make_test_audio(src_audio, duration=10.0, sample_rate=48000)

    # 1. Normal length clip (4.0s)
    out_normal = tmp_path / "out_normal.wav"
    extractor.extract_speech_slice(
        source_media_path=src_audio,
        start_time=2.0,
        end_time=6.0,
        output_path=out_normal,
        min_duration=3.2,
        target_sample_rate=48000,
    )
    assert out_normal.exists()

    with wave.open(str(out_normal), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 48000
        duration = wf.getnframes() / float(wf.getframerate())
        assert abs(duration - 4.0) < 0.05

        # Check microfade: first sample should be near 0 due to 15ms fade-in
        first_frame = wf.readframes(1)
        first_val = struct.unpack("<h", first_frame)[0]
        assert abs(first_val) <= 100  # Ramp up starts near zero

    # 2. Short clip (1.0s): should be symmetrically padded to min_duration 3.2s
    out_short = tmp_path / "out_short.wav"
    extractor.extract_speech_slice(
        source_media_path=src_audio,
        start_time=5.0,
        end_time=6.0,
        output_path=out_short,
        min_duration=3.2,
        target_sample_rate=48000,
    )
    assert out_short.exists()

    with wave.open(str(out_short), "rb") as wf:
        dur = wf.getnframes() / float(wf.getframerate())
        assert dur >= 3.15  # Padded to >= 3.2s


def test_clone_voice_from_video_creates_profile_and_consent(db_session: Session, tmp_path: Path):
    """Verify clone_voice_from_video extracts audio, normalizes reference audio,
    signs VoiceConsent, persists VoiceProfile, and updates project voice settings.
    """
    extractor = VideoVoiceExtractor()

    # 1. Setup source media
    media_file = tmp_path / "video_audio.wav"
    make_test_audio(media_file, duration=8.0, sample_rate=48000)

    # 2. Create Project in DB
    proj = Project(
        id="proj_clone_db_test",
        title="Documentary Cambodia",
        original_language="en",
        target_language="km",
        status=ProjectStatus.COMPLETED,
        tts_provider="edge",
        tts_voice="km-KH-PisethNeural",
    )
    db_session.add(proj)
    db_session.commit()

    video = Video(
        id="vid_clone_db_test",
        project_id=proj.id,
        filename="video_audio.mp4",
        file_path=str(media_file),
        file_size_bytes=media_file.stat().st_size,
        extracted_audio_path=str(media_file),
        duration_seconds=8.0,
    )
    db_session.add(video)

    seg1 = TranscriptSegment(
        id="tseg_1",
        project_id=proj.id,
        segment_order=1,
        start_time=1.0,
        end_time=5.5,
        text="The ancient ruins stand proudly under the tropical sun.",
    )
    db_session.add(seg1)

    # Add a translation segment with generated audio to verify invalidation
    t_unit = TranslationSegment(
        id="trans_1",
        project_id=proj.id,
        transcript_segment_id=seg1.id,
        segment_order=1,
        start_time=1.0,
        end_time=5.5,
        khmer_text="ប្រាសាទបុរាណឈរយ៉ាងរុងរឿងក្រោមពន្លឺព្រះអាទិត្យ។",
    )
    db_session.add(t_unit)
    db_session.flush()

    gen_audio = GeneratedAudio(
        id="ga_1",
        project_id=proj.id,
        translation_segment_id=t_unit.id,
        audio_path="/dummy/path.wav",
        duration_seconds=4.0,
        is_outdated=False,
    )
    db_session.add(gen_audio)
    db_session.commit()

    # 3. Clone voice
    profile = extractor.clone_voice_from_video(
        project_id=proj.id,
        db=db_session,
        segment_id="tseg_1",
        voice_name="Angkor Narrator",
        set_as_project_voice=True,
    )

    # 4. Assertions on profile
    assert profile is not None
    assert profile.name == "Angkor Narrator"
    assert profile.gender == "neutral"
    assert profile.language == "km"
    assert profile.is_active is True
    assert profile.consent_id is not None
    assert profile.reference_audio_duration >= 4.0

    # Verify reference file saved on disk
    ref_path = get_voice_profile_audio_path(profile.id)
    assert ref_path.exists()
    assert ref_path.stat().st_size > 0

    # 5. Assertions on consent
    consent = db_session.query(VoiceConsent).filter_by(id=profile.consent_id).first()
    assert consent is not None
    assert consent.is_authorized is True
    assert consent.signature_hash is not None
    assert len(consent.signature_hash) == 64  # SHA256 length

    # 6. Assertions on project voice assignment
    db_session.refresh(proj)
    assert proj.tts_provider == "voxcpm"
    assert proj.tts_voice == profile.id

    # Verify generated audio was marked outdated
    db_session.refresh(gen_audio)
    assert gen_audio.is_outdated is True

    # 7. Assertions on voice combination validity
    assert is_valid_voice_combination("voxcpm", profile.id, db=db_session) is True


def test_clone_api_endpoints(client: TestClient, db_session: Session, tmp_path: Path):
    """Verify HTTP endpoints for candidate discovery, preview streaming, and voice cloning."""
    # Setup source audio
    media_file = tmp_path / "project_preview_test.wav"
    make_test_audio(media_file, duration=10.0, sample_rate=48000)

    proj = Project(
        id="proj_api_clone_test",
        title="Siem Reap Travelogue",
        original_language="en",
        target_language="km",
        status=ProjectStatus.COMPLETED,
        tts_provider="edge",
        tts_voice="km-KH-PisethNeural",
    )
    db_session.add(proj)
    db_session.commit()

    video = Video(
        id="vid_api_test",
        project_id=proj.id,
        filename="project_preview_test.mp4",
        file_path=str(media_file),
        file_size_bytes=media_file.stat().st_size,
        extracted_audio_path=str(media_file),
        duration_seconds=10.0,
    )
    db_session.add(video)

    seg = TranscriptSegment(
        id="tseg_api_1",
        project_id=proj.id,
        segment_order=1,
        start_time=2.0,
        end_time=6.5,
        text="Siem Reap is the gateway to the world-renowned Angkor temple complex.",
    )
    db_session.add(seg)
    db_session.commit()

    # 1. GET /api/projects/{id}/voice/clone-candidates
    cand_res = client.get(f"/api/projects/{proj.id}/voice/clone-candidates")
    assert cand_res.status_code == 200
    cand_data = cand_res.json()
    assert cand_data["project_id"] == proj.id
    assert len(cand_data["candidates"]) >= 1
    assert cand_data["recommended_candidate_id"] is not None

    top_cand = cand_data["candidates"][0]
    assert top_cand["duration"] == 4.5
    assert "/preview-candidate" in top_cand["preview_url"]

    # 2. GET /api/projects/{id}/voice/preview-candidate
    preview_res = client.get(
        f"/api/projects/{proj.id}/voice/preview-candidate",
        params={"start_time": 2.0, "end_time": 6.5},
    )
    assert preview_res.status_code == 200
    assert "audio/wav" in preview_res.headers["content-type"]
    assert len(preview_res.content) > 1000

    # 3. POST /api/projects/{id}/voice/clone-from-video
    clone_payload = {
        "start_time": 2.0,
        "end_time": 6.5,
        "voice_name": "Siem Reap Guide",
        "set_as_project_voice": True,
    }
    clone_res = client.post(
        f"/api/projects/{proj.id}/voice/clone-from-video",
        json=clone_payload,
    )
    assert clone_res.status_code == 201
    profile_data = clone_res.json()
    assert profile_data["name"] == "Siem Reap Guide"
    assert profile_data["gender"] == "neutral"
    assert profile_data["consent"]["signature_hash"] is not None

    # Verify project reflects cloned voice
    db_session.refresh(proj)
    assert proj.tts_provider == "voxcpm"
    assert proj.tts_voice == profile_data["id"]


def test_clone_api_error_handling(client: TestClient, db_session: Session):
    """Verify validation and error handling for missing projects or invalid parameters."""
    # 404 for non-existent project
    res_candidates = client.get("/api/projects/non_existent_project/voice/clone-candidates")
    assert res_candidates.status_code == 404

    res_preview = client.get(
        "/api/projects/non_existent_project/voice/preview-candidate",
        params={"start_time": 1.0, "end_time": 3.0},
    )
    assert res_preview.status_code == 404

    # 400 for invalid preview times (end_time <= start_time)
    proj = Project(id="proj_err_test", title="Error Test")
    db_session.add(proj)
    db_session.commit()

    res_invalid_time = client.get(
        f"/api/projects/{proj.id}/voice/preview-candidate",
        params={"start_time": 5.0, "end_time": 2.0},
    )
    assert res_invalid_time.status_code == 400


def test_clone_voice_from_video_auto_candidate(client: TestClient, db_session: Session, tmp_path: Path):
    """Verify clone_from_video without explicit start/end times automatically picks the top candidate."""
    media_file = tmp_path / "auto_candidate_video.wav"
    make_test_audio(media_file, duration=10.0, sample_rate=48000)

    proj = Project(
        id="proj_auto_cand_test",
        title="Auto Candidate Project",
        status=ProjectStatus.COMPLETED,
    )
    db_session.add(proj)
    db_session.commit()

    video = Video(
        id="vid_auto_cand",
        project_id=proj.id,
        filename="auto_video.mp4",
        file_path=str(media_file),
        file_size_bytes=media_file.stat().st_size,
        extracted_audio_path=str(media_file),
        duration_seconds=10.0,
    )
    db_session.add(video)

    # Add an optimal candidate segment (5.0s, natural speech)
    seg = TranscriptSegment(
        id="tseg_auto_1",
        project_id=proj.id,
        segment_order=1,
        start_time=2.0,
        end_time=7.0,
        text="A wonderful journey exploring the hidden trails of the mountain jungle.",
    )
    db_session.add(seg)
    db_session.commit()

    # Call endpoint without start_time or end_time
    clone_res = client.post(
        f"/api/projects/{proj.id}/voice/clone-from-video",
        json={"voice_name": "Auto Cloned Speaker"},
    )
    assert clone_res.status_code == 201
    profile = clone_res.json()
    assert profile["name"] == "Auto Cloned Speaker"
    assert profile["reference_audio_duration"] >= 4.5


def test_clone_voice_store_in_voice_studio_flag(client: TestClient, db_session: Session, tmp_path: Path):
    """Verify clone_from_video with store_in_voice_studio=False does not appear in Voice Studio library."""
    media_file = tmp_path / "ephemeral_clone_video.wav"
    make_test_audio(media_file, duration=10.0, sample_rate=48000)

    proj = Project(
        id="proj_ephemeral_test",
        title="Ephemeral Voice Project",
        status=ProjectStatus.COMPLETED,
    )
    db_session.add(proj)
    db_session.commit()

    video = Video(
        id="vid_ephemeral",
        project_id=proj.id,
        filename="ephemeral.mp4",
        file_path=str(media_file),
        file_size_bytes=media_file.stat().st_size,
        extracted_audio_path=str(media_file),
        duration_seconds=10.0,
    )
    db_session.add(video)

    seg = TranscriptSegment(
        id="tseg_eph_1",
        project_id=proj.id,
        segment_order=1,
        start_time=1.0,
        end_time=6.0,
        text="Sample monologue for testing ephemeral voice cloning.",
    )
    db_session.add(seg)
    db_session.commit()

    # 1. Clone with store_in_voice_studio = False
    clone_res = client.post(
        f"/api/projects/{proj.id}/voice/clone-from-video",
        json={
            "voice_name": "Project Only Speaker",
            "store_in_voice_studio": False,
        },
    )
    assert clone_res.status_code == 201
    profile_data = clone_res.json()
    assert profile_data["is_library"] is False
    profile_id = profile_data["id"]

    # 2. Check Voice Studio endpoint: this profile must NOT appear
    studio_res = client.get("/api/voices")
    assert studio_res.status_code == 200
    studio_voices = studio_res.json().get("custom_profiles", [])
    profile_ids_in_studio = [p["id"] for p in studio_voices]
    assert profile_id not in profile_ids_in_studio, "Ephemeral voice should NOT be present in Voice Studio!"


def test_clone_speaker_voices_multi_speaker(client: TestClient, db_session: Session, tmp_path: Path):
    """Verify bulk cloning detected speakers from a multi-speaker video with store_in_voice_studio=False."""
    from app.models.project import ProjectSpeaker

    media_file = tmp_path / "multi_speaker_video.wav"
    make_test_audio(media_file, duration=15.0, sample_rate=48000)

    proj = Project(
        id="proj_multi_clone_test",
        title="Multi-Speaker Project",
        status=ProjectStatus.COMPLETED,
    )
    db_session.add(proj)
    db_session.commit()

    video = Video(
        id="vid_multi_clone",
        project_id=proj.id,
        filename="multi_video.mp4",
        file_path=str(media_file),
        file_size_bytes=media_file.stat().st_size,
        extracted_audio_path=str(media_file),
        duration_seconds=15.0,
    )
    db_session.add(video)

    # Add 2 speakers
    spk1 = ProjectSpeaker(
        id="spk_mc_1",
        project_id=proj.id,
        speaker_label="SPEAKER_01",
        display_name="First Host",
        detected_gender="male",
        assigned_voice_provider="edge",
        assigned_voice_id="km-KH-PisethNeural",
        segment_count=1,
        total_duration=5.0,
    )
    spk2 = ProjectSpeaker(
        id="spk_mc_2",
        project_id=proj.id,
        speaker_label="SPEAKER_02",
        display_name="Second Guest",
        detected_gender="female",
        assigned_voice_provider="edge",
        assigned_voice_id="km-KH-SreymomNeural",
        segment_count=1,
        total_duration=4.5,
    )
    db_session.add_all([spk1, spk2])

    seg1 = TranscriptSegment(
        id="tseg_mc_1",
        project_id=proj.id,
        segment_order=1,
        speaker_label="SPEAKER_01",
        start_time=1.0,
        end_time=6.0,
        text="Host speaking about the topic.",
    )
    seg2 = TranscriptSegment(
        id="tseg_mc_2",
        project_id=proj.id,
        segment_order=2,
        speaker_label="SPEAKER_02",
        start_time=7.0,
        end_time=11.5,
        text="Guest giving their answer clearly.",
    )
    db_session.add_all([seg1, seg2])

    trans1 = TranslationSegment(
        id="tr_mc_1",
        project_id=proj.id,
        transcript_segment_id="tseg_mc_1",
        speaker_label="SPEAKER_01",
        segment_order=1,
        khmer_text="ពិធីករនិយាយអំពីប្រធានបទនេះ",
        voice_revision=0,
    )
    trans2 = TranslationSegment(
        id="tr_mc_2",
        project_id=proj.id,
        transcript_segment_id="tseg_mc_2",
        speaker_label="SPEAKER_02",
        segment_order=2,
        khmer_text="ភ្ញៀវឆ្លើយតបយ៉ាងច្បាស់លាស់",
        voice_revision=0,
    )
    db_session.add_all([trans1, trans2])
    db_session.commit()

    # Call POST /api/projects/{id}/speakers/clone-voices with store_in_voice_studio = False
    res_clone = client.post(
        f"/api/projects/{proj.id}/speakers/clone-voices",
        json={"store_in_voice_studio": False},
    )
    assert res_clone.status_code == 201, res_clone.text
    data = res_clone.json()
    assert data["created_profiles_count"] == 2
    assert len(data["cloned_speakers"]) == 2

    # Check that speaker profiles were updated to voxcpm and cascaded to translation segments
    db_session.refresh(spk1)
    db_session.refresh(spk2)
    db_session.refresh(trans1)
    db_session.refresh(trans2)

    assert spk1.assigned_voice_provider == "voxcpm"
    assert spk1.assigned_voice_id is not None
    assert trans1.voice_override_provider == "voxcpm"
    assert trans1.voice_override_id == spk1.assigned_voice_id

    assert spk2.assigned_voice_provider == "voxcpm"
    assert spk2.assigned_voice_id is not None
    assert trans2.voice_override_provider == "voxcpm"
    assert trans2.voice_override_id == spk2.assigned_voice_id

    # Verify neither cloned profile appears in Voice Studio
    studio_res = client.get("/api/voices")
    studio_ids = [p["id"] for p in studio_res.json().get("custom_profiles", [])]
    assert spk1.assigned_voice_id not in studio_ids
    assert spk2.assigned_voice_id not in studio_ids


def test_auto_detect_and_clone_speakers_endpoint(client: TestClient, db_session: Session, tmp_path: Path):
    """Verify 1-click auto-detect-and-clone endpoint diarizes speakers and clones reference voices."""
    audio_file = tmp_path / "multi_speaker_test.wav"
    make_test_audio(audio_file, duration=12.0, sample_rate=48000)

    proj = Project(
        id="proj_auto_clone_all",
        title="Dialogue Scene",
        original_language="en",
        target_language="km",
        status=ProjectStatus.TRANSCRIBED,
        tts_provider="edge",
        tts_voice="km-KH-PisethNeural",
    )
    db_session.add(proj)
    db_session.commit()

    video = Video(
        id="vid_auto_clone_all",
        project_id=proj.id,
        filename="dialogue.mp4",
        file_path=str(audio_file),
        file_size_bytes=audio_file.stat().st_size,
        extracted_audio_path=str(audio_file),
        duration_seconds=12.0,
    )
    db_session.add(video)

    seg1 = TranscriptSegment(
        id="tseg_ac_1",
        project_id=proj.id,
        segment_order=1,
        start_time=1.0,
        end_time=5.5,
        text="First actor speaking their dialogue line clearly.",
    )
    seg2 = TranscriptSegment(
        id="tseg_ac_2",
        project_id=proj.id,
        segment_order=2,
        start_time=6.0,
        end_time=11.0,
        text="Second actor responding to the previous question.",
    )
    db_session.add_all([seg1, seg2])

    trans1 = TranslationSegment(
        id="tr_ac_1",
        project_id=proj.id,
        transcript_segment_id="tseg_ac_1",
        segment_order=1,
        khmer_text="តួអង្គទីមួយនិយាយប្រយោគរបស់ខ្លួន",
        voice_revision=0,
    )
    trans2 = TranslationSegment(
        id="tr_ac_2",
        project_id=proj.id,
        transcript_segment_id="tseg_ac_2",
        segment_order=2,
        khmer_text="តួអង្គទីពីរឆ្លើយតបទៅនឹងសំណួរ",
        voice_revision=0,
    )
    db_session.add_all([trans1, trans2])
    db_session.commit()

    res = client.post(
        f"/api/projects/{proj.id}/speakers/auto-detect-and-clone",
        json={"min_speakers": 1, "max_speakers": 4, "store_in_voice_studio": False},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["project_id"] == proj.id
    assert data["speakers_detected"] >= 1
    assert data["cloned_voices_count"] >= 1
    assert len(data["speakers"]) >= 1
    assert len(data["cloned_speakers"]) >= 1
    assert "cloned" in data["message"].lower()

    # Verify translation segments now have voice overrides
    db_session.refresh(trans1)
    db_session.refresh(trans2)
    assert trans1.voice_override_provider == "voxcpm"
    assert trans1.voice_override_id is not None
    assert trans2.voice_override_provider == "voxcpm"
    assert trans2.voice_override_id is not None



