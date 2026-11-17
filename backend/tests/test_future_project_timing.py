from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.models.project import Project, TranslationSegment, GeneratedAudio
from app.services.dubbing.duration_repair import DurationRepairService, preserves_protected_tokens
from app.services.translation.timing import speaking_budget
from app.services.tts.base import TTSAudioResult
from app.services.tts.exceptions import TTSGenerationError
from app.workers.tts import synthesize_segment_audio


@pytest.mark.parametrize("bounds,expected", [((0,3,3),2.87), ((0,3,10),3.22),
    ((0,3,None),2.87), ((0,.05,.05),.1), ((2,4,3),.87)])
def test_translation_reserves_pause_and_does_not_fill_long_gaps(bounds, expected):
    assert speaking_budget(*bounds) == expected


@pytest.mark.parametrize("before,after,ok", [
    ("៣ AI មិនបានទេ", "3 AI មិនបាន", True),
    ("៣ AI មិនបានទេ", "២ AI មិនបាន", False),
    ("៣ AI មិនបានទេ", "៣ AI បាន", False),
    ("៣ AI មិនបានទេ", "៣ ML មិនបាន", False),
])
def test_timing_retry_preserves_numbers_negation_and_identifiers(before, after, ok):
    assert preserves_protected_tokens(before, after) == ok


def fixture(db, tmp_path):
    project = Project(title="Future project fixture", translation_provider="custom",
                      tts_provider="edge", tts_voice="km-KH-PisethNeural")
    db.add(project); db.flush()
    segment = TranslationSegment(project_id=project.id, segment_order=1,
        source_text="He is still waiting.", khmer_text="គាត់នៅតែកំពុងរង់ចាំនៅទីនេះ។")
    db.add(segment); db.flush()
    master = tmp_path / "old.mp3"; master.write_bytes(b"original complete recording")
    audio = GeneratedAudio(project_id=project.id, translation_segment_id=segment.id,
        audio_path=str(master), duration_seconds=5, provider="edge", voice=project.tts_voice)
    db.add(audio); db.commit()
    item = SimpleNamespace(translation_segment_id=segment.id, raw_duration=5,
        trimmed_duration=5, effective_window=3, english_text=segment.source_text, segment_order=1)
    return project, segment, audio, item


@pytest.mark.parametrize("duration,accepted", [(3.2,True),(4.8,False)])
def test_replacement_text_and_measured_audio_publish_together_or_preserve_both(db_session, tmp_path, duration, accepted):
    project, segment, audio, item = fixture(db_session, tmp_path)
    original_text, original_path = segment.khmer_text, audio.audio_path
    shorter = "គាត់នៅតែរង់ចាំ។"
    def synthesize(text, output_path, **kwargs):
        output_path.write_bytes(b"candidate complete recording")
        return TTSAudioResult(output_path, duration, "edge", project.tts_voice)
    translator = Mock(improve_translation=Mock(return_value=SimpleNamespace(improved_khmer_text=shorter)))
    provider = Mock(synthesize=Mock(side_effect=synthesize))
    optimizer = Mock(analyze_timeline=Mock(return_value=[item]))
    with patch("app.services.dubbing.duration_repair.get_translation_provider",return_value=translator), \
         patch("app.services.dubbing.duration_repair.get_tts_provider",return_value=provider), \
         patch("app.services.dubbing.duration_repair.validate_voice"), \
         patch("app.workers.tts.get_audio_segment_path",return_value=tmp_path/"new.mp3"), \
         patch("app.services.video.ffmpeg.FFmpegVideoProcessor.get_audio_duration",return_value=duration):
        result = DurationRepairService(optimizer).repair_project(project.id,db_session,seed=12)
    db_session.refresh(segment);db_session.refresh(audio)
    assert result["updated"] == int(accepted)
    assert segment.khmer_text == (shorter if accepted else original_text)
    assert Path(original_path).read_bytes() == b"original complete recording"
    assert audio.duration_seconds == (duration if accepted else 5)
    assert (audio.audio_path != original_path) == accepted
    assert audio.voice == project.tts_voice


@pytest.mark.parametrize("manual,fits", [(True,False),(False,True)])
def test_approved_text_and_carried_delay_do_not_trigger_rewrite(db_session,tmp_path,manual,fits):
    project,segment,_,item = fixture(db_session,tmp_path)
    segment.is_manually_edited=manual;db_session.commit()
    if fits: item.trimmed_duration=2.5
    translator=Mock()
    with patch("app.services.dubbing.duration_repair.get_translation_provider",return_value=translator):
        result=DurationRepairService(Mock(analyze_timeline=Mock(return_value=[item]))).repair_project(project.id,db_session)
    assert result == {"attempted":0,"updated":0}
    translator.improve_translation.assert_not_called()


def test_concurrent_manual_approval_blocks_candidate_publication(db_session,tmp_path):
    project,segment,audio,_=fixture(db_session,tmp_path)
    previous=segment.khmer_text
    segment.is_manually_edited=True;db_session.commit()
    with pytest.raises(TTSGenerationError,match="manually approved"):
        synthesize_segment_audio(project.id,segment,Mock(),db_session,
            candidate_text="គាត់រង់ចាំ។",expected_text=previous,max_duration=3)
    assert audio.duration_seconds==5


def test_offline_translator_keeps_complete_original_and_reports_unresolved(db_session,tmp_path):
    project,segment,audio,item=fixture(db_session,tmp_path)
    previous=segment.khmer_text
    translator=Mock(improve_translation=Mock(side_effect=NotImplementedError))
    with patch("app.services.dubbing.duration_repair.get_translation_provider",return_value=translator):
        result=DurationRepairService(Mock(analyze_timeline=Mock(return_value=[item]))).repair_project(project.id,db_session)
    assert result["updated"]==0
    assert segment.khmer_text==previous and audio.duration_seconds==5


def test_new_batch_generation_automatically_runs_timing_repair(db_session,tmp_path):
    from app.models.project import ProcessingJob, JobStatus
    from app.workers.tts import process_tts
    project,segment,audio,_=fixture(db_session,tmp_path)
    job=ProcessingJob(project_id=project.id,job_type="tts",status=JobStatus.PENDING)
    db_session.add(job);db_session.commit()
    result=SimpleNamespace(total_segments=1,fitted_naturally=1,speed_adjusted=0,
                           sentence_optimized=0,unresolved_conflicts=0)
    with patch("app.workers.tts.resolve_audio_file",return_value=Path(audio.audio_path)), \
         patch("app.workers.tts.audio_matches_selection",return_value=True), \
         patch("app.services.dubbing.duration_repair.DurationRepairService.repair_project") as repair, \
         patch("app.services.dubbing.timing_optimizer.TimingOptimizerService.optimize_project",return_value=result):
        process_tts(project.id,job.id,db_session)
    repair.assert_called_once()
    db_session.refresh(job)
    assert job.status==JobStatus.COMPLETED


def test_manual_edit_during_candidate_inference_keeps_current_audio(db_session,tmp_path):
    project,segment,audio,_=fixture(db_session,tmp_path)
    previous=segment.khmer_text
    def synthesize(text,output_path,**kwargs):
        segment.is_manually_edited=True
        db_session.commit()
        output_path.write_bytes(b"candidate")
        return TTSAudioResult(output_path,3,"edge",project.tts_voice)
    with patch("app.workers.tts.get_audio_segment_path",return_value=tmp_path/"new.mp3"), \
         patch("app.services.video.ffmpeg.FFmpegVideoProcessor.get_audio_duration",return_value=3):
        with pytest.raises(TTSGenerationError,match="changed during generation"):
            synthesize_segment_audio(project.id,segment,Mock(synthesize=synthesize),db_session,
                candidate_text="គាត់រង់ចាំ។",expected_text=previous,max_duration=3.5)
    db_session.refresh(audio);db_session.refresh(segment)
    assert audio.duration_seconds==5 and segment.khmer_text==previous
