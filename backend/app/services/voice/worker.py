"""
KhmerDub AI — VoxCPM2 Local GPU Inference Worker
Dedicated FastAPI micro-service running on host in isolated Conda environment ('voxcpm-bench')
providing reference-conditioned Khmer voice cloning on the NVIDIA RTX 4060 GPU.
"""

import asyncio
import gc
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

import psutil
import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [VoxCPM-Worker] %(message)s",
)
logger = logging.getLogger("voxcpm_worker")

# Workspace and storage boundaries
WORKSPACE_ROOT = Path("/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI").resolve()
DATA_DIR = (WORKSPACE_ROOT / "data").resolve()
MODEL_DIR = (DATA_DIR / "model_cache" / "voxcpm2").resolve()
DEFAULT_SECRET = "khmerdub-voxcpm-internal-auth-token-2026"
INTERNAL_SECRET = os.environ.get("VOXCPM_INTERNAL_SECRET", DEFAULT_SECRET)

# Global model state & concurrency lock
_model = None
_model_lock = asyncio.Lock()
_load_lock = asyncio.Lock()
_is_busy = False

app = FastAPI(
    title="KhmerDub AI VoxCPM2 Inference Worker",
    version="1.0.0",
    docs_url="/docs",
)


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="Khmer Unicode text")
    reference_audio_path: str = Field(..., description="Container or host path to reference WAV")
    output_audio_path: Optional[str] = Field(None, description="Optional container or host destination path")
    cfg_value: float = Field(2.0, ge=1.0, le=5.0)
    inference_timesteps: int = Field(10, ge=5, le=50)


class SynthesizeResponse(BaseModel):
    success: bool
    duration_seconds: float
    sample_rate: int
    generation_time_s: float
    output_audio_path: str
    peak_vram_gb: float


def resolve_path(path_str: str) -> Path:
    """Safely map container paths (/app/data/...) and relative paths to host workspace."""
    if not path_str or not path_str.strip():
        raise HTTPException(status_code=400, detail="Empty path specified")

    clean_str = path_str.strip()
    if clean_str.startswith("/app/data/"):
        rel = clean_str[len("/app/data/") :]
        resolved = (DATA_DIR / rel).resolve()
    elif clean_str.startswith("/app/"):
        rel = clean_str[len("/app/") :]
        resolved = (WORKSPACE_ROOT / rel).resolve()
    else:
        p = Path(clean_str)
        if not p.is_absolute():
            resolved = (DATA_DIR / p).resolve()
        else:
            resolved = p.resolve()

    # Security boundary check: ensure resolved path is within workspace
    try:
        resolved.relative_to(WORKSPACE_ROOT)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: path '{clean_str}' is outside allowed workspace boundaries.",
        )

    return resolved


def verify_internal_auth(x_internal_token: Optional[str] = Header(None)):
    """Enforce shared internal authentication token."""
    if not x_internal_token or x_internal_token != INTERNAL_SECRET:
        logger.warning("Unauthorized inference worker request received.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Internal-Token.",
        )


def get_vram_info():
    """Retrieve GPU memory statistics."""
    if torch.cuda.is_available():
        free_b, tot_b = torch.cuda.mem_get_info(0)
        return {
            "gpu_name": torch.cuda.get_device_name(0),
            "vram_total_gb": round(tot_b / (1024**3), 3),
            "vram_free_gb": round(free_b / (1024**3), 3),
            "vram_used_gb": round((tot_b - free_b) / (1024**3), 3),
            "process_vram_allocated_gb": round(torch.cuda.memory_allocated(0) / (1024**3), 3),
        }
    return {
        "gpu_name": "N/A",
        "vram_total_gb": 0.0,
        "vram_free_gb": 0.0,
        "vram_used_gb": 0.0,
        "process_vram_allocated_gb": 0.0,
    }


async def get_or_load_model():
    """Lazily load the VoxCPM2 checkpoint into GPU VRAM with safety checks."""
    global _model
    if _model is not None:
        return _model

    async with _load_lock:
        if _model is not None:
            return _model

        if not torch.cuda.is_available():
            raise HTTPException(
                status_code=503,
                detail="CUDA is not available on worker host. Cannot load VoxCPM2.",
            )

        vram = get_vram_info()
        logger.info("VRAM before model load: Free: %s GB / Total: %s GB", vram["vram_free_gb"], vram["vram_total_gb"])
        if vram["vram_free_gb"] < 4.0:
            raise HTTPException(
                status_code=507,
                detail=f"Insufficient free VRAM ({vram['vram_free_gb']} GB < 4.0 GB requirement) to load VoxCPM2 model.",
            )

        logger.info("Loading official VoxCPM2 model from %s on CUDA...", MODEL_DIR)
        t_start = time.time()
        try:
            from voxcpm import VoxCPM

            # Run loading in threadpool to keep event loop responsive
            def _load():
                return VoxCPM.from_pretrained(
                    str(MODEL_DIR),
                    device="cuda",
                    load_denoiser=False,
                    optimize=False,
                )

            _model = await asyncio.to_thread(_load)
            elapsed = round(time.time() - t_start, 2)
            post_vram = get_vram_info()
            logger.info("VoxCPM2 loaded successfully in %ss. Process VRAM: %s GB", elapsed, post_vram["process_vram_allocated_gb"])
            return _model
        except Exception as e:
            logger.exception("Failed to load VoxCPM2 model: %s", e)
            _model = None
            torch.cuda.empty_cache()
            gc.collect()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load VoxCPM2 model checkpoint: {e}",
            )


@app.get("/health")
async def health_check():
    """Health check endpoint exposing hardware status and model availability."""
    global _model, _is_busy
    vram = get_vram_info()
    vm = psutil.virtual_memory()

    return {
        "status": "online",
        "worker_version": "1.0.0",
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "gpu_name": vram["gpu_name"],
        "vram_total_gb": vram["vram_total_gb"],
        "vram_free_gb": vram["vram_free_gb"],
        "vram_used_gb": vram["vram_used_gb"],
        "process_vram_allocated_gb": vram["process_vram_allocated_gb"],
        "ram_available_gb": round(vm.available / (1024**3), 2),
        "model_loaded": _model is not None,
        "busy": _is_busy,
    }


@app.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_khmer_speech(
    payload: SynthesizeRequest,
    x_internal_token: Optional[str] = Header(None),
):
    """Synthesize Khmer speech conditioned on authorized reference audio."""
    verify_internal_auth(x_internal_token)
    global _model, _is_busy

    clean_text = payload.text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Cannot synthesize empty text.")

    # Resolve and validate reference audio path
    ref_host_path = resolve_path(payload.reference_audio_path)
    if not ref_host_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Reference audio file does not exist at {ref_host_path}",
        )
    if ref_host_path.stat().st_size < 44:
        raise HTTPException(
            status_code=400,
            detail=f"Reference audio file is invalid or empty at {ref_host_path}",
        )

    # Determine output destination path
    if payload.output_audio_path:
        out_host_path = resolve_path(payload.output_audio_path)
    else:
        # Default fallback to temp dir
        temp_dir = DATA_DIR / "temp" / "voxcpm_worker"
        temp_dir.mkdir(parents=True, exist_ok=True)
        out_host_path = temp_dir / f"cloned_{int(time.time()*1000)}.wav"

    out_host_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure model is ready
    model = await get_or_load_model()

    # Hardware safety threshold check
    vram_cur = get_vram_info()
    if vram_cur["vram_free_gb"] < 0.8:
        torch.cuda.empty_cache()
        gc.collect()
        vram_after = get_vram_info()
        if vram_after["vram_free_gb"] < 0.8:
            raise HTTPException(
                status_code=507,
                detail=f"GPU free VRAM too low ({vram_after['vram_free_gb']} GB < 0.8 GB). Cannot safely execute inference.",
            )

    # Single-concurrency inference execution
    async with _model_lock:
        _is_busy = True
        try:
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.reset_peak_memory_stats()
            t_gen_start = time.time()

            logger.info("Starting synthesis: '%s' (ref: %s)", clean_text[:40], ref_host_path.name)

            def _run_inference():
                return model.generate(
                    text=clean_text,
                    reference_wav_path=str(ref_host_path),
                    cfg_value=payload.cfg_value,
                    inference_timesteps=payload.inference_timesteps,
                    normalize=False,
                )

            wav = await asyncio.to_thread(_run_inference)
            gen_time = round(time.time() - t_gen_start, 3)

            # Write standard 48 kHz studio mono 16-bit PCM WAV
            sample_rate = 48000
            sf.write(str(out_host_path), wav, sample_rate, subtype="PCM_16")

            # Verify generated file
            data, sr = sf.read(str(out_host_path))
            duration = round(len(data) / sr, 3)
            peak_vram = round(torch.cuda.max_memory_allocated(0) / (1024**3), 3)

            logger.info(
                "Synthesis successful: %s (%ss audio in %ss | Peak VRAM: %s GB)",
                out_host_path.name,
                duration,
                gen_time,
                peak_vram,
            )

            return SynthesizeResponse(
                success=True,
                duration_seconds=duration,
                sample_rate=sr,
                generation_time_s=gen_time,
                output_audio_path=payload.output_audio_path or str(out_host_path),
                peak_vram_gb=peak_vram,
            )

        except torch.cuda.OutOfMemoryError as oom:
            logger.error("CUDA Out of Memory during VoxCPM2 synthesis: %s", oom)
            torch.cuda.empty_cache()
            gc.collect()
            raise HTTPException(
                status_code=507,
                detail="GPU Out of Memory during Khmer voice cloning. Please retry or switch to Edge/Google TTS.",
            )
        except Exception as e:
            logger.exception("Synthesis failed: %s", e)
            raise HTTPException(
                status_code=500,
                detail=f"VoxCPM2 speech synthesis error: {e}",
            )
        finally:
            _is_busy = False
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()


@app.post("/release_memory")
async def release_gpu_memory(
    unload_model: bool = False,
    x_internal_token: Optional[str] = Header(None),
):
    """Clear CUDA cache and optionally unload the VoxCPM2 checkpoint from VRAM."""
    verify_internal_auth(x_internal_token)
    global _model

    async with _model_lock:
        if unload_model:
            logger.info("Unloading VoxCPM2 model from VRAM...")
            _model = None

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    vram = get_vram_info()
    logger.info("Memory released. Model loaded: %s | Free VRAM: %s GB", _model is not None, vram["vram_free_gb"])
    return {
        "success": True,
        "model_loaded": _model is not None,
        "vram_free_gb": vram["vram_free_gb"],
    }


if __name__ == "__main__":
    port = int(os.environ.get("VOXCPM_PORT", 8002))
    host = os.environ.get("VOXCPM_HOST", "0.0.0.0")
    logger.info("Starting VoxCPM2 Inference Worker on %s:%s...", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
