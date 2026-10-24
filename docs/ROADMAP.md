# KhmerDub AI - Development Roadmap

## Project Status

- **Current Phase**: Phase 4.1 Complete — Translation Quality & Natural Khmer Formatting Verified
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

### [x] Phase 4: English-to-Khmer Translation (Meta NLLB-200)
- [x] Open-source translation model integration (`facebook/nllb-200-distilled-600M`).
- [x] Timestamp and segment-preserving translation (`eng_Latn` → `khm_Khmr`).
- [x] Lazy model loading and persistent Docker volume caching (`_cache_lock`).
- [x] Thread-safe batch inference on CPU with RSS memory monitoring via `psutil`.
- [x] Alembic migration for `is_manually_edited` and `is_outdated` tracking flags.
- [x] Automatic outdated marking when English transcript is updated.
- [x] Preservation of user manual corrections during full project retranslation.
- [x] API endpoints: `POST /translate`, `GET /translations`, `PATCH /translations/{id}`, `POST /translations/{id}/retranslate`.
- [x] Frontend comparative UI (English vs. Khmer side-by-side) with inline editing and per-segment retranslate.
- [x] 31 unit, integration, and workflow tests passing in Docker.

### [x] Phase 4.1: Translation Quality & Natural Khmer Text Formatting
- [x] Natural Khmer orthography formatter (`KhmerTextFormatter`) collapsing artificial inter-word spaces.
- [x] Protection of punctuation clinging, Latin/English brand names (`KhmerDub AI`), and numbers.
- [x] Technical terminology alignment (`KhmerGlossary`) correcting AI (`បញ្ញាសិប្បនិម្មិត`) and greeting hallucinations.
- [x] Lightweight context-aware window strategy across adjacent segments in `process_translation`.
- [x] Dynamic target language token ID resolution from tokenizer.
- [x] Model comparison between NLLB-200 and alternative open-source translation models.
- [x] Comprehensive 20-sentence benchmark evaluation dataset tested on real CPU inference.
- [x] 38 automated unit and integration tests passing in Docker.

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
