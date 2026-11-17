"""Controlled known-stem evaluation using existing real speech; no ASR/TTS rerun."""
import hashlib
import json
import sys
import wave
from pathlib import Path

import numpy as np

from app.database.session import SessionLocal
from app.models.project import GeneratedAudio, Video
from app.services.video.cleaning import AudioCleaningProcessor

ROOT = Path("/app/data/temp/audio-cleaning-evaluation-2026-10-31")


def save(path: Path, samples: np.ndarray, rate: int = 48000) -> None:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(rate)
        stream.writeframes((np.clip(samples,-.99,.99)*32767).astype("<i2").tobytes())


def read(path: Path) -> np.ndarray:
    # Only the small controlled fixtures are loaded; full-file processing streams.
    import subprocess
    output = subprocess.run(["ffmpeg","-v","error","-i",str(path),"-ar","48000","-ac","1","-f","f32le","-"],
                            check=True,capture_output=True)
    return np.frombuffer(output.stdout,dtype=np.float32).copy()


def prepare() -> None:
    ROOT.mkdir(parents=True,exist_ok=True)
    if (ROOT/"fixture.json").exists():
        return
    with SessionLocal() as db:
        db.get_bind().echo = False
        clip = next(a for a in db.query(GeneratedAudio).filter_by(provider="edge").all()
                    if Path(a.audio_path).is_file() and 2 < a.duration_seconds < 6)
        source = next(v for v in db.query(Video).all() if Path(v.file_path).is_file())
        processor = AudioCleaningProcessor()
        decoded = ROOT/"speech-take.wav"
        processor.extract_original(Path(clip.audio_path),decoded,processor.inspect(Path(clip.audio_path)),lambda:False,lambda _:None)
        take = read(decoded)
        take *= .55/max(float(max(abs(take))),1e-6)
        rate=48000
        reference = np.concatenate([np.zeros(rate),take,np.zeros(rate),.35*take,np.zeros(rate)])
        time = np.arange(len(reference))/rate
        rng = np.random.default_rng(2026)
        noise = rng.normal(0,.005,len(reference)) + .002*np.sin(2*np.pi*80*time)*(1+.25*np.sin(2*np.pi*.8*time))
        music = np.zeros(len(reference))
        for frequency, amplitude in [(130.81,.032),(164.81,.025),(196,.025),(261.63,.015),(392,.01)]:
            music += amplitude*np.sin(2*np.pi*frequency*time)*(0.65+.35*np.sin(2*np.pi*.4*time)**2)
        music += .012*np.sin(2*np.pi*65*time)*np.exp(-((time%.5)/.06)**2)
        save(ROOT/"speech-reference.wav",reference)
        save(ROOT/"noise-stem.wav",noise)
        save(ROOT/"music-stem.wav",music)
        save(ROOT/"speech-plus-noise.wav",reference+noise)
        save(ROOT/"speech-plus-music.wav",reference+music)
        (ROOT/"fixture.json").write_text(json.dumps({"speech_source":clip.audio_path,"video_source":source.file_path,
            "source_sha256":hashlib.sha256(Path(source.file_path).read_bytes()).hexdigest(),
            "fixture_seconds":len(reference)/rate,"quiet_phrase_gain":.35,
            "conditions":"Real existing synthesized Khmer speech with known added hiss/fan or synthetic instrumental stems; not a natural field recording.",
            "human_listening":"not performed"},indent=2))


def metrics(output: Path, mixture: Path) -> dict:
    reference=read(ROOT/"speech-reference.wav")
    rendered=read(output)
    mixed=read(mixture)
    assert len(rendered)==len(reference)
    silence=np.arange(len(reference))<int(.8*48000)
    speech=abs(reference)>.008
    quiet=(np.arange(len(reference))>len(reference)//2)&speech
    def si_sdr(x):
        projected=reference*np.dot(x,reference)/max(np.dot(reference,reference),1e-12)
        return float(10*np.log10(max(np.dot(projected,projected),1e-12)/max(np.dot(x-projected,x-projected),1e-12)))
    return {"duration_seconds":len(rendered)/48000,"frames_preserved":True,
        "si_sdr_before_db":si_sdr(mixed),"si_sdr_after_db":si_sdr(rendered),
        "background_only_reduction_db":float(10*np.log10(np.mean(mixed[silence]**2)/max(np.mean(rendered[silence]**2),1e-12))),
        "speech_correlation":float(np.corrcoef(reference[speech],rendered[speech])[0,1]),
        "quiet_phrase_gain":float(np.dot(reference[quiet],rendered[quiet])/np.dot(reference[quiet],reference[quiet])),
        "clipped_samples":int(sum(abs(rendered)>=.9999)),
        "lexical_and_perceptual_quality":"not human-verified"}


def main() -> None:
    prepare()
    processor=AudioCleaningProcessor()
    results={}
    if "--music" in sys.argv:
        output=ROOT/"music-balanced.wav"
        meta=processor.separate_music(ROOT/"speech-plus-music.wav",output,ROOT/"background.wav",ROOT,
            "balanced",Path("/root/.cache/audio_cleaning"),Path("/opt/audio-cleaning-env/bin/python"),
            lambda:False,lambda p:print("SEPARATION",p,flush=True))
        results={**metrics(output,ROOT/"speech-plus-music.wav"),"engine":meta}
        (ROOT/"music-evaluation.json").write_text(json.dumps(results,indent=2))
    else:
        for strength in ("light","balanced","strong"):
            output=ROOT/f"noise-{strength}.wav"
            processor.denoise(ROOT/"speech-plus-noise.wav",output,strength,lambda:False,lambda _:None)
            results[strength]=metrics(output,ROOT/"speech-plus-noise.wav")
        (ROOT/"noise-evaluation.json").write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2),flush=True)


if __name__ == "__main__":
    main()
