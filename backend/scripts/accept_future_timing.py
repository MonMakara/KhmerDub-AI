"""Run real voice timing repair on an isolated copy of three reported units."""
import hashlib
import json
import shutil
from pathlib import Path

from app.database.session import SessionLocal
from app.models.project import Project, Video, TranslationSegment, GeneratedAudio
from app.services.dubbing.duration_repair import DurationRepairService
from app.services.dubbing.timing_optimizer import TimingOptimizerService
from app.core.storage import get_audio_segment_path

REPORT = Path('/app/data/temp/future-project-timing-acceptance.json')


def main():
    with SessionLocal() as db:
        db.get_bind().echo = False
        source = db.get(Project, '1c5b2a58-d9ba-4f0e-b51e-facdcf77d548')
        originals = db.query(TranslationSegment).filter_by(project_id=source.id).filter(
            TranslationSegment.segment_order.in_([67,68,69])).order_by(TranslationSegment.segment_order).all()
        snapshot = [(s.id,s.khmer_text,s.generated_audio.audio_path,
            hashlib.sha256(Path(s.generated_audio.audio_path).read_bytes()).hexdigest()) for s in originals]
        project = Project(title='[Timing repair acceptance] Future projects', pipeline_version='v2.3',
            translation_provider=source.translation_provider, tts_provider=source.tts_provider, tts_voice=source.tts_voice)
        db.add(project); db.flush()
        offset = originals[0].start_time
        # Timing-only fixture: original media remains read-only; no video export.
        db.add(Video(project_id=project.id, filename='Timing-only fixture',file_path=source.video.file_path,
            file_size_bytes=source.video.file_size_bytes,duration_seconds=source.video.duration_seconds-offset))
        for index,s in enumerate(originals,1):
            t = TranslationSegment(project_id=project.id,segment_order=index,start_time=s.start_time-offset,
                end_time=s.end_time-offset,source_text=s.source_text,khmer_text=s.khmer_text,
                voice_override_id=s.voice_override_id,voice_override_provider=s.voice_override_provider)
            db.add(t);db.flush()
            path=get_audio_segment_path(project.id,t.id)
            path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(s.generated_audio.audio_path,path)
            db.add(GeneratedAudio(project_id=project.id,translation_segment_id=t.id,audio_path=str(path),
                duration_seconds=s.generated_audio.duration_seconds,provider=s.generated_audio.provider,
                voice=s.generated_audio.voice,voice_revision=0))
        db.commit()
        optimizer=TimingOptimizerService()
        before=optimizer.analyze_timeline(project.id,db)
        REPORT.write_text(json.dumps({'project_id':project.id,'status':'running'},indent=2))
        result=DurationRepairService(optimizer).repair_project(project.id,db,seed=20261031)
        after=optimizer.analyze_timeline(project.id,db)
        for ident,text,path,digest in snapshot:
            db.refresh(db.get(TranslationSegment,ident))
            assert db.get(TranslationSegment,ident).khmer_text==text
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
        def summarize(items):
            return [{k:getattr(a,k) for k in ('segment_order','raw_duration','effective_window',
                'tempo_factor','status','overflow_seconds','khmer_text')} for a in items]
        report={'project_id':project.id,'originals_unchanged':True,'repair':result,
                'before':summarize(before),'after':summarize(after),
                'scope':'Three isolated timing units; not a complete-video export or human semantic assessment.'}
        REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
