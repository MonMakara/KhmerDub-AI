"""Bounded, same-text pacing experiment restricted to isolated acceptance projects."""
import hashlib
import json
import sys
from pathlib import Path

from app.database.session import SessionLocal
from app.models.project import Project, GeneratedAudio
from app.services.dubbing.timing_optimizer import TimingOptimizerService
from app.services.dubbing.speech_guard import SpeechGuardService
from app.services.tts.registry import get_tts_provider


def main() -> None:
    with SessionLocal() as db:
        db.get_bind().echo = False
        project = db.query(Project).filter_by(id=sys.argv[1]).one()
        if not project.title.startswith('[Repair acceptance]'):
            raise ValueError('Pacing experiments require an isolated acceptance project')
        optimizer = TimingOptimizerService()
        initial = optimizer.analyze_timeline(project.id, db)
        provider = get_tts_provider(project.tts_provider)
        guard = SpeechGuardService()
        root = Path('/app/data/projects') / project.id / 'pacing_trials'
        root.mkdir(parents=True, exist_ok=True)
        evidence = []
        for item in initial:
            if item.overflow_seconds <= 0.05:
                continue
            record = db.query(GeneratedAudio).filter_by(translation_segment_id=item.translation_segment_id).one()
            previous = (record.audio_path, record.duration_seconds)
            for attempt in range(2):
                seed = int(hashlib.sha256(f'{project.id}:{item.translation_segment_id}:{attempt}'.encode()).hexdigest()[:8], 16)
                destination = root / f'unit_{item.segment_order}_attempt_{attempt}.wav'
                if destination.exists():
                    raise FileExistsError('Never overwrite an earlier pacing trial')
                trial = {'unit':item.segment_order,'attempt':attempt,'seed':seed,'original_master':previous[0],'approved_text':item.khmer_text,'voice':project.tts_voice}
                try:
                    result = provider.synthesize(item.khmer_text, destination, voice=project.tts_voice, seed=seed)
                    inspection = guard.inspect_speech_audio(result.audio_path, item.khmer_text)
                    trial['inspection'] = inspection.to_dict()
                    if inspection.completeness_status != 'plausibly_complete':
                        trial['selected'] = False
                        continue
                    record.audio_path = str(result.audio_path)
                    record.duration_seconds = inspection.duration_seconds
                    db.flush()
                    analysis = optimizer.analyze_timeline(project.id, db)
                    target = next(a for a in analysis if a.translation_segment_id == item.translation_segment_id)
                    trial['remaining_overflow'] = target.overflow_seconds
                    # Select the first technically acceptable take that fits;
                    # never rank recordings by shortest duration.
                    if target.overflow_seconds <= 0.05:
                        trial['selected'] = True
                        db.commit()
                        print('ACCEPTED',item.segment_order,inspection.duration_seconds,flush=True)
                        break
                    record.audio_path, record.duration_seconds = previous
                    db.flush()
                    trial['selected'] = False
                except Exception as exc:
                    record.audio_path, record.duration_seconds = previous
                    db.flush()
                    trial['selected'] = False
                    trial['error'] = str(exc)
                finally:
                    evidence.append(trial)
                    (root/'trials.json').write_text(json.dumps(evidence,indent=2,ensure_ascii=False),encoding='utf-8')
            else:
                print('UNRESOLVED',item.segment_order,flush=True)
        db.commit()


if __name__ == '__main__':
    main()
