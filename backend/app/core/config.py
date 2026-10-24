from pathlib import Path
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json


class Settings(BaseSettings):
    # App
    APP_NAME: str = "KhmerDub AI"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Server
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    FRONTEND_PORT: int = 5173

    # CORS
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["*"]

    # Storage Paths
    DATA_DIR: Path = Path("/app/data")
    UPLOADS_DIR: Path = Path("/app/data/uploads")
    OUTPUTS_DIR: Path = Path("/app/data/outputs")
    TEMP_DIR: Path = Path("/app/data/temp")

    # Database
    DATABASE_URL: str = "sqlite:////app/data/khmerdub.db"

    # AI & Audio Cache
    MODEL_CACHE_DIR: Path = Path("/root/.cache")
    WHISPER_MODEL: str = "base"
    WHISPER_MODEL_SIZE: str = "base"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_LANGUAGE: str = "en"
    WHISPER_VAD_FILTER: bool = True

    # Translation (NLLB-200)
    TRANSLATION_PROVIDER: str = "nllb"
    TRANSLATION_MODEL: str = "facebook/nllb-200-distilled-600M"
    TRANSLATION_SOURCE_LANG: str = "eng_Latn"
    TRANSLATION_TARGET_LANG: str = "khm_Khmr"
    TRANSLATION_DEVICE: str = "cpu"
    TRANSLATION_BATCH_SIZE: int = 1
    TRANSLATION_MAX_INPUT_TOKENS: int = 512

    # Limits
    MAX_UPLOAD_SIZE_MB: int = 500

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
