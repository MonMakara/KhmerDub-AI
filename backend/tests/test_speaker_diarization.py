import math
import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from app.models.project import Project, TranscriptSegment, TranslationSegment, ProjectSpeaker
from app.services.voice.diarizer import AudioDiarizer, SpeakerProfileData


def generate_tone(freq: float, duration: float = 1.0, sr: int = 16000) -> np.ndarray:
    """Generate harmonic voice-like tone with fundamental frequency and harmonics."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Fundamental + 2nd & 3rd harmonics + subtle formant envelope
    signal = (
        0.6 * np.sin(2 * np.pi * freq * t)
        + 0.3 * np.sin(2 * np.pi * 2 * freq * t)
        + 0.15 * np.sin(2 * np.pi * 3 * freq * t)
    )
    return signal.astype(np.float32)


def test_pitch_estimation_accuracy():
    diarizer = AudioDiarizer()
    sr = 16000

    male_signal = generate_tone(freq=125.0, duration=0.5, sr=sr)
    female_signal = generate_tone(freq=225.0, duration=0.5, sr=sr)

    # Test single frame pitch
    frame_len = int(sr * 0.030)
    male_frame = male_signal[:frame_len]
    female_frame = female_signal[:frame_len]

    p_male = diarizer.estimate_frame_pitch(male_frame, sr=sr)
    p_female = diarizer.estimate_frame_pitch(female_frame, sr=sr)

    assert 115.0 <= p_male <= 135.0, f"Expected ~125Hz, got {p_male}"
    assert 215.0 <= p_female <= 235.0, f"Expected ~225Hz, got {p_female}"


def test_feature_extraction_dimension_and_pitch():
    diarizer = AudioDiarizer()
    sr = 16000

    male_signal = generate_tone(freq=120.0, duration=0.8, sr=sr)
    features, pitch = diarizer.extract_features(male_signal, sr=sr)

    assert features.shape == (39,)
    assert pitch is not None
    assert 110.0 <= pitch <= 130.0

    # Test silent/short audio
    short_signal = np.zeros(100, dtype=np.float32)
    feat_short, pitch_short = diarizer.extract_features(short_signal, sr=sr)
    assert feat_short.shape == (39,)
    assert pitch_short is None


def test_agglomerative_clustering_separates_speakers():
    diarizer = AudioDiarizer()
    sr = 16000

    # 3 male samples, 3 female samples
    samples = [
        generate_tone(freq=110.0, duration=0.6, sr=sr),
        generate_tone(freq=120.0, duration=0.6, sr=sr),
        generate_tone(freq=125.0, duration=0.6, sr=sr),
        generate_tone(freq=210.0, duration=0.6, sr=sr),
        generate_tone(freq=220.0, duration=0.6, sr=sr),
        generate_tone(freq=230.0, duration=0.6, sr=sr),
    ]

    features = []
    pitches = []
    for s in samples:
        feat, p = diarizer.extract_features(s, sr=sr)
        features.append(feat)
        pitches.append(p)

    feat_matrix = np.array(features)
    dist_matrix = diarizer.compute_cosine_distance_matrix(feat_matrix)

    # Within male cluster distance should be smaller than cross-gender distance
    within_male = dist_matrix[0, 1]
    cross_gender = dist_matrix[0, 3]
    assert within_male < cross_gender

    labels = diarizer.agglomerative_clustering(dist_matrix, n_clusters=2)
    assert len(labels) == 6
    # First 3 should share the same label, last 3 should share the other
    assert labels[0] == labels[1] == labels[2]
    assert labels[3] == labels[4] == labels[5]
    assert labels[0] != labels[3]

    sil = diarizer.compute_silhouette(dist_matrix, labels)
    assert sil > 0.40, f"Expected strong silhouette score > 0.40, got {sil}"


def test_diarize_returns_speaker_profiles_and_assignments():
    diarizer = AudioDiarizer()

    # Create 4 mock segments (2 male, 2 female)
    seg1 = MagicMock(spec=TranscriptSegment)
    seg1.id = "seg-1"
    seg1.start_time = 0.0
    seg1.end_time = 3.0  # 3s duration (longer -> SPEAKER_01)

    seg2 = MagicMock(spec=TranscriptSegment)
    seg2.id = "seg-2"
    seg2.start_time = 3.5
    seg2.end_time = 5.5  # 2s duration

    seg3 = MagicMock(spec=TranscriptSegment)
    seg3.id = "seg-3"
    seg3.start_time = 6.0
    seg3.end_time = 7.0  # 1s duration

    seg4 = MagicMock(spec=TranscriptSegment)
    seg4.id = "seg-4"
    seg4.start_time = 7.5
    seg4.end_time = 8.5  # 1s duration

    segments = [seg1, seg2, seg3, seg4]

    # Mock extract_audio_slice
    # seg1 & seg2 are female (220 Hz) -> total 5s
    # seg3 & seg4 are male (115 Hz) -> total 2s
    def mock_extract(audio_path, start_time, duration, sr=16000):
        if start_time < 5.0:
            return generate_tone(freq=220.0, duration=duration, sr=sr)
        return generate_tone(freq=115.0, duration=duration, sr=sr)

    with patch.object(diarizer, "extract_audio_slice", side_effect=mock_extract):
        result = diarizer.diarize(
            segments,
            source_audio_path=Path("/fake/audio.wav"),
            min_speakers=2,
            max_speakers=4,
        )

    assert len(result.speakers) == 2
    spk1 = result.speakers[0]
    spk2 = result.speakers[1]

    # SPEAKER_01 should be female (5s > 2s)
    assert spk1.speaker_label == "SPEAKER_01"
    assert spk1.detected_gender == "female"
    assert spk1.assigned_voice_id == "km-KH-SreymomNeural"
    assert spk1.segment_count == 2
    assert spk1.total_duration == 5.0

    # SPEAKER_02 should be male (2s)
    assert spk2.speaker_label == "SPEAKER_02"
    assert spk2.detected_gender == "male"
    assert spk2.assigned_voice_id == "km-KH-PisethNeural"
    assert spk2.segment_count == 2
    assert spk2.total_duration == 2.0

    # Segment assignments check
    assert result.segment_assignments["seg-1"] == "SPEAKER_01"
    assert result.segment_assignments["seg-2"] == "SPEAKER_01"
    assert result.segment_assignments["seg-3"] == "SPEAKER_02"
    assert result.segment_assignments["seg-4"] == "SPEAKER_02"


def test_apply_speaker_voice_cascades_to_translation_segments(db_session):
    diarizer = AudioDiarizer()

    project = Project(
        id="proj-diar-1",
        title="Diarization Test",
        tts_provider="edge",
        tts_voice="km-KH-PisethNeural",
    )
    db_session.add(project)

    spk1 = ProjectSpeaker(
        id="spk-1",
        project_id=project.id,
        speaker_label="SPEAKER_01",
        display_name="Speaker 1",
        detected_gender="female",
        assigned_voice_provider="edge",
        assigned_voice_id="km-KH-SreymomNeural",
        segment_count=2,
        total_duration=5.0,
    )
    spk2 = ProjectSpeaker(
        id="spk-2",
        project_id=project.id,
        speaker_label="SPEAKER_02",
        display_name="Speaker 2",
        detected_gender="male",
        assigned_voice_provider="edge",
        assigned_voice_id="km-KH-PisethNeural",
        segment_count=1,
        total_duration=2.0,
    )
    db_session.add_all([spk1, spk2])

    trans1 = TranslationSegment(
        id="trans-1",
        project_id=project.id,
        segment_order=1,
        khmer_text="សួស្តីអ្នកទាំងអស់គ្នា",
        speaker_label="SPEAKER_01",
        voice_override_provider=None,
        voice_override_id=None,
        voice_revision=0,
    )
    trans2 = TranslationSegment(
        id="trans-2",
        project_id=project.id,
        segment_order=2,
        khmer_text="តើយើងទៅណាថ្ងៃនេះ?",
        speaker_label="SPEAKER_01",
        voice_override_provider=None,
        voice_override_id=None,
        voice_revision=0,
    )
    trans3 = TranslationSegment(
        id="trans-3",
        project_id=project.id,
        segment_order=3,
        khmer_text="ខ្ញុំគិតថាយើងគួរទៅផ្សារ",
        speaker_label="SPEAKER_02",
        voice_override_provider=None,
        voice_override_id=None,
        voice_revision=0,
    )
    db_session.add_all([trans1, trans2, trans3])
    db_session.commit()

    # Cascade a custom or different voice to SPEAKER_01
    updated_count = diarizer.apply_speaker_voice(
        db_session,
        project_id=project.id,
        speaker_label="SPEAKER_01",
        provider="edge",
        voice_id="km-KH-SreymomNeural",
    )

    assert updated_count == 2

    db_session.refresh(trans1)
    db_session.refresh(trans2)
    db_session.refresh(trans3)
    db_session.refresh(spk1)

    assert spk1.assigned_voice_provider == "edge"
    assert spk1.assigned_voice_id == "km-KH-SreymomNeural"

    # trans1 and trans2 should now have the override applied
    assert trans1.voice_override_provider == "edge"
    assert trans1.voice_override_id == "km-KH-SreymomNeural"
    assert trans1.voice_revision == 1

    assert trans2.voice_override_provider == "edge"
    assert trans2.voice_override_id == "km-KH-SreymomNeural"
    assert trans2.voice_revision == 1

    # trans3 (SPEAKER_02) should remain unaffected
    assert trans3.voice_override_provider is None
    assert trans3.voice_override_id is None
    assert trans3.voice_revision == 0


def test_diarization_api_endpoints(client, db_session):
    # Setup test project
    project = Project(
        id="proj-api-diar-1",
        title="API Diarization Test",
        tts_provider="edge",
        tts_voice="km-KH-PisethNeural",
    )
    db_session.add(project)

    seg1 = TranscriptSegment(
        id="tseg-1",
        project_id=project.id,
        segment_order=1,
        start_time=0.0,
        end_time=3.0,
        text="Hello world",
    )
    seg2 = TranscriptSegment(
        id="tseg-2",
        project_id=project.id,
        segment_order=2,
        start_time=3.5,
        end_time=5.0,
        text="Welcome to Phnom Penh",
    )
    db_session.add_all([seg1, seg2])

    trans1 = TranslationSegment(
        id="trseg-1",
        project_id=project.id,
        transcript_segment_id="tseg-1",
        segment_order=1,
        khmer_text="សួស្តីពិភពលោក",
        voice_revision=0,
    )
    trans2 = TranslationSegment(
        id="trseg-2",
        project_id=project.id,
        transcript_segment_id="tseg-2",
        segment_order=2,
        khmer_text="សូមស្វាគមន៍មកកាន់ភ្នំពេញ",
        voice_revision=0,
    )
    db_session.add_all([trans1, trans2])
    db_session.commit()

    # 1. Mock diarize_project so API test does not depend on actual ffmpeg file read
    mock_speakers = [
        SpeakerProfileData(
            speaker_label="SPEAKER_01",
            display_name="Speaker 1",
            detected_gender="female",
            average_pitch_hz=215.0,
            color="indigo",
            assigned_voice_provider="edge",
            assigned_voice_id="km-KH-SreymomNeural",
            segment_count=1,
            total_duration=3.0,
        ),
        SpeakerProfileData(
            speaker_label="SPEAKER_02",
            display_name="Speaker 2",
            detected_gender="male",
            average_pitch_hz=120.0,
            color="emerald",
            assigned_voice_provider="edge",
            assigned_voice_id="km-KH-PisethNeural",
            segment_count=1,
            total_duration=1.5,
        ),
    ]
    from app.services.voice.diarizer import DiarizationResult

    mock_result = DiarizationResult(
        speakers=mock_speakers,
        segment_assignments={"tseg-1": "SPEAKER_01", "tseg-2": "SPEAKER_02"},
    )

    with patch.object(AudioDiarizer, "diarize_project", return_value=mock_result):
        # We manually insert speakers and set segment labels to simulate diarize_project's db effect
        seg1.speaker_label = "SPEAKER_01"
        seg2.speaker_label = "SPEAKER_02"
        trans1.speaker_label = "SPEAKER_01"
        trans2.speaker_label = "SPEAKER_02"
        spk1 = ProjectSpeaker(
            project_id=project.id,
            speaker_label="SPEAKER_01",
            display_name="Speaker 1",
            detected_gender="female",
            average_pitch_hz=215.0,
            color="indigo",
            assigned_voice_provider="edge",
            assigned_voice_id="km-KH-SreymomNeural",
            segment_count=1,
            total_duration=3.0,
        )
        spk2 = ProjectSpeaker(
            project_id=project.id,
            speaker_label="SPEAKER_02",
            display_name="Speaker 2",
            detected_gender="male",
            average_pitch_hz=120.0,
            color="emerald",
            assigned_voice_provider="edge",
            assigned_voice_id="km-KH-PisethNeural",
            segment_count=1,
            total_duration=1.5,
        )
        db_session.add_all([spk1, spk2])
        db_session.commit()

        # Test POST /api/projects/{id}/diarization/run
        res_run = client.post(f"/api/projects/{project.id}/diarization/run", json={"min_speakers": 1, "max_speakers": 4})
        assert res_run.status_code == 200, res_run.text
        data = res_run.json()
        assert data["speakers_detected"] == 2
        assert len(data["speakers"]) == 2

    # 2. Test GET /api/projects/{id}/speakers
    res_get = client.get(f"/api/projects/{project.id}/speakers")
    assert res_get.status_code == 200
    spk_list = res_get.json()
    assert len(spk_list) == 2
    assert spk_list[0]["speaker_label"] == "SPEAKER_01"
    assert spk_list[1]["speaker_label"] == "SPEAKER_02"

    # 3. Test PUT /api/projects/{id}/speakers/{label} to update name and voice
    res_update = client.put(
        f"/api/projects/{project.id}/speakers/SPEAKER_01",
        json={
            "display_name": "Host Lady",
            "assigned_voice_provider": "edge",
            "assigned_voice_id": "km-KH-SreymomNeural",
            "color": "rose",
        },
    )
    assert res_update.status_code == 200
    updated_spk = res_update.json()
    assert updated_spk["display_name"] == "Host Lady"
    assert updated_spk["color"] == "rose"
    assert updated_spk["assigned_voice_id"] == "km-KH-SreymomNeural"

    # Verify translation segment 1 received the cascaded voice override
    db_session.refresh(trans1)
    assert trans1.voice_override_provider == "edge"
    assert trans1.voice_override_id == "km-KH-SreymomNeural"
    assert trans1.voice_revision == 1

    # 4. Test PUT /api/projects/{id}/transcript/{segment_id}/speaker to reassign speaker
    res_seg_spk = client.put(
        f"/api/projects/{project.id}/transcript/tseg-2/speaker",
        json={"speaker_label": "SPEAKER_01"},
    )
    assert res_seg_spk.status_code == 200
    assert res_seg_spk.json()["speaker_label"] == "SPEAKER_01"

    # Verify trans2 propagated
    db_session.refresh(trans2)
    assert trans2.speaker_label == "SPEAKER_01"


