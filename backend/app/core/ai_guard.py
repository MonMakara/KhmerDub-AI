import logging
import os
import threading
from contextlib import contextmanager
from typing import List, Optional

logger = logging.getLogger(__name__)

# Configurable concurrency limit for AI models.
# Default concurrency of 2 enables parallel execution (e.g. Whisper transcription + Music separation)
# while staying safely within host memory limits (RTX 4060 8GB VRAM + 14GB RAM).
_DEFAULT_CONCURRENCY = int(os.environ.get("MAX_CONCURRENT_AI_TASKS", "2"))
_AI_INFERENCE_SEMAPHORE = threading.Semaphore(_DEFAULT_CONCURRENCY)
_active_model_lock = threading.Lock()
_active_models: List[str] = []


@contextmanager
def acquire_ai_inference_slot(model_name: str, timeout: Optional[float] = 300.0):
    """Context manager that acquires an AI inference slot.
    
    Allows up to MAX_CONCURRENT_AI_TASKS (default 2) heavy AI models to execute concurrently.
    Tasks queue gracefully with timeout if all slots are saturated.
    """
    acquired = _AI_INFERENCE_SEMAPHORE.acquire(timeout=timeout)
    if not acquired:
        with _active_model_lock:
            active_desc = ", ".join(_active_models) if _active_models else "unknown"
        raise TimeoutError(
            f"Timed out after {timeout}s waiting for AI inference slot for '{model_name}'. "
            f"Currently active model(s): '{active_desc}'."
        )

    with _active_model_lock:
        _active_models.append(model_name)

    logger.info("Acquired AI inference slot for '%s' (active: %d)", model_name, len(_active_models))
    try:
        yield
    finally:
        with _active_model_lock:
            if model_name in _active_models:
                _active_models.remove(model_name)
        _AI_INFERENCE_SEMAPHORE.release()
        logger.info("Released AI inference slot for '%s'", model_name)


def get_active_ai_model() -> Optional[str]:
    """Return the name of the AI model currently executing inference, or None."""
    with _active_model_lock:
        return _active_models[0] if _active_models else None


def get_active_ai_models() -> List[str]:
    """Return list of all AI models currently executing inference."""
    with _active_model_lock:
        return list(_active_models)
