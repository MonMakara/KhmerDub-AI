"""Regression coverage for measured schedule/export agreement."""
import subprocess
from pathlib import Path

import pytest

from app.services.dubbing.scheduler import TimelineScheduler
from app.services.video.ffmpeg import FFmpegVideoProcessor


def test_schedule_uses_rendered_duration_and_reuses_raw_variant(tmp_path: Path):
    raw = tmp_path / 'raw.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2.4', str(raw)], check=True)
    original = raw.read_bytes()
    items = [{'segment_order': 1, 'segment_id': 'stable-unit', 'start_time': 0.0, 'end_time': 2.0, 'orig_duration': 2.0, 'raw_duration': 2.4, 'audio_path': raw}]
    scheduler = TimelineScheduler()
    first = scheduler.schedule_timeline(items, target_duration=2.1)[0].pieces[0]
    assert first.processed_audio_path.is_file()
    measured = FFmpegVideoProcessor().get_audio_duration(first.processed_audio_path)
    assert first.processed_duration == measured
    assert first.scheduled_end == first.scheduled_start + measured
    assert 1 < first.applied_tempo <= 1.25
    stamp = first.processed_audio_path.stat().st_mtime_ns
    second = scheduler.schedule_timeline(items, target_duration=2.1)[0].pieces[0]
    assert second.processed_audio_path == first.processed_audio_path
    assert second.processed_audio_path.stat().st_mtime_ns == stamp
    assert raw.read_bytes() == original


def test_measured_overflow_marks_piece_not_just_group(monkeypatch):
    scheduler = TimelineScheduler()
    # A plausible prediction fits, but the rendered duration must determine readiness.
    monkeypatch.setattr(scheduler, '_measure_variant', lambda *args: (Path('/measured.wav'), 3.0))
    group = scheduler.schedule_timeline([{'segment_order': 1, 'start_time': 0, 'end_time': 2, 'raw_duration': 1.0}], target_duration=2)[0]
    assert group.group_overflow > 0
    assert group.pieces[0].status == 'needs_optimization'
    assert group.pieces[0].overflow_seconds == pytest.approx(group.group_overflow)


def test_export_status_exposes_authoritative_unit_schedule(client, db_session, tmp_path):
    from app.models.project import Project, Video, TranscriptSegment, TranslationSegment, GeneratedAudio

    raw = tmp_path / 'voice.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', str(raw)], check=True)
    project = Project(title='Shared schedule', pipeline_version='v2.3')
    db_session.add(project)
    db_session.flush()
    db_session.add(Video(project_id=project.id, filename='test.mp4', file_path=str(tmp_path/'test.mp4'), file_size_bytes=1, duration_seconds=3))
    transcript = TranscriptSegment(project_id=project.id, segment_order=1, start_time=0, end_time=2, text='Source phrase')
    db_session.add(transcript)
    db_session.flush()
    unit = TranslationSegment(project_id=project.id, transcript_segment_id=transcript.id, segment_order=1, start_time=0, end_time=2, khmer_text='សួស្តី')
    db_session.add(unit)
    db_session.flush()
    db_session.add(GeneratedAudio(project_id=project.id, translation_segment_id=unit.id, audio_path=str(raw), duration_seconds=1))
    db_session.commit()
    response = client.get(f'/api/projects/{project.id}/export/status')
    assert response.status_code == 200
    data = response.json()
    scheduled = data['timing_summary']['schedule'][0]
    assert scheduled['translation_segment_id'] == unit.id
    assert scheduled['tempo_factor'] == 1
    assert scheduled['scheduled_end'] == scheduled['scheduled_start'] + scheduled['processed_duration']
    assert not data['timing_conflicts']


def test_export_never_hides_excess_speech_with_duration_cutoff(tmp_path):
    from app.services.dubbing.exporter import VideoExportService
    from app.services.video.exceptions import VideoProcessingError

    source = tmp_path / 'source.mp4'
    speech = tmp_path / 'full-speech.wav'
    output = tmp_path / 'export.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=32x32:duration=1', '-c:v', 'libx264', str(source)], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=2', str(speech)], check=True)
    with pytest.raises(VideoProcessingError, match='duration mismatch'):
        VideoExportService().export(source, speech, output, expected_duration=1)
    assert not output.exists()
    assert FFmpegVideoProcessor().get_audio_duration(speech) == pytest.approx(2)


def test_mixed_waveform_matches_every_scheduled_piece_without_rounding_drift(tmp_path):
    import wave
    from app.services.dubbing.synchronizer import AudioSynchronizationService

    raw = tmp_path / 'fractional.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=0.500123:sample_rate=44100', '-ac', '2', str(raw)], check=True)
    duration = FFmpegVideoProcessor().get_audio_duration(raw)
    items = [{'idx':i,'segment_order':i+1,'segment_id':str(i),'start_time':i*0.502345,'end_time':i*0.502345+0.501,'raw_duration':duration,'audio_path':raw} for i in range(3)]
    pieces = [p for g in TimelineScheduler().schedule_timeline(items, 2) for p in g.pieces]
    output = tmp_path / 'timeline.wav'
    AudioSynchronizationService().synchronize_timed_segments('drift',items,output,target_duration=2,strict_validation=True,pipeline_version='v2.3')
    with wave.open(str(output), 'rb') as timeline:
        for piece in pieces:
            with wave.open(str(piece.processed_audio_path),'rb') as rendered:
                timeline.setpos(round(piece.scheduled_start*44100))
                assert timeline.readframes(rendered.getnframes()) == rendered.readframes(rendered.getnframes())
