"""Non-destructive full-video acceptance; unique project and checkpointed evidence."""
import json
import logging
import sys
import uuid
from pathlib import Path

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.project import Project, Video, ProcessingJob, JobStatus
from app.services.video.ffmpeg import FFmpegVideoProcessor
from app.services.dubbing.timing_optimizer import TimingOptimizerService
from app.services.dubbing.pipeline import DubbingPipeline
from app.services.dubbing.speech_guard import SpeechGuardService
from app.workers.transcription import process_transcription
from app.workers.translation import process_translation
from app.workers.tts import process_tts

SOURCE = Path('/app/data/uploads/aa4afefc-ae6d-434d-ab84-caeeea0b30c9/A_Wise_Man_Taught_a_Lost_Boy_About_Choosing_Himself.mp4')
VOICE = 'a34b14df-4d3d-41ca-9cd7-55a9a573e66a'
logging.basicConfig(level=logging.INFO)
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

def main():
    with SessionLocal() as db:
        if len(sys.argv) > 1:
            project = db.query(Project).filter_by(id=sys.argv[1]).one()
            if not project.title.startswith('[Repair acceptance]'):
                raise ValueError('Only isolated acceptance projects can be resumed')
        else:
            project = Project(id=str(uuid.uuid4()), title='[Repair acceptance] A Wise Man', original_video_path=str(SOURCE), original_language='en', target_language='km', tts_provider='voxcpm', tts_voice=VOICE, translation_provider='custom', pipeline_version='v2.3', segmentation_mode='dubbing')
            db.add(project)
            db.commit()
        db.get_bind().echo = False
        root = Path(settings.DATA_DIR) / 'projects' / project.id
        root.mkdir(parents=True, exist_ok=True)
        print('ACCEPTANCE_PROJECT', project.id, flush=True)
        vp = FFmpegVideoProcessor()
        if not project.video:
            metadata = vp.get_metadata(SOURCE)
            audio = root / 'source_audio.wav'
            vp.extract_audio(SOURCE, audio)
            db.add(Video(project_id=project.id, filename=SOURCE.name, file_path=str(SOURCE), file_size_bytes=SOURCE.stat().st_size, duration_seconds=metadata.duration_seconds, width=metadata.width, height=metadata.height, video_codec=metadata.video_codec, audio_codec=metadata.audio_codec, extracted_audio_path=str(audio)))
            db.commit()
        for kind, worker, done in [('transcription',process_transcription, bool(project.transcript_segments)), ('translation',process_translation,bool(project.translation_segments)), ('tts',process_tts, bool(project.generated_audios) and len(project.generated_audios)==len(project.translation_segments))]:
            if done:
                continue
            job=ProcessingJob(project_id=project.id,job_type=kind,status=JobStatus.PENDING)
            db.add(job); db.commit()
            worker(project.id,job.id,db=db)
            db.refresh(job)
            print('STAGE',kind,job.status,job.error_message,flush=True)
            if job.status != JobStatus.COMPLETED:
                raise RuntimeError(f'{kind}: {job.error_message}')
            db.refresh(project)
        analyses=TimingOptimizerService().analyze_timeline(project.id,db)
        raw=json.loads(project.raw_transcript_json)
        raw_words=[w for s in raw for w in (s.get('words') or [])]
        words=[w for s in project.transcript_segments for w in json.loads(s.words_json or '[]')]
        report={'project_id':project.id,'source':str(SOURCE),'duration':project.video.duration_seconds,'raw_words':len(raw_words),'segmented_words':len(words),'word_sequence_preserved':raw_words==words,'invalid_word_timestamps':[w for w in raw_words if w['end']<=w['start']],'transcript_segments':len(project.transcript_segments),'tts_units':len(analyses),'raw_total':sum(a.raw_duration for a in analyses),'natural_units':sum(a.tempo_factor==1 for a in analyses),'adjusted_units':sum(a.tempo_factor>1 for a in analyses),'conflicts':sum(a.overflow_seconds>0.05 for a in analyses),'overflow':sum(a.overflow_seconds for a in analyses),'max_overflow':max((a.overflow_seconds for a in analyses),default=0),'max_speed':max((a.tempo_factor for a in analyses),default=1),'speech_inspections':[SpeechGuardService().inspect_speech_audio(Path(a.audio_path),a.khmer_text).to_dict() for a in analyses if a.audio_path]}
        (root/'acceptance_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
        try:
            result=DubbingPipeline().run(project.id,db,strict_validation=True,max_tempo_factor=1.25,on_progress=lambda p,m:print(p,m,flush=True))
            report['export']={'path':str(result.export_result.video_path),'duration':result.export_result.duration_seconds,'status':'completed'}
        except Exception as exc:
            report['export']={'status':'blocked','error':str(exc)}
            raise
        finally:
            (root/'acceptance_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
        print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
