"""Full-stream and per-unit waveform audit for an isolated acceptance export."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from app.database.session import SessionLocal
from app.models.project import Project
from app.services.dubbing.scheduler import TimelineScheduler
from app.services.dubbing.speech_guard import SpeechGuardService


def probe(path: Path) -> dict:
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def pcm(path: Path) -> np.ndarray:
    result = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(path), '-map', '0:a:0', '-ar', '44100', '-ac', '1', '-f', 'f32le', '-'], check=True, capture_output=True)
    return np.frombuffer(result.stdout, dtype=np.float32)


def stream_hash(path: Path) -> str:
    result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:v:0', '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-'], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def main() -> None:
    with SessionLocal() as db:
        db.get_bind().echo = False
        project = db.query(Project).filter_by(id=sys.argv[1]).one()
        if not project.title.startswith(('[Repair acceptance]', '[Mixed voice acceptance]')):
            raise ValueError('Only isolated test exports may be audited here')
        source = Path(project.video.file_path)
        exported = Path(project.video.exported_video_path)
        timeline = Path(project.video.audio_timeline_path)
        root = timeline.parent
        items = []
        for unit in project.translation_segments:
            audio = unit.generated_audio
            items.append({'segment_order':unit.segment_order,'segment_id':unit.id,'start_time':unit.start_time,'end_time':unit.end_time,'raw_duration':audio.duration_seconds,'audio_path':Path(audio.audio_path),'khmer_text':unit.khmer_text})
        groups = TimelineScheduler().schedule_timeline(items, project.video.duration_seconds)
        pieces = [p for g in groups for p in g.pieces]
        final_pcm = pcm(exported)
        timeline_pcm = pcm(timeline)
        unit_results = []
        for piece in pieces:
            rendered = pcm(piece.processed_audio_path)
            offset = round(piece.scheduled_start * 44100)
            length = min(len(rendered), len(final_pcm)-offset)
            correlation = float(np.corrcoef(rendered[:length],final_pcm[offset:offset+length])[0,1]) if length>1 else 0
            unit_results.append({'unit_id':piece.segment_id,'order':piece.segment_order,'raw_duration':piece.raw_duration,'processed_duration':piece.processed_duration,'tempo':piece.applied_tempo,'scheduled_start':piece.scheduled_start,'scheduled_end':piece.scheduled_end,'local_overflow_seconds':piece.local_overflow_seconds,'alignment_delay_seconds':piece.alignment_delay_seconds,'final_audio_correlation':correlation,'processed_inspection':SpeechGuardService().inspect_speech_audio(piece.processed_audio_path).to_dict()})
        # Decode every frame of both exported streams, not a sample clip.
        subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(exported),'-map','0:v:0','-map','0:a:0','-f','null','-'],check=True,capture_output=True)
        length=min(len(final_pcm),len(timeline_pcm))
        report={'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_probe':probe(source),'export_probe':probe(exported),'video_stream_unchanged':stream_hash(source)==stream_hash(exported),'full_decode_passed':True,'timeline_to_final_audio_correlation':float(np.corrcoef(timeline_pcm[:length],final_pcm[:length])[0,1]),'unintended_overlaps':sum(a.scheduled_end>b.scheduled_start+0.001 for a,b in zip(pieces,pieces[1:])),'mean_start_deviation':sum(abs(p.scheduled_start-p.start_time) for p in pieces)/len(pieces),'maximum_start_deviation':max(abs(p.scheduled_start-p.start_time) for p in pieces),'alignment_review_units':sum(p.local_overflow_seconds>0.05 or abs(p.alignment_delay_seconds)>0.5 for p in pieces),'schedule':unit_results,'lexical_verification':'human_listening_required','naturalness_verification':'human_listening_required','scene_boundary_verification':'not_performed'}
        destination=root/'full_export_audit.json'
        destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('AUDIT',destination,'UNITS',len(pieces),'ALIGNMENT_REVIEW',report['alignment_review_units'],'MAX_DEVIATION',report['maximum_start_deviation'],'MIN_CORRELATION',min(u['final_audio_correlation'] for u in unit_results),flush=True)


if __name__ == '__main__':
    main()
