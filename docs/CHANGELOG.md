# Changelog

All notable changes to the KhmerDub AI project will be documented in this file.

## [0.8.0] - Phase 8 Complete (2026-10-24)

### Added
- **Multiple Khmer Speech Providers & Microsoft Edge TTS Integration**:
  - Installed `edge-tts>=6.1.10` inside the Docker development environment without global system dependencies.
  - Implemented `EdgeTTSProvider` (`backend/app/services/tts/edge.py`) supporting official Microsoft Neural voices:
    - `km-KH-PisethNeural`: Male, friendly & positive tone.
    - `km-KH-SreymomNeural`: Female, expressive & natural tone.
  - Implemented safe asynchronous coroutine execution handling both running and non-running event loop environments.
  - Exponential backoff retry logic for Edge TTS network resilience.
- **Provider & Voice Registry (`backend/app/services/tts/registry.py`)**:
  - `list_supported_voices()`: Returns all available Khmer voices with metadata (label, gender, sample rate, description).
  - `is_valid_voice_combination(provider, voice)`: Validates allowable provider and voice pairings.
  - `get_tts_provider(provider_name)`: Factory returning configured `GoogleTTSProvider` or `EdgeTTSProvider`.
- **Database Schema Migration (`c1f72a4d9e01`)**:
  - Added `tts_provider` (default `'gtts'`) and `tts_voice` (default `'default'`) columns to `projects` table.
  - Safe SQLite column introspection preventing duplicate column migration errors.
- **API Endpoints**:
  - `GET /api/tts/voices`: Returns supported voices list, default provider, and default voice.
  - `POST /api/tts/preview`: Generates temporary voice preview audio stream (`audio/mpeg`) with text hashing and a 200-character maximum text limit.
  - `PATCH /api/projects/{project_id}/voice`: Updates project voice configuration and automatically marks existing `GeneratedAudio` as `is_outdated = True` and `Video` as `is_export_outdated = True`.
- **Worker & Regeneration Updates**:
  - Updated `backend/app/workers/tts.py` to synthesize all segments according to the project's selected `tts_provider` and `tts_voice`.
  - Updated `POST /api/projects/{project_id}/tts/{segment_id}/regenerate` to respect the project's selected voice.
- **Frontend Step 4 Voice Workspace (`ProjectWorkspace.tsx`)**:
  - Voice selection card deck featuring Google Khmer, Microsoft Piseth, and Microsoft Sreymom with colored gender and provider badges.
  - In-browser interactive "Preview Voice" player with stop/play toggle and audio stream playback.
  - Automatic voice selection update via `PATCH /api/projects/{id}/voice`.
  - Visual alert when voice selection changes, advising users to regenerate all speech segments.
  - Segment cards display voice metadata labels (`Microsoft Piseth (Male)`, `Microsoft Sreymom (Female)`, or `Google Khmer (Default)`).
- **Testing**:
  - 11 new automated test cases in `backend/tests/test_voice_selection.py` (92 tests total passing, 100% pass rate):
    - Voice registry metadata and validation.
    - Input validation and exception handling for Edge TTS.
    - Edge TTS retry logic on transient network failure.
    - API voice listing and validation tests.
    - API voice preview streaming test.
    - Project voice selection update and audio/export invalidation.
    - Background worker synthesis with Edge TTS voice.
    - Real Edge TTS synthesis for both Piseth and Sreymom.
    - Full dubbing pipeline compatibility with Edge TTS audio.
  - Frontend typecheck and production build verified with 0 errors.

## [0.7.0] - Phase 7 Complete (2026-10-24)

### Added
- **AI Model Concurrency & Memory Guard (`app/core/ai_guard.py`)**:
  - Implemented a unified global inference slot manager (`acquire_ai_inference_slot`).
  - Serializes heavy CPU/RAM inference tasks between `faster-whisper` and Meta's `NLLB-200` to prevent memory exhaustion and 100% CPU core contention on 16GB host machines.
  - Active model tracking via `get_active_ai_model()`.
- **Interrupted Job Startup Recovery (`app/core/recovery.py`)**:
  - Automated startup hook executing during FastAPI `lifespan`.
  - Safely detects orphan background jobs interrupted by container restarts or shutdowns.
  - Transitions orphan jobs to `FAILED` with an informative recovery message (*"Job was interrupted by a server restart or shutdown. No completed files or records were removed; please retry."*).
  - Resets project status back to the last completed pipeline milestone.
  - Never deletes any generated audio, video, or database records.
- **Configurable Timing Safety Margins**:
  - Made `safety_margin_seconds: float = 0.05` configurable in `AudioSynchronizationService`.
  - Added distinct `available_window` (raw interval) and `effective_window` (after safety margin) fields in `TimingConflict` and `TimingConflictResponse`.
  - Resolved timing discrepancies between mathematical ratios and padded windows.
- **Active Job Deduplication**:
  - Added running job check to `POST /api/projects/{project_id}/extract-audio`.
- **End-to-End Pipeline Testing Suite (`tests/test_e2e_pipeline.py`)**:
  - Verified 5 distinct real video cases:
    - Case A: Short video (12s) with single speech segment.
    - Case B: Medium video (35s) with multiple spaced segments.
    - Case C: Multiple segments with distinct silence pauses (20s).
    - Case D: Speech segment near video end boundary (10s).
    - Case E: Speech segment with longer Khmer translation, verifying strict block and subsequent successful re-export after text correction.
- **Testing**:
  - 10 new unit, integration, and E2E tests added (81 tests total, 100% pass rate in Docker).
  - Frontend TypeScript strict check and Vite production build passed with 0 errors.

## [0.6.1] - Phase 6.1 Complete (2026-10-24)

### Added
- **Strict Duration Validation & Timing Conflict Guard**:
  - Implemented `TimingConflictError` in `backend/app/services/dubbing/synchronizer.py` raised whenever speech cannot safely fit within the video duration at maximum tempo adjustment (1.25x).
  - Prevents corrupted, overlong, or silently truncated video exports.
  - Added strict duration verification in `VideoExportService.verify_exported_video` asserting that video stream, audio stream, and container duration match the expected target duration within a small codec tolerance (±0.15s).
- **Enhanced Timing Conflict Schema & Reporting**:
  - Extended `TimingConflict` and `TimingConflictResponse` with:
    - `required_tempo`: Calculated exact speedup factor needed to fit the segment.
    - `max_tempo_factor`: Maximum allowable speedup limit (1.25x).
    - `suggested_action`: Actionable user recommendation specifying the estimated words/syllables to trim in translation (e.g. "Shorten the Khmer translation for Segment #1 by approximately 3 word(s) (~0.9s excess), regenerate audio, and retry export.").
- **Worker & API Enhancements**:
  - `process_dubbing` worker intercepts `TimingConflictError`, transitions job to `FAILED` with detailed conflict summaries, and leaves project in `VOICE_GENERATED` state so users can easily edit translations.
  - `GET /api/projects/{project_id}/export/status` computes detailed conflict diagnostics before export is triggered.
- **Frontend Step 5 UI Enhancements (`ProjectWorkspace.tsx`)**:
  - Enhanced Timing Conflicts Panel with "Export Guard Active" badge.
  - Displays per-segment conflict breakdown with original timestamps, original duration, Khmer audio duration, required speedup, and highlighted `suggested_action`.
- **Testing**:
  - 11 new automated test cases in `backend/tests/test_dubbing.py`:
    - `test_audio_longer_than_available_time`
    - `test_audio_shorter_than_available_time`
    - `test_exact_duration_audio`
    - `test_last_segment_exceeding_video_duration`
    - `test_multiple_consecutive_segments`
    - `test_overlapping_segments`
    - `test_silence_padding`
    - `test_safe_tempo_adjustment`
    - `test_unresolved_timing_conflicts_details`
    - `test_correct_output_stream_durations`
    - `test_prevention_of_silent_truncation`
  - Total backend tests increased to 71 passing with 0 failures.
  - Verified real video test cases with FFprobe:
    - Case A (speech shorter than interval): exported successfully with matching 4.000s streams.
    - Case B (speech fits after safe tempo $\le 1.25x$): exported successfully with 4.000s video and 3.998s audio (within 2ms codec tolerance).
    - Case C (speech cannot fit even at 1.25x): export blocked cleanly with `TimingConflictError`, 0 files corrupted.

## [0.6.0] - Phase 6 Complete (2026-10-24)

### Added
- **Project-Specific Storage (`backend/app/core/storage.py`)**:
  - Organized persistent storage under `data/projects/{project_id}/` with dedicated folders:
    - `voice/`: Synthesized Khmer segment audio (`audio_{segment_id}.wav` / `.mp3`).
    - `output/`: Aligned timeline audio (`khmer_timeline.wav`) and exported video (`dubbed_khmer.mp4`).
    - `uploads/`: Original uploaded video.
  - Transparent backward compatibility (`resolve_audio_file`) resolving legacy `data/temp/` audio files.
- **Audio Synchronization Engine (`AudioSynchronizationService`)**:
  - Built robust timeline constructor sorting speech segments by start timestamp.
  - Generates silence segments (`anullsrc`) matching intervals between segments and between video start/end.
  - Standardizes audio formats (44.1kHz, 16-bit, stereo PCM WAV) to enable lossless FFmpeg concat demuxer concatenation.
  - Implements conservative tempo adjustment (up to 1.25x via `atempo` filter) to gracefully fit slightly longer Khmer speech without chipmunking or pitch degradation.
  - Non-destructive timing conflict detection: if a segment still exceeds its allocated window, it preserves the complete speech audio without silent truncation and logs structured `TimingConflict` details.
- **Video Export Service (`VideoExportService`)**:
  - Remuxes video with synchronized timeline audio using explicit stream mapping (`-map 0:v:0 -map 1:a:0`).
  - Encodes audio to high-quality AAC (`-c:a aac -b:a 192k`).
  - Applies `-movflags +faststart` for instant web streaming and playback initialization.
  - Atomic export safety: writes to `.tmp.mp4` staging file before replacing final output file.
  - FFprobe container and stream verification checking duration and format integrity.
- **Dubbing Pipeline & Background Worker (`DubbingPipeline` & `process_dubbing`)**:
  - Full end-to-end orchestration connecting segments, synchronizer, exporter, and database state.
  - Background worker updating `ProcessingJob` progress (10% -> 30% -> 60% -> 80% -> 100%).
  - Transitions `Project.status` to `EXPORTING` and then `COMPLETED`.
  - Detailed error capturing and informative timing conflict notifications in job message.
- **Database Tracking & Alembic Migration**:
  - Extended `Video` model with `audio_timeline_path`, `exported_duration_seconds`, `exported_file_size_bytes`, and `is_export_outdated`.
  - Migration revision `b90d366cd5b0` created and executed cleanly against SQLite.
  - Automatic invalidation: editing transcripts, editing translations, retranslating, or regenerating TTS automatically flags `video.is_export_outdated = True`.
- **Dubbing & Export REST API Endpoints**:
  - `POST /api/projects/{project_id}/export`: Triggers asynchronous background dubbing and export.
  - `GET /api/projects/{project_id}/export/status`: Returns export readiness, job status, file size, duration, timing conflicts, and media URLs.
  - `GET /api/projects/{project_id}/export/video`: Media streaming endpoint supporting HTTP 206 Partial Content byte ranges for smooth video seeking.
  - `GET /api/projects/{project_id}/export/download`: Direct attachment download with project title filename.
- **Frontend Step 5 Workspace (`ProjectWorkspace.tsx`)**:
  - Stepper indicator updated to include Step 5: `5. Dubbed Video`.
  - Section 5 UI featuring:
    - Pre-export readiness checklist (Video uploaded, Transcribed, Translated, Voice generated).
    - "Generate Dubbed Video" / "Re-export Video" action buttons with real-time progress bar.
    - Prominent yellow warning banner when upstream transcripts/translations/audio were modified (`is_export_outdated = True`).
    - Timing conflicts panel detailing affected segments, original duration, Khmer duration, speed adjustment applied, and remaining overflow.
    - In-browser HTML5 `<video controls>` preview player loaded with the dubbed video.
    - Quick actions: "Download Dubbed Video (MP4)" and "Open in New Tab".
- **Testing**:
  - 9 comprehensive unit and integration tests in `backend/tests/test_dubbing.py`.
  - Live end-to-end dubbing pipeline verification on Docker backend container.
  - 60 backend automated tests passing with 0 failures.
  - TypeScript strict typecheck and production build passing with 0 errors.

## [0.5.0] - Phase 5 Complete (2026-10-24)

### Added
- **Google Khmer Text-to-Speech (`GoogleTTSProvider`)**:
  - Implemented concrete TTS provider conforming to `TTSProvider` using `gTTS>=2.5.0`.
  - Supports Khmer language code (`km`) with clear labeling: `Provider: Google gTTS`, `Language: Khmer (km)`, `Voice: Default Khmer Voice`.
  - Exponential backoff retry mechanism (configurable `TTS_MAX_RETRIES=3`) handling transient network and HTTP errors.
  - Duration measurement using `FFmpegVideoProcessor.get_audio_duration` via `ffprobe`.
  - Audio files saved as MP3 segments into `data/temp/tts_{project_id}_{segment_id}.mp3`.
  - Clean error handling with custom exceptions (`EmptyTextError`, `LanguageNotSupportedError`, `TTSNetworkError`, `TTSGenerationError`).
- **Database Tracking & Migration**:
  - Extended `GeneratedAudio` entity with `voice`, `is_outdated`, and `updated_at` columns.
  - Alembic migration `0cff7668ac18_add_audio_voice_and_outdated_flags.py` generated and applied.
  - Automatic audio invalidation: modifying or retranslating any Khmer translation segment automatically marks linked `GeneratedAudio.is_outdated = True`.
- **TTS API Endpoints**:
  - `POST /api/projects/{project_id}/tts`: Dispatches non-blocking background speech synthesis for all translated Khmer segments.
  - `GET /api/projects/{project_id}/generated-audio`: Retrieves list of generated audio records with playback URLs, durations, and outdated flags.
  - `POST /api/projects/{project_id}/tts/{segment_id}/regenerate`: Regenerates speech audio for an individual segment.
  - `GET /api/projects/{project_id}/tts/{segment_id}/audio`: Streams synthesized MP3 audio for browser playback with `audio/mpeg` content type.
- **Background Worker (`process_tts`)**:
  - Asynchronous background worker updating `ProcessingJob` progress (10% -> 95% -> 100%).
  - Transitions `Project.status` to `GENERATING_VOICE` and then `VOICE_GENERATED`.
- **Frontend Step 4 Workspace**:
  - Active Step 4 indicator in the dubbing pipeline stepper (`4. Khmer Voice ✓`).
  - Section 4 UI with provider badges, online service disclaimer, and "Generate Khmer Audio" action button.
  - Real-time generation progress bar.
  - Audio summary bar displaying total duration and segment count.
  - Segment cards featuring Khmer text, HTML `<audio controls>` player, duration readout, and single-segment `[Regenerate]` button.
  - Prominent amber alert badge on outdated segments where translation text was modified after audio generation.
- **Testing**:
  - 13 new unit, integration, and real TTS tests in `backend/tests/test_tts.py`.
  - Verified live Khmer speech generation with FFprobe audio stream and duration analysis.
  - 100% test pass rate across 51 backend tests.
  - Frontend TypeScript compilation and Vite production build verified with 0 errors.

## [0.4.1] - Phase 4.1 Complete (2026-10-24)

### Added
- **Natural Khmer Orthography Formatter (`KhmerTextFormatter`)**:
  - Implemented scriptio continua spacing rules for Khmer script (`\u1780-\u17D3`, `\u17D7`, `\u17DD`).
  - Safely collapses artificial word-level spaces generated by subword tokenizers (e.g. `វីដេអូ នេះ` → `វីដេអូនេះ`).
  - Strictly preserves meaningful spaces around Latin/English brand names (e.g. `KhmerDub AI`), programming terms (`Python 3`), and numbers (`100 នាក់`).
  - Corrects punctuation clinging (no space before `។`, `!`, `?`, `,`, `;` and single space after sentence delimiters).
  - Preserves Khmer repetition character (Leka `ៗ`).
  - Thorough unit test coverage in `tests/test_khmer_formatter.py`.
- **Domain Terminology Alignment & Hallucination Mitigation (`KhmerGlossary`)**:
  - Maps domain-specific English terms to standardized Cambodian vocabulary.
  - Fixes critical NLLB hallucinations: replaces `អចលនទ្រព្យ` (real estate) with `បញ្ញាសិប្បនិម្មិត` (Artificial Intelligence).
  - Distinguishes mechanical/algorithmic operation (`ដំណើរការ`) from human manual labor (`ធ្វើការ`).
  - Fixes greeting hallucination: replaces `ថ្ងៃអាទិត្យល្អ` (Good Sunday) with `អរុណសួស្តី!` (Good morning).
- **Lightweight Context-Aware Translation**:
  - `process_translation` constructs contextual windows from adjacent transcript segments (`prev_seg + current + next_seg`).
  - Retranslate endpoint (`POST /retranslate`) builds surrounding context lookahead and lookbehind.
  - Preserves 100% of individual segment boundaries, timestamps, and database links.
- **Generation Parameters Optimization**:
  - Configurable `TRANSLATION_NUM_BEAMS=2` preventing beam-search n-gram hallucinations.
  - Dynamic resolution of Khmer BOS token ID from tokenizer vocabulary (`convert_tokens_to_ids("khm_Khmr")`).
- **Evaluation Dataset**:
  - Benchmarked 20 varied English sentences across greetings, conversation, technical/AI, programming, numbers, questions, and narration.
  - 38 automated backend tests passing in Docker.

## [0.4.0] - Phase 4 Complete (2026-10-24)

### Added
- **NLLB-200 Translation Provider (`NLLBTranslationProvider`)**:
  - Implemented concrete translation provider using Meta's `facebook/nllb-200-distilled-600M` model.
  - FLORES-200 language code support (`eng_Latn` → `khm_Khmr`) with input code normalization (`en` → `eng_Latn`, `km` → `khm_Khmr`).
  - Thread-safe lazy model loading with in-memory caching (`_cache_lock`) and persistent Docker volume caching (`/root/.cache`).
  - Generation using beam search (`num_beams=4`), `forced_bos_token_id=256092`, and configurable max sequence length.
  - Process RSS memory monitoring utility (`get_current_process_ram_mb`) using `psutil`.
- **Alembic Database Migration**:
  - Configured Alembic migration environment (`backend/alembic/`) targeting SQLite database.
  - Migration `16a1a4d3bf49` added `is_manually_edited` and `is_outdated` flags to `translation_segments`.
- **Translation API Endpoints**:
  - `POST /api/projects/{project_id}/translate`: Asynchronous background translation job with duplicate prevention (`HTTP 409 Conflict`).
  - `GET /api/projects/{project_id}/translations`: Retrieves ordered translated segments enriched with linked transcript English text and timestamps.
  - `PATCH /api/projects/{project_id}/translations/{segment_id}`: Inline manual editing of Khmer translation text (`is_manually_edited=True`, `is_outdated=False`).
  - `POST /api/projects/{project_id}/translations/{segment_id}/retranslate`: Single-segment retranslation from its corresponding English transcript text.
  - `PATCH /api/projects/{project_id}/transcript/{segment_id}`: Automatically flags corresponding translation segment as `is_outdated=True` when transcript text is changed.
- **Background Worker (`process_translation`)**:
  - Translates unedited English transcript segments while strictly preserving user manual corrections (`is_manually_edited=True`).
  - Transitions `ProcessingJob` through `pending` → `running` (15%, 30%, 50%, 85%) → `completed` (100%).
- **Frontend Khmer Translation Workspace (`ProjectWorkspace.tsx`)**:
  - "Khmer Translation" section with NLLB model badge and "Translate to Khmer" / "Retranslate All" action buttons.
  - Real-time polling for background translation job progression.
  - Dual-column comparative segment view (Original English on the left, Khmer Translation on the right).
  - Visual status badges for `[English Changed (Outdated)]` and `[Manually Edited]`.
  - Inline editing with Save / Cancel controls and single-segment retranslate button.
- **Testing**:
  - 31 backend unit, integration, and workflow tests passing in Docker.
  - Verified manual edit preservation, outdated propagation, and single-segment retranslation.

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
