# KhmerDub AI - System Architecture

## 1. High-Level Overview

KhmerDub AI is structured as a **modular monolith** running inside Docker Compose. It separates concerns between an interactive modern frontend (React/Vite/Tailwind) and a high-performance Python backend (FastAPI/SQLAlchemy/FFmpeg/AI models).

```
┌────────────────────────────────────────────────────────┐
│              Browser Client (Port 5173)                │
│         React 18 + TypeScript + Tailwind CSS           │
└───────────────────────────┬────────────────────────────┘
                            │ HTTP / REST API
                            ▼
┌────────────────────────────────────────────────────────┐
│             FastAPI Backend (Port 8000)                │
│  - API Endpoints (/api/health, /api/projects, etc.)   │
│  - SQLAlchemy ORM + SQLite (/app/data/khmerdub.db)     │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │              Service Layer Providers             │  │
│  │  - VideoProcessor (FFmpeg / ffprobe)             │  │
│  │  - TranscriptionProvider (faster-whisper)        │  │
│  │  - TranslationProvider (NLLB-200 English->Khmer) │  │
│  │  - TTSProvider (Google gTTS / Khmer voice)       │  │
│  │  - DubbingPipeline (Audio sync & video remux)    │  │
│  └──────────────────────────────────────────────────┘  │
└───────────────────────────┬────────────────────────────┘
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
┌───────────────────────┐       ┌───────────────────────┐
│     Data Storage      │       │      Model Cache      │
│  (Persistent Volume)  │       │  (Persistent Volume)  │
│  - uploads/           │       │  - Whisper models     │
│  - outputs/           │       │  - NLLB checkpoints   │
│  - temp/              │       │                       │
└───────────────────────┘       └───────────────────────┘
```

---

## 2. Core Components

### 2.1 Backend (`backend/app`)
- **`core/config.py`**: Centralized configuration management using Pydantic Settings.
- **`database/`**: SQLAlchemy SQLite session manager and table initialization with automated schema column upgrades.
- **`models/`**: Relational models for `Project`, `Video`, `TranscriptSegment`, `TranslationSegment`, `ProcessingJob`, and `GeneratedAudio`.
- **`schemas/`**: Pydantic input/output validation schemas (`ProjectResponse`, `VideoResponse`, `ProcessingJobResponse`).
- **`api/endpoints/`**:
  - `GET /api/health`: Diagnostics and environment readiness.
  - `GET /api/projects` & `POST /api/projects`: Project list and creation.
  - `POST /api/projects/{id}/upload`: Streaming MP4 upload with FFprobe container validation.
  - `POST /api/projects/{id}/extract-audio`: Manual trigger or retry for background audio extraction.
  - `POST /api/projects/{id}/transcribe`: Asynchronous speech-to-text inference with faster-whisper.
  - `GET /api/projects/{id}/transcript`: Retrieve ordered timestamped transcript segments.
  - `PATCH /api/projects/{id}/transcript/{segment_id}`: Inline editing of transcript segment text (automatically marks corresponding translation as outdated).
  - `POST /api/projects/{id}/translate`: Asynchronous English-to-Khmer translation inference with NLLB-200.
  - `GET /api/projects/{id}/translations`: Retrieve ordered translated segments with original English text and timestamps.
  - `PATCH /api/projects/{id}/translations/{segment_id}`: Inline manual editing of Khmer translation text (`is_manually_edited=True`, `is_outdated=False`).
  - `POST /api/projects/{id}/translations/{segment_id}/retranslate`: Single segment retranslation from English transcript.
  - `GET /api/projects/{id}/jobs`: Processing jobs and progress tracking.
  - `GET /api/projects/{id}/video`: Stream uploaded MP4 for browser video preview.
  - `GET /api/projects/{id}/audio`: Stream extracted 16kHz WAV audio for browser playback.
- **`services/transcription/`**:
  - `FasterWhisperTranscriptionProvider`: Concretely implements `TranscriptionProvider`. Features thread-safe lazy model loading, CTranslate2 INT8 quantization, Voice Activity Detection, and generator consumption returning timestamped `TranscriptionSegment` instances.
- **`services/translation/`**:
  - `NLLBTranslationProvider`: Concretely implements `TranslationProvider`. Uses Meta's `facebook/nllb-200-distilled-600M` (`eng_Latn` → `khm_Khmr`) with thread-safe lazy loading (`_cache_lock`), beam search decoding, RSS RAM monitoring via `psutil`, and persistent caching in Docker volume `model_cache` (`/root/.cache`).
- **`services/video/`**:
  - `FFmpegVideoProcessor`: Concretely implements `VideoProcessor` using safe subprocess execution. Validates MP4 containers, extracts stream metadata, and converts audio to 16,000 Hz mono 16-bit PCM WAV.
- **`workers/`**:
  - `process_audio_extraction`: Non-blocking background worker updating audio extraction job status.
  - `process_transcription`: Background STT worker populating `TranscriptSegment` database records.
  - `process_translation`: Background translation worker processing English segments, respecting and preserving manually edited translations (`is_manually_edited`), and populating `TranslationSegment` records.

### 2.2 Frontend (`frontend/src`)
- **Layout**: Clean left sidebar with Dashboard, Projects, and Settings tabs; top header with live backend connectivity status.
- **Pages**:
  - `Dashboard`: System health metrics and quick-start actions.
  - `Projects`: Project table and management.
  - `Settings`: Environment configurations, storage paths, and hardware details.
- **Services**: Typed API client interacting with backend REST endpoints.

---

## 3. Data Flow (5-Step Dubbing Pipeline)

1. **Step 1: Video Upload**:
   - User uploads an MP4 video. Backend validates format and file size (< 500 MB), saves it to `data/uploads/`, and creates `Project` and `Video` database records.
2. **Step 2: Audio Extraction & Transcription**:
   - FFmpeg extracts a 16kHz mono WAV audio file into `data/temp/`.
   - `faster-whisper` transcribes audio into timestamped segments (`TranscriptSegment`).
3. **Step 3: English-to-Khmer Translation**:
   - English transcript segments are translated to Khmer using an open-source model (e.g. NLLB-200), preserving segment timings in `TranslationSegment`. User can review and edit in UI.
4. **Step 4: Khmer Speech Synthesis**:
   - Google gTTS generates audio segments for each Khmer sentence into `data/temp/`.
5. **Step 5: Audio Synchronization & Video Remux**:
   - Audio segments are aligned against original timestamps with modest time-stretching if necessary.
   - FFmpeg replaces the original audio track with the synchronized Khmer dubbed track, producing the final output in `data/outputs/`.

---

## 4. Extensibility & Future Architecture

- **Voice Cloning & Local TTS**: The `TTSProvider` abstract class allows seamlessly dropping in alternative engines (Edge TTS, Piper, Coqui, or custom fine-tuned Khmer voice models) without altering frontend or database logic.
- **GPU Acceleration**: CUDA container support can be enabled via Docker Compose `runtime: nvidia` for faster inference with RTX 4060 GPU without any architectural redesign.
