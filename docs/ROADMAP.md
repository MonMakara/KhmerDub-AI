# KhmerDub AI - Development Roadmap

## Project Status

- **Current Phase**: Phase 1 — Environment Initialization & Baseline Connectivity
- **Overall Status**: In Progress

---

## Phase Breakdown

### [x] Phase 1: Environment & Architecture Initialization
- [x] Workspace inspection and Git repository initialization.
- [x] Monorepo structure setup (`frontend/`, `backend/`, `data/`, `docs/`).
- [x] Docker & Docker Compose setup with persistent caching and live bind-mounts.
- [x] FastAPI backend setup with healthcheck and SQLite database integration.
- [x] React + Vite + Tailwind CSS frontend setup with status dashboard and project creation.
- [x] Service provider abstract interfaces defined for transcription, translation, TTS, and video processing.
- [x] Automated backend tests verifying health and database operations.

### [ ] Phase 2: Video Upload & Audio Extraction
- [ ] Safe MP4 video upload API endpoint with size validation.
- [ ] FFmpeg integration for extracting 16kHz mono audio tracks.
- [ ] Video preview component in frontend.
- [ ] Media processing unit tests.

### [ ] Phase 3: English Transcription (faster-whisper)
- [ ] faster-whisper integration inside `TranscriptionProvider`.
- [ ] Segment generation with start/end timestamps.
- [ ] Interactive transcript viewer and editor on frontend.
- [ ] Model size configuration (base, small, medium).

### [ ] Phase 4: English-to-Khmer Translation
- [ ] Open-source translation model integration (NLLB-200).
- [ ] Timestamp-preserving segment translation.
- [ ] Khmer transcript editor in UI with per-segment regeneration.
- [ ] Khmer Unicode font rendering verification.

### [ ] Phase 5: Google Khmer TTS
- [ ] Verification of Google gTTS Khmer (`km`) support with sample audio generation.
- [ ] Segment-level Khmer MP3 speech synthesis with retry mechanisms.
- [ ] Audio preview player in frontend.

### [ ] Phase 6: Audio Synchronization & Video Export
- [ ] Transcript-timed audio synchronization with conservative speed adjustment.
- [ ] Conflict detection for timing overflows without silent truncation.
- [ ] FFmpeg remuxing replacing original speech with synchronized Khmer audio.
- [ ] Final video preview and download.

### [ ] Phase 7: Polish, Robustness & Comprehensive Testing
- [ ] End-to-end integration testing.
- [ ] Polished error reporting and progress indicators.
- [ ] Complete technical documentation update.

---

## Future Scope (Post Version 1)
- Custom Khmer voices (Piseth, Sreymom).
- Voice cloning from original speakers.
- Background music & ambient sound preservation.
- Multiple speakers and voice emotion control.
- Subtitle generation and export (.srt / .vtt).
