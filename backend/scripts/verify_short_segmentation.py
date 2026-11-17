"""Read-only source media; uniquely named isolated full-video segmentation evidence."""
import copy
import hashlib
import json
import sys
import uuid
from pathlib import Path

from app.database.session import SessionLocal
from app.models.project import Project, Video
from app.services.video.ffmpeg import FFmpegVideoProcessor
from app.services.transcription.whisper import FasterWhisperTranscriptionProvider
from app.services.transcription.segmentation import segment_transcript

SOURCE = Path('/app/data/uploads/0018b756-0169-4883-9c7d-d154c338802b/When_Everyone_Says_Your_Dream_is_Impossible_-_Remember_the_Bamboo_Tree.mp4')


def stats(segments):
    durations = [s.end_time-s.start_time for s in segments]
    return {'segments':len(segments),'words':sum(len(s.words or []) for s in segments),
            'average_duration':sum(durations)/len(durations),'minimum_duration':min(durations),
            'maximum_duration':max(durations),'over_five_seconds':sum(d>5.000001 for d in durations),
            'under_one_second':sum(d<1 for d in durations),
            'overlapping_segments':sum(a.end_time>b.start_time+0.000001 for a,b in zip(segments,segments[1:])),
            'invalid_word_intervals':sum(w.end<=w.start for s in segments for w in s.words or [])}


def main():
    with SessionLocal() as db:
        db.get_bind().echo=False
        if len(sys.argv)>1:
            project=db.query(Project).filter_by(id=sys.argv[1]).one()
            if not project.title.startswith('[Segmentation acceptance]'):
                raise ValueError('Only isolated segmentation acceptance projects may be used')
        else:
            project=Project(id=str(uuid.uuid4()),title='[Segmentation acceptance] Bamboo Tree',original_video_path=str(SOURCE),original_language='en',segmentation_mode='sentence')
            db.add(project);db.commit()
        root=Path('/app/data/projects')/project.id
        root.mkdir(parents=True,exist_ok=True)
        print('PROJECT',project.id,flush=True)
        processor=FFmpegVideoProcessor()
        audio=root/'source_audio.wav'
        if not audio.exists():
            processor.extract_audio(SOURCE,audio)
        if not project.video:
            metadata=processor.get_metadata(SOURCE)
            db.add(Video(project_id=project.id,filename=SOURCE.name,file_path=str(SOURCE),file_size_bytes=SOURCE.stat().st_size,duration_seconds=metadata.duration_seconds,width=metadata.width,height=metadata.height,video_codec=metadata.video_codec,audio_codec=metadata.audio_codec,extracted_audio_path=str(audio)))
            db.commit()
        provider=FasterWhisperTranscriptionProvider()
        raw=provider.transcribe(audio,language='en',word_timestamps=True)
        baseline_path=root/'segmentation_before.json'
        if baseline_path.exists():
            raise FileExistsError('Baseline evidence is immutable')
        report={'source':str(SOURCE),'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                'audio_duration':processor.get_audio_duration(audio),'vad_enabled':provider.vad_filter,
                'model':provider.model_size,'raw':[s.to_dict() for s in raw],'modes':{}}
        for mode in ('original','sentence','dubbing'):
            segmented=segment_transcript(copy.deepcopy(raw),mode=mode)
            report['modes'][mode]={'metrics':stats(segmented),'segments':[s.to_dict() for s in segmented]}
        baseline_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('BASELINE',json.dumps({k:v['metrics'] for k,v in report['modes'].items()}),flush=True)


if __name__=='__main__':
    main()
