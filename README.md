# KhmerDub AI

**KhmerDub AI** is an automated web platform that converts English videos into Khmer-dubbed videos using open-source AI transcription, machine translation, and speech synthesis.

---

## 1. Features (Version 1 Scope)

1. **Video Upload** *(Phase 2 Complete)*: Safe MP4 video uploads with streaming chunk processing (< 500 MB limit), FFprobe container inspection, filename sanitization, and video metadata extraction.
2. **Audio Extraction** *(Phase 2 Complete)*: FFmpeg extraction converting video audio track to 16,000 Hz mono 16-bit PCM WAV in a non-blocking background job. Includes audio preview player and retry support.
3. **English Transcription** *(Phase 3 Complete)*: Accurate timestamped English transcription using `faster-whisper` (CTranslate2 INT8 on CPU) with Voice Activity Detection, background execution, and inline transcript editing in the web UI.
4. **English-to-Khmer Translation** *(Phase 4 Complete)*: Free, locally runnable neural machine translation using Meta's NLLB-200 (`eng_Latn` → `khm_Khmr`) with thread-safe lazy caching, background execution, side-by-side comparative review, manual editing preservation, and single-segment retranslation.
5. **Khmer Text-to-Speech** *(Phase 5)*: Speech synthesis using Google gTTS for Khmer audio segments.
6. **Audio Synchronization** *(Phase 6)*: Dynamic audio alignment matching original segment timestamps with conservative speed adjustment.
7. **Video Export** *(Phase 6)*: Clean remuxing via FFmpeg to export a final dubbed MP4 video.

---

## 2. Tech Stack

- **Frontend**: React 18, Vite, TypeScript, Tailwind CSS, Lucide Icons.
- **Backend**: Python 3.11, FastAPI, Pydantic, SQLAlchemy 2.0, SQLite.
- **Media & AI**: FFmpeg, faster-whisper, NLLB-200, gTTS.
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
│   └── temp/             # Extracted audio & synthesized segments
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
