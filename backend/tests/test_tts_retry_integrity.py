from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.models.project import Project, TranslationSegment, GeneratedAudio
from app.models.voice import VoiceConsent, VoiceProfile
from app.services.tts.base import TTSAudioResult
from app.services.tts.exceptions import TTSGenerationError
from app.workers.tts import synthesize_segment_audio


def setup_segment(db):
    consent = VoiceConsent(speaker_name='Fixture', authorized_by='Fixture', consent_statement='Test authorization', signature_hash='f'*64)
    db.add(consent)
    db.flush()
    db.add(VoiceProfile(id='authorized', name='Fixture', reference_audio_path='fixture.wav', consent_id=consent.id))
    project = Project(title='Retry integrity', tts_provider='voxcpm', tts_voice='authorized')
    db.add(project)
    db.flush()
    segment = TranslationSegment(project_id=project.id, segment_order=1, khmer_text='សួស្តីអ្នកទាំងអស់គ្នា')
    db.add(segment)
    db.commit()
    return project, segment


def test_rejected_retry_preserves_existing_audio_and_record(db_session, tmp_path):
    project, segment = setup_segment(db_session)
    output = tmp_path / 'existing.mp3'
    output.write_bytes(b'previous approved recording')
    record = GeneratedAudio(project_id=project.id, translation_segment_id=segment.id, audio_path=str(output), duration_seconds=7, provider='voxcpm', voice='authorized')
    db_session.add(record)
    db_session.commit()
    paths = []

    def synthesize(text, output_path, **kwargs):
        paths.append(output_path)
        output_path.write_bytes(b'rejected recording')
        return TTSAudioResult(output_path, 1, 'voxcpm', 'authorized')

    provider = Mock(synthesize=Mock(side_effect=synthesize))
    with patch('app.workers.tts.get_audio_segment_path', return_value=output), patch('app.services.video.ffmpeg.FFmpegVideoProcessor.get_audio_duration', return_value=1), patch('app.services.dubbing.speech_guard.SpeechGuardService.inspect_speech_audio', return_value=Mock(completeness_status='requires_review', warning_message='possible cutoff')):
        with pytest.raises(TTSGenerationError, match='existing audio preserved'):
            synthesize_segment_audio(project.id, segment, provider, db_session, seed=42)
    assert len(paths) == 2 and paths[0] != paths[1]
    assert output.read_bytes() == b'previous approved recording'
    db_session.refresh(record)
    assert record.duration_seconds == 7
    assert all(path.exists() for path in paths)


def test_retry_selects_valid_recording_using_measured_duration(db_session, tmp_path):
    project, segment = setup_segment(db_session)
    output = tmp_path / 'speech.mp3'
    paths = []

    def synthesize(text, output_path, **kwargs):
        paths.append(output_path)
        output_path.write_bytes(b'first' if len(paths) == 1 else b'second valid recording')
        return TTSAudioResult(output_path, 99, 'voxcpm', kwargs['voice'])

    provider = Mock(synthesize=Mock(side_effect=synthesize))
    with patch('app.workers.tts.get_audio_segment_path', return_value=output), patch('app.services.video.ffmpeg.FFmpegVideoProcessor.get_audio_duration', side_effect=[1, 4]), patch('app.services.dubbing.speech_guard.SpeechGuardService.inspect_speech_audio', side_effect=[Mock(completeness_status='requires_review', warning_message='short'), Mock(completeness_status='plausibly_complete')]):
        record = synthesize_segment_audio(project.id, segment, provider, db_session, seed=42)
    assert Path(record.audio_path).read_bytes() == b'second valid recording'
    assert record.audio_path != str(output)
    assert record.voice_revision == 0
    assert record.duration_seconds == 4
    assert record.voice == 'authorized'
    assert [c.kwargs['seed'] for c in provider.synthesize.call_args_list] == [42, 43]
    assert paths[0].read_bytes() == b'first'
