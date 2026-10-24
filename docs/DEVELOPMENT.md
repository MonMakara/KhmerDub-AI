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

# 3. Edit a transcript segment (automatically flags linked translation as outdated)
curl -X PATCH "http://localhost:8000/api/projects/$PROJ_ID/transcript/$SEGMENT_ID" \
  -H "Content-Type: application/json" \
  -d '{"text": "Corrected transcript text"}'
```

### Testing Translation via cURL (Phase 4)
```bash
# 1. Trigger English-to-Khmer translation
curl -X POST "http://localhost:8000/api/projects/$PROJ_ID/translate"

# 2. View generated translation segments (with English text and timestamps)
curl -s "http://localhost:8000/api/projects/$PROJ_ID/translations" | jq .

# 3. Manually edit a Khmer translation segment
curl -X PATCH "http://localhost:8000/api/projects/$PROJ_ID/translations/$TRANSLATION_SEGMENT_ID" \
  -H "Content-Type: application/json" \
  -d '{"khmer_text": "អត្ថបទបកប្រែកែសម្រួល"}'

# 4. Retranslate an individual segment from English
curl -X POST "http://localhost:8000/api/projects/$PROJ_ID/translations/$TRANSLATION_SEGMENT_ID/retranslate"
```

### Testing AI Translation API & LLM Features via cURL (Phase 9)
```bash
# 1. List translation providers (NLLB, Gemini, OpenAI, Claude, Custom) and styles
curl -s "http://localhost:8000/api/translation/providers" | jq .

# 2. Test AI provider connection (Gemini, OpenAI, Claude, or Custom)
curl -X POST "http://localhost:8000/api/translation/test-connection" \
  -H "Content-Type: application/json" \
  -d '{"provider": "gemini", "api_key": "YOUR_GEMINI_KEY"}'

# Test Custom OpenAI-compatible endpoint (e.g. DeepSeek / Groq / OpenRouter / Ollama)
curl -X POST "http://localhost:8000/api/translation/test-connection" \
  -H "Content-Type: application/json" \
  -d '{"provider": "custom", "api_key": "YOUR_DEEPSEEK_KEY", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"}'

# 3. Securely save AI provider credentials (encrypted at /app/data/.secrets/credentials.enc)
curl -X POST "http://localhost:8000/api/translation/credentials" \
  -H "Content-Type: application/json" \
  -d '{"provider": "custom", "api_key": "YOUR_KEY", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"}'

# 4. Update project translation settings (Custom AI, Gemini, OpenAI, or Claude with 'short' dubbing mode)
curl -X PATCH "http://localhost:8000/api/projects/$PROJ_ID/translation-settings" \
  -H "Content-Type: application/json" \
  -d '{"translation_provider": "custom", "translation_style": "short"}'

# 5. AI improve an individual translation segment with timing awareness
curl -X POST "http://localhost:8000/api/projects/$PROJ_ID/translations/$TRANSLATION_SEGMENT_ID/ai-improve" \
  -H "Content-Type: application/json" \
  -d '{"style": "short", "custom_prompt": "Make concise to fit under 2.5s"}'

# 6. Generate structured alternatives (Natural, Simple, Short)
curl -X POST "http://localhost:8000/api/projects/$PROJ_ID/translations/$TRANSLATION_SEGMENT_ID/alternatives"

# 7. Apply chosen translation alternative
curl -X POST "http://localhost:8000/api/projects/$PROJ_ID/translations/$TRANSLATION_SEGMENT_ID/apply" \
  -H "Content-Type: application/json" \
  -d '{"khmer_text": "វីដេអូនេះពន្យល់ពីដំណើរការបញ្ញាសិប្បនិម្មិត។", "style": "short"}'
```

### Testing Khmer Text-to-Speech & Voice Selection via cURL (Phase 5 & Phase 8)
```bash
# 1. List all available Khmer voices (Google Khmer, Microsoft Piseth, Microsoft Sreymom)
curl -s "http://localhost:8000/api/tts/voices" | jq .

# 2. Preview voice speech audio before generating
curl -X POST "http://localhost:8000/api/tts/preview" \
  -H "Content-Type: application/json" \
  -d '{"provider": "edge", "voice": "km-KH-PisethNeural", "text": "សួស្តី KhmerDub AI"}' \
  --output preview_piseth.mp3

# 3. Update project voice selection (Microsoft Piseth Male)
curl -X PATCH "http://localhost:8000/api/projects/$PROJ_ID/voice" \
  -H "Content-Type: application/json" \
  -d '{"tts_provider": "edge", "tts_voice": "km-KH-PisethNeural"}'

# 4. Trigger background speech synthesis using the project's selected voice
curl -X POST "http://localhost:8000/api/projects/$PROJ_ID/tts"

# 5. View generated audio records with durations and voice metadata
curl -s "http://localhost:8000/api/projects/$PROJ_ID/generated-audio" | jq .

# 6. Regenerate speech audio for a single segment
curl -X POST "http://localhost:8000/api/projects/$PROJ_ID/tts/$TRANSLATION_SEGMENT_ID/regenerate"

# 7. Stream or download synthesized MP3 segment
curl -o segment.mp3 "http://localhost:8000/api/projects/$PROJ_ID/tts/$TRANSLATION_SEGMENT_ID/audio"
```

### Testing Audio Synchronization & Video Export via cURL (Phase 6)
```bash
# 1. Trigger background dubbing and video export
curl -X POST "http://localhost:8000/api/projects/$PROJ_ID/export"

# 2. Poll export status, progress, and timing conflicts
curl -s "http://localhost:8000/api/projects/$PROJ_ID/export/status" | jq .

# 3. Stream dubbed MP4 video with byte-range support (HTTP 206)
curl -i -r 0-1023 "http://localhost:8000/api/projects/$PROJ_ID/export/video"

# 4. Download finalized dubbed MP4 video with attachment headers
curl -O -J "http://localhost:8000/api/projects/$PROJ_ID/export/download"
```

### Text-to-Speech Providers (Google gTTS & Microsoft Edge TTS)
KhmerDub AI supports multiple speech providers behind the abstract `TTSProvider` interface:
- **Google gTTS** (`provider="gtts"`, `voice="default"`): Cloud synthesis via Google Translate endpoint (`https://translate.google.com/translate_tts`). Normal speed, clear neutral tone.
- **Microsoft Edge TTS** (`provider="edge"`): Neural speech synthesis via `edge-tts` calling Microsoft Speech Services. Voices:
  - `km-KH-PisethNeural` (Male, friendly & positive)
  - `km-KH-SreymomNeural` (Female, friendly & positive)

> [!NOTE]
> **Online Service Notice**: Both Google gTTS and Microsoft Edge TTS require active internet access. Neither provider executes as an offline local neural model on CPU/GPU. Edge TTS interfaces with Microsoft's cloud speech endpoints and is subject to service availability.


### Translation Model Configuration (NLLB-200)
The following variables in `.env` control English-to-Khmer translation:
- `TRANSLATION_PROVIDER`: Translation service provider (`nllb`). Defaults to `nllb`.
- `TRANSLATION_MODEL`: Hugging Face repository or checkpoint (`facebook/nllb-200-distilled-600M`).
- `TRANSLATION_SOURCE_LANG`: Source language FLORES-200 code (`eng_Latn`).
- `TRANSLATION_TARGET_LANG`: Target language FLORES-200 code (`khm_Khmr`).
- `TRANSLATION_DEVICE`: Execution device (`cpu` or `cuda`). Defaults to `cpu`.
- `TRANSLATION_BATCH_SIZE`: Inference batch size (default `1` for minimal RAM footprint on CPU).
- `TRANSLATION_MAX_INPUT_TOKENS`: Maximum sequence token length (default `512`).

> [!NOTE]
> **Model License**: Meta's `facebook/nllb-200-distilled-600M` model is released under the **CC BY-NC 4.0** license (Creative Commons Attribution-NonCommercial 4.0 International) for research and non-commercial usage.

### Database Migrations (Alembic)
KhmerDub AI uses Alembic for database schema versioning:
```bash
# Apply pending migrations
docker compose exec backend alembic upgrade head

# Create a new migration revision
docker compose exec backend alembic revision --autogenerate -m "describe_changes"
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

---

## 5. Manual End-to-End Browser Testing Checklist

Follow this checklist to verify the full platform in your browser at [http://localhost:5173](http://localhost:5173):

1. **Create Project**:
   - Navigate to the **Projects** tab. Click **"New Project"**, enter title (e.g. `Browser Test 1`), and click **"Create Project"**.
2. **Step 1: Upload Video**:
   - Drag and drop or browse for an English `.mp4` video (< 500 MB).
   - Verify upload progress bar displays smoothly.
   - Verify video preview player appears and audio extraction automatically triggers and completes (`Status: Audio Extracted`).
3. **Step 2: English Transcription**:
   - Click **"Transcribe English Audio"**.
   - Verify progress bar and segment listing.
   - Click the inline edit button on a segment, change a word, and save. Verify the update persists.
4. **Step 3: English-to-Khmer Translation**:
   - Click **"Translate to Khmer"**.
   - Review side-by-side English vs. Khmer text with terminology glossary alignment.
   - Edit a Khmer sentence manually. Verify the **[Manually Edited]** badge appears.
5. **Step 4: Khmer Speech Synthesis**:
   - Click **"Generate Khmer Audio"**.
   - Listen to synthesized audio segments using the embedded audio players.
   - Edit a translation segment in Step 3; observe that the corresponding audio segment in Step 4 displays the amber **[Text Modified (Outdated)]** warning.
   - Click **"Regenerate"** on that specific segment to update its voice track.
6. **Step 5: Dubbed Video Export**:
   - Click **"Generate Dubbed Video"**.
   - If speech fits within the timing window, export completes, and the dubbed video preview player renders with synchronized Khmer speech.
   - If speech is too long, the **Export Guard** prevents corruption, displaying the Timing Conflict alert with exact speedup needed and word trimming advice.
   - Click **"Download Dubbed Video (MP4)"** to download the final video file.
