"""Full original-video transcription, VAD comparison and segmentation acceptance."""
import copy
import hashlib
import html
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np
from faster_whisper.audio import decode_audio
from faster_whisper.vad import get_speech_timestamps, VadOptions

from app.database.session import SessionLocal
from app.models.project import Project, ProcessingJob, JobStatus
from app.services.transcription.base import TranscriptionSegment
from app.services.transcription.segmentation import segment_transcript, validate_word_coverage
from app.services.transcription.whisper import FasterWhisperTranscriptionProvider
from app.services.dubbing.grouper import DubbingGrouper
from app.services.subtitles.generator import SubtitleCue, generate_srt
from app.workers.transcription import process_transcription
from scripts.verify_short_segmentation import stats


def waveform_evidence(audio: Path, words: list, segments: list, root: Path) -> list:
    with wave.open(str(audio), 'rb') as recording:
        rate = recording.getframerate()
        samples = np.frombuffer(recording.readframes(recording.getnframes()), dtype=np.int16).astype(float)/32768
    duration = len(samples)/rate
    windows = [(0,min(10,duration)),(duration/2-5,duration/2+5),(max(0,duration-10),duration)]
    panels = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="780" viewBox="0 0 1200 780"><rect width="1200" height="780" fill="white"/>']
    evidence = []
    for panel,(start,end) in enumerate(windows):
        y = 35+panel*255
        points=[]
        for index in range(1100):
            low=int((start+(end-start)*index/1100)*rate)
            high=max(low+1,int((start+(end-start)*(index+1)/1100)*rate))
            peak=float(np.max(np.abs(samples[low:high]))) if high>low and low<len(samples) else 0
            points.append(f'{60+index},{y+100-peak*85}')
        panels.append(f'<text x="60" y="{y}" font-size="16">{start:.3f}–{end:.3f} seconds: original waveform and ASR word intervals</text>')
        panels.append(f'<polyline fill="none" stroke="#2563eb" points="{" ".join(points)}"/>')
        selected=[w for w in words if w.start>=start and w.end<=end]
        for index,word in enumerate(selected):
            x=60+(word.start-start)/(end-start)*1100
            width=max(1,(word.end-word.start)/(end-start)*1100)
            panels.append(f'<rect x="{x:.2f}" y="{y+115}" width="{width:.2f}" height="12" fill="#cbd5e1"/><text x="{x:.2f}" y="{y+150+(index%2)*23}" font-size="11">{html.escape(word.word.strip())}</text>')
        for segment in segments:
            if start<=segment.start_time<=end:
                x=60+(segment.start_time-start)/(end-start)*1100
                panels.append(f'<path d="M{x},{y+20} V{y+130}" stroke="#dc2626"/>')
        word_checks=[]
        for word in selected:
            chunk=samples[max(0,int(word.start*rate)):min(len(samples),int(word.end*rate))]
            rms=float(np.sqrt(np.mean(chunk*chunk))) if len(chunk) else 0
            word_checks.append({'word_id':word.word_id,'text':word.word,'start':word.start,'end':word.end,'rms_dbfs':float(20*np.log10(max(rms,1e-12)))})
        evidence.append({'start':start,'end':end,'word_energy':word_checks,'spoken_phrase_verification':'human_listening_not_performed'})
    panels.append('</svg>')
    (root/'original_waveform_boundaries.svg').write_text(''.join(panels),encoding='utf-8')
    return evidence


def main() -> None:
    with SessionLocal() as db:
        db.get_bind().echo=False
        project=db.query(Project).filter_by(id=sys.argv[1]).one()
        if not project.title.startswith('[Segmentation acceptance]'):
            raise ValueError('Only isolated segmentation acceptance projects may be changed')
        root=Path('/app/data/projects')/project.id
        baseline=json.loads((root/'segmentation_before.json').read_text())
        source=Path(project.video.file_path)
        if hashlib.sha256(source.read_bytes()).hexdigest()!=baseline['source_sha256']:
            raise ValueError('Source video changed')
        if not project.raw_transcript_json:
            job=ProcessingJob(project_id=project.id,job_type='transcription',status=JobStatus.PENDING)
            db.add(job);db.commit()
            process_transcription(project.id,job.id,db)
            db.refresh(job);db.refresh(project)
            if job.status != JobStatus.COMPLETED:
                raise RuntimeError(job.error_message)
        raw=[TranscriptionSegment.from_dict(s) for s in json.loads(project.raw_transcript_json)]
        all_words=[w for s in raw for w in s.words or []]
        modes={}
        for mode in ('original','sentence','dubbing'):
            segmented=segment_transcript(copy.deepcopy(raw),mode=mode)
            modes[mode]={'metrics':stats(segmented),'coverage':validate_word_coverage(raw,segmented),'segments':[s.to_dict() for s in segmented]}
        current=segment_transcript(raw,mode=project.segmentation_mode)
        persisted=project.transcript_segments
        assert [(s.start_time,s.end_time,s.text) for s in persisted]==[(s.start_time,s.end_time,s.text) for s in current]
        assert all(s.source_word_ids for s in persisted)
        assert all(0<=s.start_time<=s.end_time<=baseline['audio_duration'] for s in current)
        assert all(a.end_time<=b.start_time for a,b in zip(current,current[1:]))
        units=DubbingGrouper().group_segments(persisted)
        assert [identifier for u in units for identifier in u.source_segment_ids]==[s.id for s in persisted]
        srt=generate_srt([SubtitleCue(s.segment_order,s.start_time,s.end_time,s.text) for s in persisted])
        (root/'verified_english.srt').write_text(srt,encoding='utf-8')
        audio=Path(project.video.extracted_audio_path)
        signal=decode_audio(str(audio),sampling_rate=16000)
        regions=get_speech_timestamps(
            signal, VadOptions(min_silence_duration_ms=200, speech_pad_ms=0), sampling_rate=16000,
        )
        uncovered=[]
        for region in regions:
            start,end=region['start']/16000,region['end']/16000
            if not any(w.end>start and w.start<end for w in all_words):
                uncovered.append({'start':start,'end':end})
        print('CHECKING_VAD_OFF_FULL_AUDIO',flush=True)
        no_vad=FasterWhisperTranscriptionProvider(vad_filter=False).transcribe(audio,language='en',word_timestamps=True)
        no_vad_words=[w.word.strip() for s in no_vad for w in s.words or []]
        checks=waveform_evidence(audio,all_words,current,root)
        original_words=[w['word'].strip() for s in baseline['raw'] for w in s['words'] or []]
        report={'project_id':project.id,'source':str(source),'source_sha256':baseline['source_sha256'],
                'audio_duration':baseline['audio_duration'],'modes':modes,
                'before_words_match_after':[w.word.strip() for w in all_words]==original_words,
                'diagnostic_vad_options':{'min_silence_duration_ms':200,'speech_pad_ms':0},
                'vad_regions':len(regions),'speech_regions_without_any_recognized_words':uncovered,
                'vad_off_words':len(no_vad_words),'vad_on_off_word_sequence_equal':no_vad_words==[w.word.strip() for w in all_words],
                'uncertain_word_ids':[w.word_id for w in all_words if w.is_uncertain],
                'tts_units':len(units),'tts_source_mapping_exact':True,'waveform_checks':checks,
                'human_listening_performed':False,'models_installed':False}
        destination=root/f'segmentation_after_{time.time_ns()}.json'
        destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('AFTER',destination,flush=True)
        print(json.dumps({mode:data['metrics'] for mode,data in modes.items()},indent=2),flush=True)
        print('VAD',len(regions),'UNCOVERED',uncovered,'VAD_OFF_WORDS',len(no_vad_words),'SAME',report['vad_on_off_word_sequence_equal'],flush=True)


if __name__=='__main__':
    main()
