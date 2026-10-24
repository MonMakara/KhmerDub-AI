# KhmerDub AI - Development Guide

This guide provides instructions for developing, running, and testing **KhmerDub AI** locally on Ubuntu using Docker Compose.

---

## 1. Prerequisites

- **OS**: Ubuntu Linux (or modern Linux distribution)
- **Docker**: Docker Engine 24+ and Docker Compose v2+
- **Hardware**: Intel Core i7 13th Gen, 16 GB RAM, RTX 4060 GPU (optional for Phase 1)

Ensure Docker daemon is running and current user has Docker permissions:
```bash
docker ps
```

---

## 2. Quick Start

### 1. Clone repository & configure environment
```bash
cd /path/to/KhmerDub-AI
cp .env.example .env
```

### 2. Build and start containers
```bash
docker compose up -d --build
```

### 3. Verify running containers
```bash
docker compose ps
```

### 4. Access applications
- **Frontend Web UI**: [http://localhost:5173](http://localhost:5173)
- **Backend API**: [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check Endpoint**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

---

## 3. Daily Development Commands

### View live logs
```bash
# All services
docker compose logs -f

# Backend only
docker compose logs -f backend

# Frontend only
docker compose logs -f frontend
```

### Run Backend Tests (pytest)
```bash
docker compose exec backend pytest -v
```

### Run Frontend Typecheck and Build
```bash
docker compose exec frontend npm run typecheck
docker compose exec frontend npm run build
```

### Testing Transcription via cURL
```bash
# 1. Trigger transcription for a project with extracted audio
curl -X POST "http://localhost:8000/api/projects/$PROJ_ID/transcribe"

# 2. View generated transcript segments
curl -s "http://localhost:8000/api/projects/$PROJ_ID/transcript" | jq .

# 3. Edit a transcript segment
curl -X PATCH "http://localhost:8000/api/projects/$PROJ_ID/transcript/$SEGMENT_ID" \
  -H "Content-Type: application/json" \
  -d '{"text": "Corrected transcript text"}'
```

### Whisper Model Configuration
The following variables in `.env` control speech recognition:
- `WHISPER_MODEL`: Model size (`tiny`, `base`, `small`, `medium`, `large-v3`). Defaults to `base`.
- `WHISPER_DEVICE`: Execution device (`cpu` or `cuda`). Defaults to `cpu`.
- `WHISPER_COMPUTE_TYPE`: Precision/quantization (`int8`, `float32`, or `float16` on CUDA). Defaults to `int8`.
- `WHISPER_LANGUAGE`: Primary transcription language (default `en`).
- `WHISPER_VAD_FILTER`: Voice activity detection filter (default `true`).
Model weights are automatically cached inside the persistent Docker volume `khmerdub_model_cache` at `/root/.cache`.
```bash
# 1. Create a project
PROJ_ID=$(curl -s -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"title": "Terminal Upload Test"}' | jq -r .id)

# 2. Upload an MP4 video file
curl -X POST "http://localhost:8000/api/projects/$PROJ_ID/upload" \
  -F "file=@/path/to/video.mp4"

# 3. Check status and extracted audio
curl -s "http://localhost:8000/api/projects/$PROJ_ID" | jq .
```

### Stop containers
```bash
docker compose down
```

---

## 4. Enabling Optional NVIDIA GPU Acceleration

By default, Phase 1 uses CPU execution to ensure effortless reproducibility.

To enable NVIDIA GPU acceleration with your RTX 4060 GPU:
1. Ensure `nvidia-container-toolkit` is installed on your Ubuntu host.
2. In `compose.yaml`, add the `deploy` reservation to `backend`:
   ```yaml
   services:
     backend:
       deploy:
         resources:
           reservations:
             devices:
               - driver: nvidia
                 count: 1
                 capabilities: [gpu]
   ```
3. Set `WHISPER_DEVICE=cuda` and `WHISPER_COMPUTE_TYPE=float16` in `.env`.
4. Restart containers: `docker compose up -d`.
