# Changelog

All notable changes to the KhmerDub AI project will be documented in this file.

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
