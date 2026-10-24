# Changelog

All notable changes to the KhmerDub AI project will be documented in this file.

## [0.3.0] - Phase 3 Complete (2026-10-24)

### Added
- **faster-whisper Transcription Provider (`FasterWhisperTranscriptionProvider`)**:
  - Implemented concrete speech-to-text provider using `faster-whisper` and CTranslate2.
  - Thread-safe lazy loading with in-memory model caching to avoid redundant model loads.
  - Configurable model size (`base`, `tiny`, `small`), device (`cpu`), compute type (`int8`), and Voice Activity Detection (`vad_filter=True`).
  - Safe error handling for incompatible compute types on CPU (`float16` rejected with clear guidance) and model loading failures.
  - Fully consumes generator to extract timestamped segments (`start_time`, `end_time`, `text`).
- **Transcription API Endpoints**:
  - `POST /api/projects/{project_id}/transcribe`: Initiates asynchronous background transcription job, preventing duplicate concurrent runs (`HTTP 409 Conflict`).
  - `GET /api/projects/{project_id}/transcript`: Returns ordered transcript segments with timestamps and project status.
  - `PATCH /api/projects/{project_id}/transcript/{segment_id}`: Allows inline editing of transcript segment text with database persistence.
- **Background Worker (`process_transcription`)**:
  - Safely deletes previous segments on retranscription to prevent duplicates.
  - Transitions `ProcessingJob` through `pending` → `running` (20%, 80%) → `completed` (100%) or `failed`.
- **Frontend Transcript Editor (`ProjectWorkspace.tsx`)**:
  - "English Transcription" section with model badge and "Start Transcription" / "Retranscribe" controls.
  - Live background polling for transcription status.
  - Segment card list displaying timestamps (`[00:00 – 00:11]`), segment index, duration, and text.
  - Inline edit mode with "Edit", "Save", and "Cancel" buttons communicating with PATCH API.
  - Persistent state on page refresh.
- **Testing**:
  - 24 automated backend unit and integration tests passing in 1.56s in Docker.
  - Real end-to-end inference verification using short speech audio.

## [0.2.0] - Phase 2 Complete (2026-10-24)

### Added
- **Backend Video Upload (`POST /api/projects/{project_id}/upload`)**:
  - Streaming chunk-by-chunk file writing with strict 500 MB limit check (`HTTP 413`).
  - Deep media container inspection via FFprobe, rejecting non-MP4 and corrupted files (`HTTP 400`).
  - Filename sanitization against path traversal and shell injection.
  - Video metadata extraction (resolution, duration, video codec, audio codec).
- **FFmpeg Audio Extraction**:
  - `FFmpegVideoProcessor` implementing `VideoProcessor`.
  - Converts audio track to 16,000 Hz mono 16-bit PCM WAV.
  - Non-blocking background worker (`process_audio_extraction`) with `ProcessingJob` tracking.
  - Error detection for silent videos without audio tracks (`NoAudioTrackError`).
  - Endpoints to trigger/retry extraction (`POST /api/projects/{id}/extract-audio`) and poll jobs (`GET /api/projects/{id}/jobs`).
  - Media streaming endpoints for video preview (`GET/HEAD /api/projects/{id}/video`) and extracted WAV audio (`GET/HEAD /api/projects/{id}/audio`).
- **Frontend Video Upload & Workspace**:
  - Modern drag-and-drop file upload zone with browse fallback and client-side format/size validation.
  - Live upload percentage progress bar and status indicator.
  - Interactive HTML5 video player for uploaded MP4 preview.
  - FFprobe metadata display (duration, resolution, codecs).
  - Background extraction status tracking with real-time polling.
  - Extracted audio preview player (`<audio>`) and retry button for failed extractions.
- **Testing**:
  - 15 automated unit and integration tests passing in 0.64s in Docker backend.
  - End-to-end integration test with live generated test media.

## [0.1.0] - Phase 1 Complete (2026-10-24)

### Added
- Modular monolith repository layout: `backend/`, `frontend/`, `data/`, and `docs/`.
- Docker Compose configuration (`compose.yaml`) with persistent cache volume (`khmerdub_model_cache`) and live bind-mounts.
- FastAPI backend with:
  - Pydantic Settings configuration (`app/core/config.py`).
  - SQLite database setup via SQLAlchemy 2.0 (`app/database/session.py`).
  - Core database models: `Project`, `Video`, `TranscriptSegment`, `TranslationSegment`, `ProcessingJob`, `GeneratedAudio`.
  - Service provider abstract base classes for Transcription, Translation, TTS, and Video Processing.
  - Health check endpoint `/api/health` and basic project CRUD endpoints `/api/projects`.
  - Pytest test suite with in-memory database fixtures.
- React 18 + Vite + TypeScript + Tailwind CSS frontend with:
  - Sidebar navigation (Dashboard, Projects, Settings).
  - Live backend connectivity and FFmpeg status header.
  - Overview cards, dubbing workflow visualizer, and project creation form.
  - Kantumruy Pro Khmer font support ready for upcoming phases.
- Comprehensive documentation: `README.md`, `AGENTS.md`, `ARCHITECTURE.md`, `DEVELOPMENT.md`, `ROADMAP.md`.
