# KhmerDub AI - Development Roadmap

## Project Status

- **Current Phase**: Phase 3 Complete — English Automatic Speech Recognition Verified
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

### [x] Phase 2: Video Upload & Audio Extraction
- [x] Safe MP4 video upload API endpoint (`POST /api/projects/{id}/upload`) with 500 MB streaming limit.
- [x] FFprobe container validation and metadata extraction (dimensions, duration, codecs).
- [x] `FFmpegVideoProcessor` implementation extracting 16kHz mono 16-bit PCM WAV.
- [x] Non-blocking background worker with `ProcessingJob` progress and error logging.
- [x] Frontend drag-and-drop upload, upload progress indicator, video player preview, and audio preview player.
- [x] Comprehensive test suite (15 tests passing) with synthetic MP4 test fixtures.

### [x] Phase 3: English Transcription (faster-whisper)
- [x] `FasterWhisperTranscriptionProvider` implementation using faster-whisper and CTranslate2.
- [x] Thread-safe lazy model caching to avoid reloading weights per request.
- [x] Segment generation with start/end timestamps and Voice Activity Detection (VAD).
- [x] Background worker (`process_transcription`) with duplicate prevention on retranscribe.
- [x] API endpoints: `POST /transcribe`, `GET /transcript`, `PATCH /transcript/{segment_id}`.
- [x] Frontend English Transcription workspace with segment list and inline editor.
- [x] 24 unit, integration, and real inference tests passing in Docker.

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
