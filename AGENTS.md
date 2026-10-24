# AI Agent Guidelines - KhmerDub AI

These guidelines govern how AI coding assistants work on this repository. Every agent must strictly follow these rules to maintain project modularity, simplicity, and safety.

---

## 1. Core Principles

1. **Step-by-Step Evolution**: Never generate the entire application or multiple phases at once. Execute only the currently requested phase.
2. **Keep It Simple (KISS)**: Do not prematurely introduce Redis, Celery, microservices, or complex distributed abstractions for Version 1.
3. **Reproducibility First**: Always prioritize Docker-first execution. Application dependencies must run inside Docker containers, never globally on Ubuntu.
4. **Preserve Integrity**: Do not rewrite working modules or break existing tests.
5. **No Hallucinated Testing**: Never report tests as passing without actually executing `pytest` or frontend verification commands.

---

## 2. Architecture & File Structure Conventions

- **Frontend**: Vite + React + TypeScript + Tailwind CSS in `frontend/`.
- **Backend**: FastAPI + Pydantic + SQLAlchemy in `backend/app/`.
- **Media & Models**:
  - Keep AI model logic completely abstracted behind interface classes in `backend/app/services/`.
  - API endpoints in `backend/app/api/` should orchestrate business logic, not embed raw AI library code.
  - Video and audio operations must use FFmpeg wrapped in `VideoProcessor`.
- **Data & Cache**:
  - User media files reside in `data/uploads/`, `data/outputs/`, and `data/temp/`.
  - AI model checkpoints and weights must be cached in Docker volume `model_cache` (`/root/.cache`), never committed to Git.
  - Database is SQLite (`/app/data/khmerdub.db`) managed via SQLAlchemy models and Alembic migrations.

---

## 3. Communication & Code Style

- Write clean, type-annotated Python 3.11 code adhering to PEP 8.
- Write modular React components with TypeScript strict mode enabled.
- Handle errors explicitly; never use blank `except:` blocks or swallow audio/video processing failures.
- Provide user-friendly error messages on the frontend and detailed logs on the backend.

---

## 4. Testing Requirements

- Every backend endpoint and service provider must have corresponding unit or integration tests in `backend/tests/`.
- Run tests inside Docker:
  ```bash
  docker compose exec backend pytest -v
  ```
- Any newly introduced module must be verified before moving to the next development phase.
