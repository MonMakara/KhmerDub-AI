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
- **`core/credentials.py`**: Fernet-encrypted symmetric credential storage (AES-128-CBC + HMAC-SHA256) at `/app/data/.secrets/credentials.enc` with automatic key generation, permission restriction (0o600), masked API keys, and environment variable overrides.
- **`core/ai_guard.py`**: Unified concurrency slot manager serializing memory-intensive AI inference (Whisper & NLLB).
- **`core/recovery.py`**: Interrupted job recovery hook self-healing orphan jobs on startup without deleting records.
- **`core/storage.py`**: Project file storage manager organizing project assets (`data/projects/{project_id}/`) with paths for uploads, extracted audio, voice segments, audio timelines, and exported videos with backward compatibility resolution.
- **`database/`**: SQLAlchemy SQLite session manager and table initialization with automated schema column upgrades.
- **`models/`**: Relational models for `Project`, `Video` (with export metadata & `is_export_outdated` flag), `TranscriptSegment`, `TranslationSegment`, `ProcessingJob`, and `GeneratedAudio`.
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
  - `POST /api/projects/{id}/translations/{segment_id}/retranslate`: Single segment retranslation from English transcript using project's active provider and style.
  - `PATCH /api/projects/{id}/translation-settings`: Update project translation provider (NLLB, Gemini) and style mode (natural, short, simple, formal, standard).
  - `POST /api/projects/{id}/translations/{segment_id}/ai-improve`: Context-, style-, and speech-duration-aware translation improvement via Gemini.
  - `POST /api/projects/{id}/translations/{segment_id}/alternatives`: Generate 3 structured translation alternatives (Natural, Simple, Short) via Gemini.
  - `POST /api/projects/{id}/translations/{segment_id}/apply`: Apply AI improvement or alternative to segment with automated speech invalidation.
  - `GET /api/translation/providers`: List translation providers with status and available styles.
  - `POST /api/translation/test-connection`: Verify provider API key and connectivity.
  - `POST /api/translation/credentials` & `DELETE /api/translation/credentials/{provider}`: Securely store and purge encrypted API credentials.
  - `POST /api/projects/{id}/tts`: Asynchronous text-to-speech synthesis generating Khmer MP3 audio files via Google gTTS.
  - `GET /api/projects/{id}/generated-audio`: Retrieve all synthesized audio records with playback URLs and outdated flags.
  - `POST /api/projects/{id}/tts/{segment_id}/regenerate`: Single segment audio regeneration.
  - `GET /api/projects/{id}/tts/{segment_id}/audio`: Stream synthesized MP3 audio for browser playback.
  - `POST /api/projects/{id}/export`: Dispatch asynchronous background audio synchronization and dubbed video export.
  - `GET /api/projects/{id}/export/status`: Retrieve export status, job progress, file metadata, and timing conflicts.
  - `GET /api/projects/{id}/export/video`: Stream dubbed MP4 video with HTTP 206 Partial Content byte-range support.
  - `GET /api/projects/{id}/export/download`: Download finalized dubbed MP4 video as attachment with project title filename.
  - `GET /api/projects/{id}/jobs`: Processing jobs and progress tracking.
  - `GET /api/projects/{id}/video`: Stream uploaded MP4 for browser video preview.
  - `GET /api/projects/{id}/audio`: Stream extracted 16kHz WAV audio for browser playback.
- **`services/transcription/`**:
  - `FasterWhisperTranscriptionProvider`: Concretely implements `TranscriptionProvider`. Features thread-safe lazy model loading, CTranslate2 INT8 quantization, Voice Activity Detection, and generator consumption returning timestamped `TranscriptionSegment` instances.
- **`services/translation/`**:
  - `NLLBTranslationProvider`: Concretely implements `TranslationProvider`. Uses Meta's `facebook/nllb-200-distilled-600M` (`eng_Latn` → `khm_Khmr`) with thread-safe lazy loading (`_cache_lock`), beam search decoding, RSS RAM monitoring via `psutil`, and persistent caching in Docker volume `model_cache` (`/root/.cache`).
  - `GeminiTranslationProvider`: Implements `TranslationProvider` using the official `google-genai` SDK. Supports batch and per-segment translation, exponential backoff retries, JSON structured outputs, 5 distinct translation styles, prompt injection defense, and automated terminology alignment with `KhmerGlossary`.
  - `prompts.py`: Prompt engineering templates for translation, AI refinement, and structured alternatives with technical glossary injection and user input sanitization.
  - `registry.py`: Provider factory, model catalog (`gemini-2.5-flash`, `gemini-1.5-flash`, `gemini-1.5-pro`), and dynamic connection tester.
- **`services/tts/`**:
  - `GoogleTTSProvider`: Concretely implements `TTSProvider`. Streams speech MP3 from Google gTTS (`km`) with exponential backoff retries, text validation, and duration measurement using `FFmpegVideoProcessor.get_audio_duration`.
  - `EdgeTTSProvider`: Concretely implements `TTSProvider` using `edge-tts` to stream natural Microsoft Neural Khmer speech (`km-KH-PisethNeural` Male, `km-KH-SreymomNeural` Female) with exponential backoff retry logic.
  - `registry`: Provider factory (`get_tts_provider`) and voice validator (`is_valid_voice_combination`) supporting multi-voice selection across Google and Microsoft Edge.
- **`services/video/`**:
  - `FFmpegVideoProcessor`: Concretely implements `VideoProcessor` using safe subprocess execution. Validates MP4 containers, extracts stream metadata, measures audio duration, and converts audio to 16,000 Hz mono 16-bit PCM WAV.
- **`services/dubbing/`**:
  - `AudioSynchronizationService`: Coordinates timeline construction, inserts silence gaps via `anullsrc`, standardizes pieces to 44.1kHz 16-bit stereo PCM WAV, applies conservative `atempo` adjustment (max 1.25x), and detects timing conflicts without silent truncation.
  - `VideoExportService`: Remuxes video with synchronized timeline audio using explicit FFmpeg stream mapping (`-map 0:v:0 -map 1:a:0`), AAC encoding at 192kbps, faststart container optimization, and atomic staging (`.tmp.mp4` -> final).
  - `DubbingPipeline`: Orchestrates the complete end-to-end synchronization and export workflow, returning an `ExportResult`.
- **`workers/`**:
  - `process_audio_extraction`: Non-blocking background worker updating audio extraction job status.
  - `process_transcription`: Background STT worker populating `TranscriptSegment` database records.
  - `process_translation`: Background translation worker processing English segments, respecting and preserving manually edited translations (`is_manually_edited`), and populating `TranslationSegment` records.
  - `process_tts`: Background TTS worker orchestrating segment-level speech synthesis, updating `GeneratedAudio` records and tracking invalidation (`is_outdated`).
  - `process_dubbing`: Background dubbing worker orchestrating audio synchronization, video export, conflict logging, and database metadata updates.

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
4. **Step 4: Khmer Speech Synthesis & Voice Selection**:
   - User selects preferred Khmer voice (Google Khmer Neutral, Microsoft Piseth Male, Microsoft Sreymom Female) and can audition samples via interactive voice preview.
   - Selected provider (Google gTTS or Microsoft Edge TTS) synthesizes audio segments for each Khmer sentence into `data/projects/{project_id}/audio/`.
5. **Step 5: Audio Synchronization & Video Remux**:
   - Synthesized Khmer speech audio segments are fetched and validated against original segment timestamps.
   - `AudioSynchronizationService` calculates offsets, inserts silence gaps via `anullsrc`, standardizes sample rates, applies conservative tempo scaling (max 1.25x), and generates a master timeline WAV (`khmer_timeline.wav`).
   - If audio exceeds the available timestamp slot even with tempo adjustment, the system preserves the full audio and surfaces a descriptive `TimingConflict` report rather than truncating speech.
   - `VideoExportService` cleanly muxes the video stream from the uploaded MP4 with the synchronized audio timeline using FFmpeg (`-map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 192k -movflags +faststart`).
   - Video is atomically saved to `data/projects/{project_id}/output/dubbed_khmer.mp4` and made accessible via in-browser streaming player and direct download.

---

## 4. Extensibility & Future Architecture

- **Voice Cloning & Local TTS**: The `TTSProvider` abstract class allows seamlessly dropping in alternative engines (Edge TTS, Piper, Coqui, or custom fine-tuned Khmer voice models) without altering frontend or database logic.
- **GPU Acceleration**: CUDA container support can be enabled via Docker Compose `runtime: nvidia` for faster inference with RTX 4060 GPU without any architectural redesign.
