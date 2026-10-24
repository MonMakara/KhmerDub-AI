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
- **`database/`**: SQLAlchemy SQLite session manager and table initialization.
- **`models/`**: Relational models for `Project`, `Video`, `TranscriptSegment`, `TranslationSegment`, `ProcessingJob`, and `GeneratedAudio`.
- **`schemas/`**: Pydantic input/output validation schemas.
- **`api/endpoints/`**: Thin REST API controllers delegating work to services.
- **`services/`**: Pluggable provider interfaces:
  - `TranscriptionProvider`: Defines `transcribe(audio_path, language)`
  - `TranslationProvider`: Defines `translate(texts, source_lang, target_lang)`
  - `TTSProvider`: Defines `synthesize(text, output_path, language)`
  - `VideoProcessor`: Defines `get_metadata()`, `extract_audio()`, and `merge_audio_video()`
  - `DubbingPipeline`: Coordinates the end-to-end synchronization workflow.

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
