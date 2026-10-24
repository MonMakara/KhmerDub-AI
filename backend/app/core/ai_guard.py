import logging
import threading
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

# Shared concurrency limit for memory-intensive AI models (Whisper + NLLB).
# Default concurrency of 1 ensures that heavy model inference tasks queue cleanly
# rather than running concurrently and exhausting system RAM on a 16 GB host.
_AI_INFERENCE_SEMAPHORE = threading.Semaphore(1)
_active_model_lock = threading.Lock()
_active_model_name: Optional[str] = None


@contextmanager
def acquire_ai_inference_slot(model_name: str, timeout: Optional[float] = 300.0):
    """Context manager that acquires the global AI inference slot.
    
    Ensures that only one heavy AI model (faster-whisper or NLLB-200) executes
    inference on the CPU/GPU at any given moment, avoiding memory spikes.
    """
    global _active_model_name
    acquired = _AI_INFERENCE_SEMAPHORE.acquire(timeout=timeout)
    if not acquired:
        raise TimeoutError(
            f"Timed out after {timeout}s waiting for AI inference slot for '{model_name}'. "
            f"Currently active model: '{_active_model_name}'."
        )

    with _active_model_lock:
        _active_model_name = model_name

    logger.info("Acquired AI inference slot for '%s'", model_name)
    try:
        yield
    finally:
        with _active_model_lock:
            _active_model_name = None
        _AI_INFERENCE_SEMAPHORE.release()
        logger.info("Released AI inference slot for '%s'", model_name)


def get_active_ai_model() -> Optional[str]:
    """Return the name of the AI model currently executing inference, or None."""
    with _active_model_lock:
        return _active_model_name
