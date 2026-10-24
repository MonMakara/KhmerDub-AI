import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any

from cryptography.fernet import Fernet

from app.core.config import settings

logger = logging.getLogger(__name__)

SECRETS_DIR = Path(getattr(settings, "DATA_DIR", "/app/data")) / ".secrets"
KEY_FILE = SECRETS_DIR / ".fernet_key"
CREDENTIALS_FILE = SECRETS_DIR / "credentials.enc"

ENV_VAR_MAPPING = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "custom": "CUSTOM_AI_API_KEY",
}


def _get_or_create_cipher() -> Fernet:
    """Retrieve or initialize encryption key for credential storage."""
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    if not KEY_FILE.exists():
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
        try:
            KEY_FILE.chmod(0o600)
        except OSError:
            pass
    else:
        key = KEY_FILE.read_bytes().strip()
    return Fernet(key)


def _load_stored_credentials() -> Dict[str, Any]:
    """Load and decrypt saved credentials dictionary."""
    if not CREDENTIALS_FILE.exists() or CREDENTIALS_FILE.stat().st_size == 0:
        return {}
    try:
        cipher = _get_or_create_cipher()
        encrypted_data = CREDENTIALS_FILE.read_bytes()
        decrypted_json = cipher.decrypt(encrypted_data).decode("utf-8")
        return json.loads(decrypted_json)
    except Exception as e:
        logger.warning("Could not decrypt stored credentials file: %s", e)
        return {}


def _save_stored_credentials(data: Dict[str, Any]) -> None:
    """Encrypt and write credentials dictionary to disk."""
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    cipher = _get_or_create_cipher()
    encrypted_data = cipher.encrypt(json.dumps(data).encode("utf-8"))
    CREDENTIALS_FILE.write_bytes(encrypted_data)
    try:
        CREDENTIALS_FILE.chmod(0o600)
    except OSError:
        pass


def get_api_key(provider: str) -> Optional[str]:
    """Retrieve plaintext API key for a provider from env vars or encrypted store.

    NEVER log or return this value to API clients.
    """
    p_norm = (provider or "").strip().lower()

    # 1. Check environment variable first
    env_var = ENV_VAR_MAPPING.get(p_norm)
    if env_var:
        env_val = os.getenv(env_var) or getattr(settings, env_var, None)
        if env_val and env_val.strip():
            return env_val.strip()

    # 2. Check encrypted store
    creds = _load_stored_credentials()
    val = creds.get(p_norm)
    if isinstance(val, dict):
        return val.get("api_key")
    if isinstance(val, str) and val.strip():
        return val.strip()

    return None


def get_provider_credentials(provider: str) -> Dict[str, Any]:
    """Retrieve configuration dictionary for a provider (api_key, base_url, model)."""
    p_norm = (provider or "").strip().lower()
    creds = _load_stored_credentials()
    stored = creds.get(p_norm, {})
    if isinstance(stored, str):
        stored = {"api_key": stored}
    elif not isinstance(stored, dict):
        stored = {}

    api_key = get_api_key(p_norm)
    base_url = (
        os.getenv(f"{p_norm.upper()}_BASE_URL")
        or getattr(settings, f"{p_norm.upper()}_BASE_URL", None)
        or stored.get("base_url")
    )
    model = (
        os.getenv(f"{p_norm.upper()}_MODEL")
        or getattr(settings, f"{p_norm.upper()}_MODEL", None)
        or stored.get("model")
    )

    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
    }


def save_api_key(
    provider: str,
    api_key: str,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> None:
    """Securely encrypt and store an API key and optional configuration."""
    p_norm = (provider or "").strip().lower()
    clean_key = (api_key or "").strip()
    if not clean_key:
        remove_api_key(p_norm)
        return

    creds = _load_stored_credentials()
    existing = creds.get(p_norm)
    if isinstance(existing, dict):
        record = dict(existing)
        record["api_key"] = clean_key
        if base_url is not None:
            record["base_url"] = base_url.strip() if base_url else None
        if model is not None:
            record["model"] = model.strip() if model else None
        creds[p_norm] = record
    elif base_url or model:
        creds[p_norm] = {
            "api_key": clean_key,
            "base_url": base_url.strip() if base_url else None,
            "model": model.strip() if model else None,
        }
    else:
        creds[p_norm] = clean_key

    _save_stored_credentials(creds)
    logger.info("Saved encrypted credentials for provider '%s'", p_norm)


def remove_api_key(provider: str) -> bool:
    """Remove stored API key for a provider."""
    p_norm = (provider or "").strip().lower()
    creds = _load_stored_credentials()
    if p_norm in creds:
        del creds[p_norm]
        _save_stored_credentials(creds)
        logger.info("Removed stored API key for provider '%s'", p_norm)
        return True
    return False


def is_api_key_configured(provider: str) -> bool:
    """Check whether an API key is available for a provider."""
    key = get_api_key(provider)
    return bool(key and len(key) > 5)


def get_masked_api_key(provider: str) -> Optional[str]:
    """Return a masked representation of the API key for safe UI display (e.g. 'AIzaSy...4aB8')."""
    key = get_api_key(provider)
    if not key:
        return None
    if len(key) <= 8:
        return "••••••••"
    return f"{key[:6]}...{key[-4:]}"
