# KhmerDub AI - Development Roadmap

## Project Status

- **Current Phase**: Phase 10.2 Complete — Project Management Improvements (Rename & Safe Cascading Deletion)
- **Overall Status**: Version 1 Complete & Verified

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

### [x] Phase 5: Google Khmer TTS (gTTS)
- [x] Verification of Google gTTS Khmer (`km`) support with sample audio generation.
- [x] Concrete `GoogleTTSProvider` implementation conforming to `TTSProvider` with exponential backoff retries.
- [x] Accurate duration measurement of synthesized audio segments via `FFmpegVideoProcessor.get_audio_duration`.
- [x] Background worker (`process_tts`) orchestrating segment-level speech synthesis.
- [x] Database migration for `voice`, `is_outdated`, and `updated_at` fields in `GeneratedAudio`.
- [x] Automatic invalidation (`is_outdated=True`) when Khmer translation segments are updated or retranslated.
- [x] API endpoints: `POST /tts`, `GET /generated-audio`, `POST /tts/{segment_id}/regenerate`, `GET /tts/{segment_id}/audio`.
- [x] Frontend Step 4 workspace: audio players, duration readouts, outdated warnings, individual segment regeneration.
- [x] 51 automated unit, integration, and real TTS tests passing in Docker.

### [x] Phase 6: Audio Synchronization & Video Export
- [x] Project storage centralization under `data/projects/{project_id}/` (voice, timeline, exported MP4) with backward compatibility.
- [x] Transcript-timed audio synchronization (`AudioSynchronizationService`) aligning synthesized Khmer speech to English segment timestamps.
- [x] Standardized WAV pieces (44.1kHz, 16-bit, stereo) concatenated via FFmpeg concat demuxer without re-encoding quality degradation.
- [x] Conservative tempo adjustment (max 1.25x via `atempo`) to fit natural Khmer speech into allocated time slots.
- [x] Non-destructive timing conflict detection reporting overflows without silent speech truncation.
- [x] Clean FFmpeg remuxing (`VideoExportService`) replacing original audio with synchronized Khmer audio (`-map 0:v:0 -map 1:a:0`).
- [x] Faststart MP4 container optimization (`+faststart`) for instant in-browser web playback.
- [x] Atomic video publishing via temporary staging file (`.tmp.mp4`) preventing incomplete or corrupted downloads.
- [x] Database migration adding `audio_timeline_path`, `exported_duration_seconds`, `exported_file_size_bytes`, `is_export_outdated`, and `updated_at`.
- [x] Automatic invalidation: modifying transcript, translation, or audio triggers `is_export_outdated = True`.
- [x] API endpoints: `POST /export`, `GET /export/status`, `GET /export/video` (HTTP 206 Partial Content), `GET /export/download`.
- [x] Frontend Step 5 workspace: readiness checklist, timing conflicts panel, real-time export progress, video player preview, and download button.
- [x] 60 automated backend tests passing in Docker with verified end-to-end dubbing pipeline.

### [x] Phase 6.1: Synchronization Reliability & Strict Duration Validation
- [x] Root cause investigation of duration mismatch (differentiating actual speech overflow from codec/container tolerance).
- [x] Strict duration validation in `AudioSynchronizationService` preventing exports that would cut off Khmer speech.
- [x] Introduction of `TimingConflictError` halting pipeline before corrupted or overlong video export.
- [x] Enhanced `TimingConflict` reporting: `required_tempo`, `max_tempo_factor`, `overflow_seconds`, and `suggested_action`.
- [x] FFprobe-based stream and container duration verification in `VideoExportService` (`expected_duration` ± tolerance).
- [x] UI update in `ProjectWorkspace.tsx`: active export guard badge, detailed conflict breakdown, and actionable trimming recommendations.
- [x] 11 new automated test cases covering longer audio, shorter audio, exact duration, tail overflow, consecutive segments, overlapping segments, silence padding, safe tempo, conflict details, duration verification, and non-truncation.
- [x] Verified real video testing across Case A (shorter speech), Case B (safe tempo fit), and Case C (conflict blocked).
- [x] 71 automated backend tests and frontend typecheck/build passing in Docker.

### [x] Phase 7: Stabilization, Reliability & End-to-End Quality Assurance
- [x] Shared AI model inference guard (`app/core/ai_guard.py`) preventing concurrent memory-heavy Whisper and NLLB CPU execution.
- [x] Startup interrupted job recovery (`app/core/recovery.py`) self-healing orphan jobs across container restarts without deleting files or records.
- [x] Deduplication of active jobs in audio extraction endpoint (`extract-audio`).
- [x] Configurable timing safety margin (`safety_margin_seconds=0.05`) clearly separating raw available windows from effective windows.
- [x] Complete end-to-end integration test suite (`tests/test_e2e_pipeline.py`) verifying Cases A through E (short, medium, pauses, speech near end, and recovery from long translation).
- [x] Total automated test suite expanded to 81 backend tests passing (100%).
- [x] Live container restart and database persistence verified.
- [x] Documentation and manual browser testing checklist completed.

### [x] Phase 8: Khmer Voice Selection (Google gTTS & Microsoft Edge TTS)
- [x] Integration of `edge-tts` inside Docker development environment with zero global Ubuntu packages.
- [x] Concrete `EdgeTTSProvider` implementation conforming to `TTSProvider` with exponential backoff retries and safe async execution.
- [x] Multi-voice support for official Microsoft Neural Khmer voices: `km-KH-PisethNeural` (Male) and `km-KH-SreymomNeural` (Female).
- [x] Factory registry (`get_tts_provider`, `is_valid_voice_combination`, `list_supported_voices`) managing voice metadata and provider instantiation.
- [x] Database migration (`c1f72a4d9e01`) adding `tts_provider` and `tts_voice` to `projects` table with safe column introspection.
- [x] API endpoints:
  - `GET /api/tts/voices`: Returns available providers, voices, descriptions, and gender tags.
  - `POST /api/tts/preview`: Generates cached preview audio stream (`audio/mpeg`) for any voice with max 200 character limit.
  - `PATCH /api/projects/{id}/voice`: Updates project voice and automatically invalidates existing audio (`is_outdated=True`) and export (`is_export_outdated=True`).
- [x] Background worker (`process_tts`) and regenerate endpoint updated to synthesize using the project's selected provider and voice.
- [x] Full audio format compatibility: Edge TTS MP3 audio tracks seamlessly normalized to 44.1kHz WAV by `AudioSynchronizationService`.
- [x] Frontend Step 4 workspace updated:
  - Voice selection card deck (Google Khmer, Microsoft Piseth, Microsoft Sreymom) with gender and provider badges.
  - Interactive "Preview Voice" button with live audio playback.
  - Outdated warning banner when voice selection changes.
  - Voice metadata label displayed on each synthesized segment card.
- [x] Total automated test suite expanded to 92 passing backend tests (11 new tests in `tests/test_voice_selection.py`).
- [x] Production frontend build verified with TypeScript strict mode enabled.

### [x] Phase 9: AI Translation API Integration (Google Gemini, OpenAI, Claude, Custom AI)
- [x] Official `google-genai` Python SDK installed in Docker environment with cryptography library for secure credentials.
- [x] Multi-provider architecture supporting Google Gemini, OpenAI, Anthropic Claude, and OpenAI-compatible custom endpoints.
- [x] Symmetric credential encryption (`backend/app/core/credentials.py`) using Fernet (AES-128-CBC + HMAC-SHA256) at `/app/data/.secrets/credentials.enc`.
- [x] Masked API key display (`AIzaSy...4aB8`), environment variable override (`GEMINI_API_KEY`), and zero plaintext exposure.
- [x] Multi-style translation prompt engineering (`backend/app/services/translation/prompts.py`) supporting 5 distinct modes: `natural`, `short`, `simple`, `formal`, `standard`.
- [x] Strict technical glossary (`KhmerGlossary`) prompt injection and regex normalization guaranteeing standard terminology (`បញ្ញាសិប្បនិម្មិត`, `ដំណើរការ`).
- [x] Prompt injection defense sanitizing and strictly bounding user custom prompt instructions.
- [x] Concrete translation providers (`gemini.py`, `openai_compat.py`, `claude.py`) implementing `TranslationProvider` with exponential backoff on rate limits, JSON structured outputs, and fallback per-segment processing.
- [x] Dynamic provider registry (`backend/app/services/translation/registry.py`) and connection validation supporting `nllb` (local offline default), `gemini`, `openai`, `claude`, and `custom`.
- [x] Database migration (`d2a83b5e1f02`) adding `translation_provider` and `translation_style` to `projects` table, plus `style` and `explanation` to `translation_segments`.
- [x] API endpoints:
  - `GET /api/translation/providers`: Catalog of providers, supported models, and styles.
  - `POST /api/translation/test-connection`: Non-blocking authentication test and connectivity ping.
  - `POST /api/translation/credentials` & `DELETE /api/translation/credentials/{provider}`: Secure storage and removal of API keys.
  - `PATCH /api/projects/{id}/translation-settings`: Project translation provider and style updates.
  - `POST /api/projects/{id}/translations/{segment_id}/ai-improve`: Per-segment context-, style-, and duration-aware AI translation improvement.
  - `POST /api/projects/{id}/translations/{segment_id}/alternatives`: Generation of 3 distinct alternatives (Natural, Simple, Short) side-by-side.
  - `POST /api/projects/{id}/translations/{segment_id}/apply`: 1-click apply of AI suggestion/alternative, updating segment and automatically invalidating generated audio and video export.
- [x] Automated test suite expanded to 106 passing backend tests (14 tests in `tests/test_ai_translation.py`).
- [x] Production frontend build verified with TypeScript strict mode enabled (0 errors).

### [x] Phase 10: Professional UI/UX Redesign & Modular Dubbing Studio
- [x] Complete Dashboard overhaul (`Dashboard.tsx`): Real metrics (`totalProjects`, `completedProjects`, `processingProjects`, `attentionProjects`), recent projects list with progress bars, fast project creation drawer, and AI engine overview.
- [x] Advanced Project Management (`Projects.tsx`): Real-time search, status filter pills, sorting options, Grid vs Table view switcher, stage progress bars, and "Open Studio" continue actions.
- [x] Professional Dubbing Studio Architecture (`ProjectWorkspace.tsx`): Replaced 2,550-line vertical monolith with a 5-stage tabbed studio (`Media`, `Transcript`, `Translation`, `Voice`, `Export`) and non-stalling polling.
- [x] Studio Navigation Bar (`StudioHeader.tsx`): Compact 5-stage stepper with status indicators, background processing spinners, timing conflict badge, and manual refresh.
- [x] Persistent Video Preview Dock (`PersistentVideoPlayer.tsx`): Docked player accessible across all editing tabs, click-to-seek timestamp navigation, active segment highlighting by playhead time, speed presets (`0.75x`, `1x`, `1.25x`, `1.5x`), and volume controls.
- [x] Media Management Tab (`MediaTab.tsx`): Drag-and-drop video upload zone with real-time percentage progress, FFprobe container metadata (dimensions, duration, codecs), and 16kHz PCM WAV audio extraction player.
- [x] Transcript Editor Tab (`TranscriptTab.tsx`): Faster-Whisper English transcript list, search filter, click-to-seek timestamp navigation, inline segment text editing, and timing window badges.
- [x] Bilingual Comparative Translation Tab (`TranslationTab.tsx`): Side-by-side English + Khmer layout, provider & style selector, segment cards with audio players, timing warnings, AI Improve modal trigger, and per-segment retranslation.
- [x] AI Refinement & Alternatives Modal (`AIImproveModal.tsx`): Side-by-side comparative preview for Gemini/OpenAI/Claude/NLLB, 3-style alternatives generation (Natural, Simple, Short), duration constraints, and 1-click apply.
- [x] Khmer Voice Selection Tab (`VoiceTab.tsx`): Cards for Google Khmer, Microsoft Piseth, and Microsoft Sreymom with voice preview audio players, batch speech generation, and single-segment regeneration.
- [x] Export & Delivery Tab (`ExportTab.tsx`): 5-point readiness checklist, timing conflict analysis with overflow breakdown, export progress bar, in-browser dubbed video player, and MP4 download.
- [x] Reorganized Settings Workspace (`Settings.tsx`): Tabbed configuration sections for AI Translation Providers & API Keys, Voice Providers, AI Models, Hardware, Storage, and Developer CLI.
- [x] Modular Component Extraction (`frontend/src/components/studio/`): AIImproveModal, ExportTab, MediaTab, PersistentVideoPlayer, StudioHeader, TranscriptTab, TranslationTab, VoiceTab.
- [x] Automated Verification: 106 backend tests passing (100%), TypeScript typecheck passing (0 errors), and Vite production build verified.

### [x] Phase 10.2: Project Management Improvements (Rename & Safe Cascading Deletion)
- [x] Project Rename API (`PATCH /api/projects/{project_id}`): Validated title updates (1 to 255 characters, non-empty, stripped whitespace) preserving project ID, metadata, and directory paths.
- [x] Two-Stage Safe Project Deletion (`DELETE /api/projects/{project_id}`):
  - Active background job check: returns HTTP 409 Conflict if jobs are pending or running, or if project is active (`transcribing`, `translating`, `generating_voice`, `synchronizing`).
  - Stage 1: Mark project status as `ProjectStatus.DELETING` to reject new operations.
  - Stage 2: Safely remove project files and cascade-delete database records.
- [x] Strict Path Traversal Prevention (`delete_project_storage`):
  - Reject `..`, `/`, and `\` in `sanitize_project_id`.
  - Validate resolved directory ownership under `DATA_DIR/projects` and `UPLOADS_DIR`.
  - Never touches shared model weights, `.secrets`, `khmerdub.db`, or other projects' files.
- [x] Project Three-Dot Action Menu (`ProjectActionMenu.tsx`):
  - Accessible on project cards (Grid view), table rows (Table view), and Recent Projects on the Dashboard.
  - Actions: Open Studio, Rename Project, Delete Project.
- [x] Studio In-Place Renaming (`StudioHeader.tsx`): Quick rename pencil button next to the project title in Dubbing Studio.
- [x] Interactive Confirmation Modals:
  - `RenameProjectModal.tsx`: Focus management, character count, validation error handling, and save/cancel actions.
  - `DeleteProjectModal.tsx`: Warning breakdown of assets to be deleted, and type-to-confirm input requiring the user to type the exact project title before the deletion button is unlocked.
- [x] Dashboard Real-Time Synchronization:
  - Deleting or renaming immediately updates metric cards (Total, In Progress, Exported MP4, Attention) and Recent Projects list without page reload.
- [x] Automated Testing:
  - 13 automated backend tests in `tests/test_project_management.py` covering rename, empty title, too long title, delete success, active job 409 conflict, active status 409 conflict, other project preservation, path traversal prevention, duplicate delete 404, and deleting status mutation blocks.
  - Total backend test suite expanded to 119 passing tests (100%).
- [x] Full Browser Automation Verification:
  - Verified in real Firefox headless via geckodriver across all 7 workflows (create disposable project, rename, refresh persistence, 3-dot menu, cancel delete, type-to-confirm delete, and dashboard count sync).

---

## Future Scope (Post Version 1)
- Voice cloning from original English speakers.
- Background music & ambient sound preservation.
- Multiple speakers and voice emotion control.
- Subtitle generation and export (.srt / .vtt).
