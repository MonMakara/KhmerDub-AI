"""Unit identities, persistent selections, targeted freshness and real-session races."""
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.project import Project, TranscriptSegment, TranslationSegment, GeneratedAudio, Video, ProcessingJob, JobStatus
from app.models.voice import VoiceConsent, VoiceProfile
from app.services.tts.base import TTSAudioResult
from app.services.tts.exceptions import TTSGenerationError, VoiceNotSupportedError
from app.services.tts.selection import (
    effective_voice, set_unit_voice, audio_matches_selection, voice_aware_groups,
    source_keys, validate_voice, voice_catalog, preserve_partition,
)
from app.workers.tts import synthesize_segment_audio, process_tts

PISETH = "km-KH-PisethNeural"
SREYMOM = "km-KH-SreymomNeural"


def seed(db):
    project = Project(title="Mixed voice fixture", pipeline_version="v2.3")
    db.add(project)
    db.flush()
    segments = []
    for index in range(1, 4):
        transcript = TranscriptSegment(
            project_id=project.id, segment_order=index, start_time=index * 2,
            end_time=index * 2 + 1, text=f"Word{index}.",
            words_json=json.dumps([{"word": f"Word{index}.", "start": index*2,
                                    "end": index*2+1, "word_id": f"word-{index}"}]),
        )
        db.add(transcript)
        db.flush()
        segment = TranslationSegment(
            project_id=project.id, transcript_segment_id=transcript.id,
            source_segment_ids=json.dumps([transcript.id]), source_text=transcript.text,
            start_time=transcript.start_time, end_time=transcript.end_time,
            segment_order=index, khmer_text="សួស្តី។",
        )
        db.add(segment)
        segments.append(segment)
    db.commit()
    return project, segments


def recording(db, project, segment, tmp_path):
    path = tmp_path / f"{segment.id}.mp3"
    path.write_bytes(b"previous recording")
    audio = GeneratedAudio(project_id=project.id, translation_segment_id=segment.id,
                           audio_path=str(path), duration_seconds=2, provider="edge",
                           voice=PISETH, voice_revision=0)
    db.add(audio)
    db.commit()
    return audio


def test_inheritance_override_reset_persist_and_targeted_invalidation(client, db_session, tmp_path):
    p, units = seed(db_session)
    audios = [recording(db_session, p, s, tmp_path) for s in units]
    before = [(s.khmer_text, s.start_time, s.end_time) for s in units]
    assert effective_voice(p, units[0]) == ("edge", PISETH)
    response = client.patch(f"/api/projects/{p.id}/translations/{units[1].id}/voice",
                            json={"provider": "edge", "voice": SREYMOM})
    assert response.status_code == 200, response.text
    assert response.json()["effective_tts_voice"] == SREYMOM
    db_session.expire_all()
    assert [a.is_outdated for a in audios] == [False, True, False]
    assert [(s.khmer_text, s.start_time, s.end_time) for s in units] == before
    data = client.get(f"/api/projects/{p.id}/translations").json()["segments"]
    assert data[1]["voice_override_id"] == SREYMOM
    assert json.loads(units[1].voice_source_keys) == ["word:word-2"]
    assert client.patch(f"/api/projects/{p.id}/translations/{units[1].id}/voice",
                        json={"provider": None, "voice": None}).status_code == 200
    db_session.refresh(units[1])
    assert effective_voice(p, units[1]) == ("edge", PISETH)
    assert units[1].voice_override_id is None


def test_bulk_update_is_atomic_and_project_default_only_invalidates_inherited(client, db_session, tmp_path):
    p, units = seed(db_session)
    audios = [recording(db_session, p, s, tmp_path) for s in units]
    endpoint = f"/api/projects/{p.id}/translations/voices"
    payload = {"segment_ids": [units[1].id, "wrong-project-id"], "provider": "edge", "voice": SREYMOM}
    assert client.patch(endpoint, json=payload).status_code == 404
    db_session.refresh(units[1])
    assert units[1].voice_override_id is None
    payload["segment_ids"] = [units[1].id, units[2].id]
    assert client.patch(endpoint, json=payload).status_code == 200
    for a in audios:
        a.is_outdated = False
    db_session.commit()
    assert client.patch(f"/api/projects/{p.id}/voice", json={"tts_provider": "edge", "tts_voice": SREYMOM}).status_code == 200
    db_session.expire_all()
    assert [a.is_outdated for a in audios] == [True, False, False]
    assert units[0].voice_revision == 1
    assert units[1].voice_revision == 1


@pytest.mark.parametrize("payload", [
    {"provider": "edge", "voice": "en-US-AriaNeural"},
    {"provider": "gtts", "voice": "default"},
    {"provider": "edge"},
    {"provider": "voxcpm", "voice": "speaker display name"},
])
def test_invalid_incompatible_or_incomplete_override_rejected(client, db_session, payload):
    p, units = seed(db_session)
    assert client.patch(f"/api/projects/{p.id}/translations/{units[0].id}/voice", json=payload).status_code == 400


def test_custom_identity_availability_and_revoked_consent(client, db_session):
    p, units = seed(db_session)
    consent = VoiceConsent(speaker_name="Fixture", authorized_by="Fixture", consent_statement="Authorized", signature_hash="a"*64)
    db_session.add(consent)
    db_session.flush()
    profile = VoiceProfile(name="Fixture clone", consent_id=consent.id, reference_audio_path="fixture.wav")
    db_session.add(profile)
    db_session.commit()
    endpoint = f"/api/projects/{p.id}/translations/{units[0].id}/voice"
    with patch("app.services.tts.voxcpm.VoxCPM2TTSProvider.is_worker_online", return_value=False):
        assert client.patch(endpoint, json={"provider": "voxcpm", "voice": profile.id}).status_code == 400
        options = client.get(f"/api/projects/{p.id}/segment-voices").json()["voices"]
        assert all(v["language"] == "km" for v in options)
        assert next(v for v in options if v["voice"] == profile.id)["availability_reason"] == "Voice worker offline"
    with patch("app.services.tts.voxcpm.VoxCPM2TTSProvider.is_worker_online", return_value=True):
        assert client.patch(endpoint, json={"provider": "voxcpm", "voice": profile.id}).status_code == 200
        consent.is_authorized = False
        db_session.commit()
        with pytest.raises(VoiceNotSupportedError, match="consent"):
            validate_voice(db_session, "voxcpm", profile.id)


@pytest.mark.parametrize("change", ["override", "default", "text", "away-and-back"])
def test_inflight_result_cannot_publish_after_concurrent_change(tmp_path, change):
    engine = create_engine(f"sqlite:///{tmp_path/'race.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        p, units = seed(db)
        unit = units[0]
        old = recording(db, p, unit, tmp_path)
        old_path = old.audio_path
        pid, uid = p.id, unit.id

        def synthesize(text, output_path, **kwargs):
            output_path.write_bytes(b"new obsolete recording")
            with sessions() as other:
                op = other.get(Project, pid)
                os = other.get(TranslationSegment, uid)
                if change == "text":
                    os.khmer_text = "Changed approved words"
                elif change == "default":
                    op.tts_voice = SREYMOM
                    os.voice_revision += 1
                else:
                    set_unit_voice(other, op, os, "edge", SREYMOM)
                    if change == "away-and-back":
                        set_unit_voice(other, op, os, None, None)
                other.commit()
            return TTSAudioResult(output_path, 2, "edge", kwargs["voice"])

        with patch("app.workers.tts.get_audio_segment_path", return_value=tmp_path/"target.mp3"), patch("app.services.video.ffmpeg.FFmpegVideoProcessor.get_audio_duration", return_value=2):
            with pytest.raises(TTSGenerationError, match="changed during generation"):
                synthesize_segment_audio(pid, unit, Mock(synthesize=synthesize), db)
        db.refresh(old)
        assert old.audio_path == old_path
        assert Path(old_path).read_bytes() == b"previous recording"
    engine.dispose()


def test_worker_generates_mixed_voices_and_reuses_unmodified_recordings(db_session, tmp_path):
    p, units = seed(db_session)
    p.pipeline_version = "v1"
    set_unit_voice(db_session, p, units[1], "edge", SREYMOM)
    job = ProcessingJob(project_id=p.id, job_type="tts")
    db_session.add(job)
    db_session.commit()
    calls = []

    def synthesize(text, output_path, **kwargs):
        output_path.write_bytes(b"generated fixture")
        calls.append(kwargs["voice"])
        return TTSAudioResult(output_path, 2, "edge", kwargs["voice"])

    with patch("app.workers.tts.get_tts_provider", return_value=Mock(synthesize=synthesize)), patch("app.services.video.ffmpeg.FFmpegVideoProcessor.get_audio_duration", return_value=2):
        process_tts(p.id, job.id, db_session)
        assert job.status == JobStatus.COMPLETED
        assert calls == [PISETH, SREYMOM, PISETH]
        before = {a.translation_segment_id: a.audio_path for a in p.generated_audios}
        set_unit_voice(db_session, p, units[1], None, None)
        db_session.commit()
        calls.clear()
        process_tts(p.id, job.id, db_session)
        assert calls == [PISETH]
        after = {a.translation_segment_id: a.audio_path for a in p.generated_audios}
        assert after[units[0].id] == before[units[0].id]
        assert after[units[2].id] == before[units[2].id]
        assert after[units[1].id] != before[units[1].id]


def test_source_mapping_survives_split_reorder_and_prevents_mixed_merge(db_session):
    p, units = seed(db_session)
    set_unit_voice(db_session, p, units[0], "edge", SREYMOM)
    db_session.commit()
    members = p.transcript_segments
    # Boundaries cannot merge different source choices even when both are short.
    members[1].start_time = members[0].end_time + .1
    groups = voice_aware_groups(members, units)
    assert groups[0].voice_override == ("edge", SREYMOM)
    assert members[1].id not in groups[0].source_segment_ids
    members[0].segment_order = 9
    assert voice_aware_groups(members, units)[0].voice_override == ("edge", SREYMOM)
    # One overridden span becomes multiple children retaining occurrence identities.
    words = json.loads(members[0].words_json)
    words.append({"word": "Again", "word_id": "child-word", "start": 3, "end": 3.2})
    members[0].words_json = json.dumps(words)
    set_unit_voice(db_session, p, units[0], None, None)
    set_unit_voice(db_session, p, units[0], "edge", SREYMOM)
    db_session.commit()
    from app.services.transcription.base import TranscriptionSegment, WordTiming
    children = [TranscriptionSegment(i+1, w["start"], w["end"], w["word"], words=[WordTiming.from_dict(w)]) for i,w in enumerate(words)]
    preserve_partition(children + members[1:], units)
    choices = json.loads(units[0].voice_source_keys)
    assert all(source_keys([s]).issubset(set(choices)) for s in children)


def test_export_rejects_new_audio_revision_mismatch_and_legacy_remains_compatible(client, db_session, tmp_path):
    p, units = seed(db_session)
    path = tmp_path/"source.mp4"
    path.write_bytes(b"source fixture")
    db_session.add(Video(project_id=p.id, filename="source.mp4", file_path=str(path), file_size_bytes=14))
    audios = [recording(db_session, p, s, tmp_path) for s in units]
    audios[0].voice_revision = None
    assert audio_matches_selection(p, units[0], audios[0])
    set_unit_voice(db_session, p, units[1], "edge", SREYMOM)
    audios[1].is_outdated = False  # A bad legacy flag cannot override the identity fence.
    db_session.commit()
    assert not audio_matches_selection(p, units[1], audios[1])
    response = client.post(f"/api/projects/{p.id}/export")
    assert response.status_code == 400
    assert "outdated" in response.json()["detail"]


def test_active_export_blocks_voice_mutation(client, db_session):
    p, units = seed(db_session)
    db_session.add(ProcessingJob(project_id=p.id, job_type="dub", status=JobStatus.RUNNING))
    db_session.commit()
    response = client.patch(f"/api/projects/{p.id}/translations/{units[0].id}/voice", json={"provider": "edge", "voice": SREYMOM})
    assert response.status_code == 409


def test_manual_split_copies_legacy_assignment_and_merge_conflict_is_explicit(client, db_session):
    p, units = seed(db_session)
    first = p.transcript_segments[0]
    first.text = "One two."
    first.words_json = json.dumps([{"word": "One", "start": 2, "end": 2.4},
                                  {"word": "two.", "start": 2.4, "end": 3}])
    db_session.commit()
    set_unit_voice(db_session, p, units[0], "edge", SREYMOM)
    db_session.commit()
    response = client.post(f"/api/projects/{p.id}/transcript/{first.id}/split", json={"word_index": 1})
    assert response.status_code == 200, response.text
    db_session.expire_all()
    keys = set(json.loads(units[0].voice_source_keys))
    children = p.transcript_segments[:2]
    assert source_keys(children) == keys
    # Both split children keep the assignment; neighboring inherited unit cannot merge into it.
    choices = voice_aware_groups(p.transcript_segments, units)
    assert choices[0].voice_override == ("edge", SREYMOM)
    before = [(s.text, s.id) for s in p.transcript_segments]
    response = client.post(f"/api/projects/{p.id}/transcript/{children[-1].id}/merge-next")
    assert response.status_code == 409
    assert "different voice" in response.json()["detail"]
    db_session.expire_all()
    assert [(s.text, s.id) for s in p.transcript_segments] == before


def test_resegmentation_preserves_voice_word_identity_and_approved_khmer(client, db_session):
    from app.services.transcription.base import TranscriptionSegment, WordTiming
    p, units = seed(db_session)
    units[0].is_manually_edited = True
    set_unit_voice(db_session, p, units[0], "edge", SREYMOM)
    p.raw_transcript_json = json.dumps([
        TranscriptionSegment(s.segment_order, s.start_time, s.end_time, s.text,
                             words=[WordTiming.from_dict(w) for w in json.loads(s.words_json)]).to_dict()
        for s in p.transcript_segments
    ])
    approved = units[0].khmer_text
    db_session.commit()
    response = client.post(f"/api/projects/{p.id}/transcript/segmentation/apply", json={"mode": "sentence", "confirm": True})
    assert response.status_code == 200, response.text
    db_session.expire_all()
    assert units[0].khmer_text == approved
    assert units[0].voice_override_id == SREYMOM
    groups = voice_aware_groups(p.transcript_segments, p.translation_segments)
    assert groups[0].voice_override == ("edge", SREYMOM)
    assert json.loads(units[0].voice_source_keys) == ["word:word-1"]


def test_mixed_voice_timing_uses_measured_audio_from_each_voice(db_session, tmp_path):
    import subprocess
    from app.services.video.ffmpeg import FFmpegVideoProcessor
    from app.services.dubbing.timing_optimizer import TimingOptimizerService
    p, units = seed(db_session)
    set_unit_voice(db_session, p, units[1], "edge", SREYMOM)
    db_session.add(Video(project_id=p.id, filename="fixture.mp4", file_path="fixture.mp4",
                         file_size_bytes=1, duration_seconds=20))
    processor = FFmpegVideoProcessor()
    for index, unit in enumerate(units):
        unit.start_time = index * 6
        unit.end_time = index * 6 + 5
        path = tmp_path/f"voice-{index}.mp3"
        duration = 1.5 + index * .8
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"sine=frequency=440:duration={duration}", str(path)], check=True)
        provider, voice = effective_voice(p, unit)
        db_session.add(GeneratedAudio(project_id=p.id, translation_segment_id=unit.id,
                                      audio_path=str(path), duration_seconds=processor.get_audio_duration(path),
                                      provider=provider, voice=voice, voice_revision=unit.voice_revision))
    db_session.commit()
    analysis = TimingOptimizerService().analyze_timeline(p.id, db_session)
    assert len(analysis) == 3
    assert all(a.tempo_factor == 1 for a in analysis)
    assert analysis[0].raw_duration < analysis[1].raw_duration < analysis[2].raw_duration
    assert all(a.processed_duration <= a.end_time-a.start_time for a in analysis)


def test_export_cannot_become_current_after_selection_changes_while_rendering(db_session, tmp_path):
    from app.services.dubbing.pipeline import DubbingPipeline
    from app.services.dubbing.exporter import ExportResult
    p, units = seed(db_session)
    original = tmp_path/"source.mp4"
    original.write_bytes(b"fixture")
    video = Video(project_id=p.id, filename=original.name, file_path=str(original),
                  file_size_bytes=7, duration_seconds=10)
    db_session.add(video)
    for unit in units:
        recording(db_session, p, unit, tmp_path)
    db_session.commit()
    synchronizer = Mock()
    synchronizer.synchronize.return_value = Mock(timeline_path=tmp_path/"timeline.wav", conflicts=[])
    exporter = Mock()

    def export(**kwargs):
        set_unit_voice(db_session, p, units[0], "edge", SREYMOM)
        db_session.commit()
        return ExportResult(tmp_path/"export.mp4", 10, 10, "h264", "aac")

    exporter.export.side_effect = export
    with pytest.raises(ValueError, match="changed during export"):
        DubbingPipeline(synchronizer=synchronizer, exporter=exporter).run(p.id, db_session)
    db_session.refresh(video)
    assert video.is_export_outdated is True


def test_offline_selected_custom_voice_sets_failure_without_fallback(db_session):
    p, units = seed(db_session)
    consent = VoiceConsent(speaker_name="Fixture", authorized_by="Fixture", consent_statement="Authorized", signature_hash="b"*64)
    db_session.add(consent)
    db_session.flush()
    profile = VoiceProfile(name="Offline fixture", consent_id=consent.id, reference_audio_path="fixture.wav")
    db_session.add(profile)
    db_session.flush()
    set_unit_voice(db_session, p, units[0], "voxcpm", profile.id)
    job = ProcessingJob(project_id=p.id, job_type="tts")
    db_session.add(job)
    db_session.commit()
    with patch("app.services.tts.voxcpm.VoxCPM2TTSProvider.is_worker_online", return_value=False), patch("app.workers.tts.get_tts_provider") as factory:
        process_tts(p.id, job.id, db_session)
        factory.assert_not_called()
    assert job.status == JobStatus.FAILED
    db_session.refresh(units[0])
    assert "offline" in units[0].tts_error
    assert db_session.query(GeneratedAudio).filter_by(project_id=p.id).count() == 0


def test_legacy_named_custom_default_resolves_to_profile_identity(db_session):
    p, units = seed(db_session)
    consent = VoiceConsent(speaker_name="Fixture", authorized_by="Fixture", consent_statement="Authorized", signature_hash="c"*64)
    db_session.add(consent)
    db_session.flush()
    profile = VoiceProfile(name="Old display name", consent_id=consent.id, reference_audio_path="fixture.wav")
    db_session.add(profile)
    db_session.flush()
    p.tts_provider, p.tts_voice = "custom", "custom:Old display name"
    db_session.commit()
    assert effective_voice(p, units[0]) == ("voxcpm", profile.id)
    assert p.tts_voice == "custom:Old display name"


def test_standard_voice_validation_does_not_probe_unrelated_custom_worker(db_session):
    with patch("app.services.tts.voxcpm.VoxCPM2TTSProvider.is_worker_online", side_effect=AssertionError("Unexpected custom worker probe")):
        validate_voice(db_session, "edge", PISETH)
