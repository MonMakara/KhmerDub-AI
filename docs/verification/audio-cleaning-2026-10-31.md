# Audio Noise & Music Remover — delivery and verification

Implemented and enabled locally on 2026-10-31. No project deletion, database reset,
voice/consent changes, model-volume removal, automatic commit, or Phase 14 work.

## 1. Files and responsibilities

- `backend/app/services/video/cleaning.py`: `AudioCleaningProcessor`; bounded FFmpeg
  passes, inspection, extraction, denoising, isolated separation, validation and video export.
- `backend/app/services/audio_cleaning.py`: capabilities, existing ToolkitTask lifecycle,
  processing slot, progress, cancellation, verification and atomic output publication.
- `backend/app/services/separation_engine.py`: offline Demucs subprocess, bounded windows,
  overlap crossfades, exact frame coverage and global clipping protection.
- `backend/app/api/endpoints/audio_cleaning.py`, `backend/app/api/router.py`: API wiring.
- `backend/app/api/endpoints/toolkit.py`: card capabilities, active-task deletion guard,
  completed-only cleanup bundles. `backend/app/core/recovery.py`: interrupted cleanup recovery.
- `frontend/src/components/toolkit/AudioCleaning.tsx`: focused new workspace.
- `frontend/src/pages/MediaToolkit.tsx`, `frontend/src/services/api.ts`,
  `frontend/src/types/index.ts`: navigation, history, upload/progress APIs and status types.
- `backend/Dockerfile.audio-evaluation`, `compose.audio-cleaning.yaml`: optional isolated environment.
- `backend/scripts/download_cleaning_model.py`, `evaluate_audio_cleaning.py`,
  `accept_audio_cleaning.py`: explicit model installation and reproducible verification.
- `backend/tests/test_audio_cleaning.py`: 14 new regression/integration cases.

## 2. Media Toolkit UI

New card/workspace uses existing styling. Upload or drag/drop audio/video, or copy an
existing project's source. Mode and strength controls, upload progress, estimated overall
stage progress, measured pass progress, cancellation, friendly errors, previews and exports.
Existing history opens completed and cancelled cleanup tasks; queued/cancelling/cancelled
labels and filters are included. Browser verification screenshot: `audio-cleaning-browser.jpg`.

## 3. API

Under `/api/toolkit/audio-cleaning`: `GET /capabilities`, multipart `POST /start`,
`POST /{task_id}/cancel`, `GET|HEAD /{task_id}/files/{kind}`. Kinds are original, wav,
mp3, video and background; `download=true` requests attachment delivery. Existing task
read/history/bundle APIs are reused. No schema migration required.

Uploads have configured size and free-space limits, fixed owned paths, extension and
actual media validation. Task queue is bounded to three active cleanup requests and
one cleanup worker. Music shares the existing heavy-AI inference slot. Cancellation
stops subprocesses, keeps source input and removes task-owned temporary files. Failed,
cancelled or incomplete tasks cannot download cleaned results. Interrupted jobs become
failed on startup with source preserved; they are not silently resumed.

## 4. Noise method

Installed FFmpeg `afftdn`, fixed conservative noise floor, adaptive noise learning disabled.
No speech gate, high-pass speech removal, tempo adjustment or silence trimming. Its measured
25 ms algorithmic delay is compensated with tail flushing and timestamp reset; a waveform
alignment regression test protects synchronization and end-of-file speech.

## 5. Music method

Demucs htdemucs vocals separation, with some residual retained to reduce over-processing.
One model is reused through each task. 20-second windows, 18-second hops and two-second
context/crossfades bound memory; full input frame coverage is asserted. The model operates
at 44.1 kHz, with outputs restored to the 48 kHz comparison timeline. No runtime downloads.

## 6. Models and dependencies

User approved this installation/evaluation. Private `/opt/audio-cleaning-env` contains
Demucs 4.0.1, CPU Torch 2.0.1+cpu, torchaudio 2.0.2+cpu, NumPy <2 and soundfile >=0.12,<0.14.
Existing application Torch/Whisper/translation/TTS packages remain separate and unchanged.
No Ubuntu host Python dependencies installed.

Checkpoint `955717e8-8726e21a.th`: 84,141,911 bytes; SHA256
`8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`.
Stored in `model_cache` at `/root/.cache/audio_cleaning/`. The explicit download script
checks size and published hash prefix before publishing the checkpoint.

Upstream: [Demucs documentation](https://github.com/facebookresearch/demucs),
[MIT license](https://github.com/facebookresearch/demucs/blob/main/LICENSE),
[checkpoint listing](https://github.com/facebookresearch/demucs/blob/main/demucs/remote/files.txt).
Upstream targets music stems and is archived; narration quality requires source-specific review.

Runtime uses the evaluated `khmerdub-ai-backend-cleaning` Docker image. Restart with:

```sh
docker compose -f compose.yaml -f compose.audio-cleaning.yaml up -d --no-build backend
```

For a fresh installation, first build the ordinary backend, then build the overlay:

```sh
docker compose build backend
docker compose -f compose.yaml -f compose.audio-cleaning.yaml build backend
```

Install approved weights separately using `python -m scripts.download_cleaning_model`
inside the backend container. A clean base-only deployment keeps noise removal available
and explicitly disables music removal until the optional environment and checkpoint exist.
The final production overlay is the successfully tested evaluation image. An unnecessary
ordinary-backend rebuild was stopped when it began resolving a newer application Torch;
that image was not deployed and the existing AI installation was preserved.

## 7. CPU/GPU

This Docker backend has no usable CUDA; installed private Torch is CPU-only. All results
here are CPU results using two Torch/FFmpeg threads. The subprocess has device-selection
and CUDA OOM-to-CPU fallback logic for a future CUDA-enabled private environment; GPU
execution and OOM recovery remain unverified. GPU acceleration is unavailable in this
deployment and no NVIDIA host toolkit was installed.

## 8–9. Formats and strengths

Actual generated fixtures for WAV, MP3, M4A, FLAC, OGG, MP4, MOV, MKV and WebM passed
inspection, extraction, cleanup and complete audio validation. First audio track is used,
up to two channels; extra tracks are explicitly omitted from cleaned video.

| Preset | Noise reduction setting | Music residual retained |
|---|---:|---:|
| Light | 6 dB | 40% |
| Balanced | 10 dB | 20% |
| Strong | 16 dB | 5% |

These are processing controls, not guaranteed measured reductions. Balanced is the default.

## 10–12. Preview and exports

Original/cleaned WAV players have linked seeking and mutually exclusive playback; music
results also expose the removed-background player to inspect speech leakage. No autoplay.
Browser tests verified playback, linked positions, cancellation, successful upload,
download and history reopening. API range requests returned 206 for seeking.

Exports: PCM24 WAV, 192 kbps MP3, and cleaned MP4 for compatible video inputs. MP4 uses
original video stream copy first, H.264 fallback only if needed. Different stream start
offsets or audio extending past video produce a clear video warning and preserve clean
audio rather than truncate speech. Both full-video test outputs used stream copy.

## 13–14. Real-media, quality and synchronization evidence

Complete existing Bamboo Tree video: original audio 193.793741 seconds, decoded and cleaned
WAV 193.793750 seconds in both modes, exactly zero difference relative to decoded input.
Every output audio/video was fully decoded for validation, not just spot-checked.
Both cleaned MP4 video payload hashes equal the original:
`d12c9edb4f2da227c80e405ea5dad9fdac5be01dfc05bf280aaca68fca88a37d`.
Original source file SHA256 remained unchanged.

Noise task: `5177b151-fbb0-48e8-9cd6-fbab1da79c80`.
Music task: `c032e828-8987-419c-954b-9e1fff92ed33`.
Both remain in toolkit history with verified WAV/MP3/MP4 exports. Actual running API
HEAD requests confirmed export sizes/dispositions; range preview reads passed.

Known-stem quality fixture: 10.2 seconds of existing synthesized Khmer speech, including
a second phrase reduced to 35% amplitude, plus known seeded hiss/fan or synthetic
instrumental music. This is controlled real speech, not a natural field recording.

| Mode / preset | Background-only reduction | Speech correlation | Quiet phrase gain |
|---|---:|---:|---:|
| Noise Light | 4.02 dB | .9991 | .9983 |
| Noise Balanced | 5.54 dB | .9992 | .9981 |
| Noise Strong | 6.74 dB | .9993 | .9980 |
| Music Light | 7.98 dB | .9822 | .9455 |
| Music Balanced | 14.02 dB | .9882 | .9319 |
| Music Strong | 26.23 dB | .9903 | .9217 |

All fixtures preserved exact frame counts with no clipped output samples. Balanced music
SI-SDR improved from 4.51 to 14.24 dB; balanced noise from 19.68 to 24.35 dB. Metrics
support reduction on these fixtures; they do not establish word completeness, speaker
identity or perceptual quality across arbitrary recordings.

## 15–16. Tests

Final isolated Docker backend suite: **435 passed, 1 skipped**, two existing deprecation
warnings, 65.85 seconds. Tests include actual FFmpeg passes, strength presets, exact
alignment, exports/history/downloads, invalid/corrupt/muted input, multitrack policy,
limits, full-disk upload rejection, queue/cancel/delete behavior, processing failure,
temporary cleanup, path safety and restart recovery. Full suite log is saved below.

Final frontend `npm run build` inside Docker passed TypeScript compilation and Vite
production build. Existing large-chunk advisory remains. Browser tests additionally
covered the real enabled music model; uploaded task
`9eacaa1f-26d7-4d3f-b5c8-6a2df12d3504` completed and downloaded `cleaned.wav`.

## 17–18. Limitations and unavailable behavior

No human listening or word-by-word assessment was performed; no claim of perfect removal,
zero voice artifacts or guaranteed complete words is made. Demucs can retain singing,
remove quiet narration, or distort difficult overlapping speech/music. Noise cleanup
cannot reliably remove overlapping music, sudden loud transients, wind or severe hum.
Strong processing trades naturalness for reduction. Compare every important output.

GPU acceleration, natural noisy field-recording benchmarks, very long six-hour inputs,
actual disk exhaustion during encoding and GPU OOM recovery were not tested. Browser
tests used the desktop viewport; dedicated mobile layout testing was not performed.
No model is currently blocking the two implemented modes. Video outputs with incompatible
timing deliberately require review. Work stays in the existing single-backend task model.

Raw metrics, manifests, format checks, download/hash checks and test/build logs are in
[`audio-cleaning-evidence/`](audio-cleaning-evidence/).
