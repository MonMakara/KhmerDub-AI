# KhmerDub AI

**KhmerDub AI** is an automated web platform that converts English videos into Khmer-dubbed videos using open-source AI transcription, machine translation, and speech synthesis.

---

## 1. Features (Version 1 Scope)

1. **Video Upload** *(Phase 2 Complete)*: Safe MP4 video uploads with streaming chunk processing (< 500 MB limit), FFprobe container inspection, filename sanitization, and video metadata extraction.
2. **Audio Extraction** *(Phase 2 Complete)*: FFmpeg extraction converting video audio track to 16,000 Hz mono 16-bit PCM WAV in a non-blocking background job. Includes audio preview player and retry support.
3. **English Transcription** *(Phase 3 Complete)*: Accurate timestamped English transcription using `faster-whisper` (CTranslate2 INT8 on CPU) with Voice Activity Detection, background execution, and inline transcript editing in the web UI.
4. **English-to-Khmer Translation** *(Phase 4 & 4.1 Complete)*: Free, locally runnable neural machine translation using Meta's NLLB-200 (`eng_Latn` → `khm_Khmr`) with thread-safe lazy caching, natural Khmer text compaction (`KhmerTextFormatter`), terminology glossary (`KhmerGlossary`), context-aware translation, side-by-side comparative review, manual editing preservation, and single-segment retranslation.
5. **Khmer Text-to-Speech & Voice Selection** *(Phase 5 & Phase 8 Complete)*: Multi-provider speech synthesis supporting:
   - **Google gTTS**: Default Khmer online voice (neutral tone).
   - **Microsoft Edge Neural Piseth**: Male voice (`km-KH-PisethNeural`), friendly and positive tone.
   - **Microsoft Edge Neural Sreymom**: Female voice (`km-KH-SreymomNeural`), friendly and positive tone.
   Includes interactive voice preview player, per-project voice selection persistence, audio invalidation on voice change, individual segment regeneration, and 44.1kHz audio normalization.
6. **Audio Synchronization** *(Phase 6 Complete)*: Transcript-timed audio synchronization that aligns synthesized Khmer speech segments onto original English timestamps, standardizes audio pieces (44.1kHz stereo 16-bit PCM WAV), inserts silence padding, applies conservative tempo adjustment (max 1.25x via `atempo`), and detects timing conflicts without silent speech truncation.
7. **Video Export** *(Phase 6 Complete)*: Clean remuxing via FFmpeg replacing the original audio with the synchronized Khmer speech track using explicit stream mapping (`-map 0:v:0 -map 1:a:0`), AAC audio, faststart MP4 container optimization for web streaming, atomic publishing, in-browser video preview player, and instant download.
8. **Stabilization & Reliability** *(Phase 7 Complete)*: Shared AI model concurrency guard serializing Whisper and NLLB to prevent memory spikes on 16GB laptops, automated interrupted-job recovery on startup, active job deduplication, configurable 50ms timing safety margins, and 92 passing automated tests across real English video pipelines.
9. **AI Translation API Integration** *(Phase 9 Complete)*: Cloud AI language model integration using Google Gemini (`gemini-2.5-flash`, `gemini-1.5-flash`, `gemini-1.5-pro`) via the official `google-genai` SDK:
   - **5 Translation Modes/Styles**: Natural Spoken Khmer, Short for Video Dubbing (fitted timing slots), Simple & Clear, Formal / Professional, and Standard.
   - **AI Improve**: One-click context- and timing-aware translation refinement per segment.
   - **Structured Alternatives**: Instant generation of 3 distinct translation styles (Natural, Simple, Short) with 1-click apply and automated audio invalidation.
   - **Secure Key Storage**: Client keys encrypted with Fernet (AES-128-CBC + HMAC-SHA256) at `/app/data/.secrets/credentials.enc`, never exposed to the browser or committed to Git.
   - **Meta NLLB-200**: Preserved as the default free local offline translation provider.

---

## 2. Tech Stack

- **Frontend**: React 18, Vite, TypeScript, Tailwind CSS, Lucide Icons.
- **Backend**: Python 3.11, FastAPI, Pydantic, SQLAlchemy 2.0, SQLite.
- **Media & AI**: FFmpeg, faster-whisper, NLLB-200, gTTS, edge-tts.
- **Infrastructure**: Docker & Docker Compose.

---

## 3. Quick Start (Docker Development)

### Prerequisites
- Ubuntu Linux (or any modern Linux / macOS / Windows with Docker)
- Docker Engine & Docker Compose

### Step 1: Clone & Configure
```bash
cp .env.example .env
```

### Step 2: Start Containers
```bash
docker compose up -d --build
```

### Step 3: Access Services
- **Frontend Dashboard**: [http://localhost:5173](http://localhost:5173)
- **Backend API**: [http://localhost:8000](http://localhost:8000)
- **API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **System Health Check**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

---

## 4. Useful Commands

```bash
# View all container logs
docker compose logs -f

# View backend logs only
docker compose logs -f backend

# Run backend unit and integration tests
docker compose exec backend pytest -v

# Stop all containers
docker compose down
```

---

## 5. Project Structure

```
KhmerDub-AI/
├── frontend/             # React + Vite + TypeScript + Tailwind
│   ├── src/              # Components, pages, services, types
│   └── Dockerfile
├── backend/              # FastAPI application & AI service layer
│   ├── app/              # Core config, API routes, models, services
│   ├── tests/            # Pytest test suite
│   ├── Dockerfile
│   └── requirements.txt
├── data/                 # Persistent media directory
│   ├── uploads/          # Original uploaded videos
│   ├── outputs/          # Dubbed exported videos
│   ├── temp/             # Temporary processing files
│   └── projects/         # Per-project media (voice, timeline, exported video)
├── docs/                 # Documentation (Architecture, Development, Roadmap)
├── compose.yaml          # Docker Compose definition
├── .env.example          # Environment variable template
├── AGENTS.md             # AI development guidelines
└── README.md
```

---

## 6. Architecture & Documentation

- [System Architecture](docs/ARCHITECTURE.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [Project Roadmap](docs/ROADMAP.md)
- [Changelog](docs/CHANGELOG.md)
- [AI Agent Rules](AGENTS.md)
