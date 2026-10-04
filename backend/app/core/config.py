from typing import List
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from dotenv import load_dotenv
import os

# Calculate explicit directory paths independent of current working directory:
# backend/app/core/config.py -> core -> app -> backend
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_ENV_PATH = BACKEND_DIR / ".env"
VENV_ENV_PATH = BACKEND_DIR / ".venv" / ".env"
ROOT_ENV_PATH = BACKEND_DIR.parent / ".env"

# Prioritized explicit loading with python-dotenv
# 1. backend/.env (primary canonical location)
# 2. backend/.venv/.env (in case created inside venv)
# 3. project root .env (fallback)
env_sources = [BACKEND_ENV_PATH, VENV_ENV_PATH, ROOT_ENV_PATH]
loaded_file = None
for env_path in env_sources:
    if env_path.is_file():
        load_dotenv(dotenv_path=env_path, override=True)
        if not loaded_file:
            loaded_file = env_path

class Settings(BaseSettings):
    APP_NAME: str = "NARAD"
    APP_VERSION: str = "3.2.0"
    APP_ENV: str = "development"
    NARAD_ENV: str = "development"
    ENVIRONMENT: str = "LOCAL"  # LOCAL | CLOUD | SELF_HOSTED
    PUBLIC_BASE_URL: str = ""
    LOG_LEVEL: str = "INFO"
    NARAD_RUNTIME_MODE: str = "hybrid"  # local | cloud | hybrid
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    API_HOST: str = "127.0.0.1"
    OFFLINE_MODE: bool = False
    LOCAL_ONLY_MODE: bool = False
    RUNTIME_OPERATION_MODE: str = "AUTO"  # AUTO | LOCAL_ONLY | OFFLINE | CLOUD_PREFERRED

    # Database Configuration (SQLite local, PostgreSQL cloud)
    DATABASE_URL: str = "sqlite:///./narad.db"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30
    KNOWLEDGE_BASE_DIR: str = str(BACKEND_DIR / "data" / "knowledge_base")

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"]

    # Security & Protection for Cloud / Production
    NARAD_API_KEY: str = ""  # If set, enforces single-user Bearer/X-Narad-Key auth
    MAX_REQUEST_SIZE_BYTES: int = 15 * 1024 * 1024  # 15 MB limit
    RATE_LIMIT_PER_MINUTE: int = 120
    RATE_LIMIT_ENABLED: bool = True

    # AI Provider & Model Router Settings
    GROQ_API_KEY: str = ""
    NVIDIA_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    NARAD_DEFAULT_PROVIDER: str = "groq"
    NARAD_DEFAULT_MODEL: str = "openai/gpt-oss-120b"

    # Additional Connector Slots & OpenAI-Compatible Gateway Mesh
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_COMPATIBLE_BASE_URL: str = ""
    OPENAI_COMPATIBLE_API_KEY: str = ""
    OPENAI_COMPATIBLE_MODEL: str = ""
    OPENAI_COMPATIBLE_NAME: str = "OpenAI-Compatible Gateway"

    # Ollama Local Fast Model Settings
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3.5:0.8b"
    OLLAMA_TIMEOUT: float = 30.0
    OLLAMA_ENABLED: bool = True

    # Vāṇī Local TTS Engine Settings (Chatterbox Multilingual)
    TTS_PROVIDER: str = "chatterbox"
    TTS_LOCAL: bool = True
    TTS_DEVICE: str = "auto"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, v):
        if isinstance(v, str):
            v_clean = v.strip()
            # Render/Fly.io/Heroku provide postgres:// which SQLAlchemy 1.4+ requires as postgresql://
            if v_clean.startswith("postgres://"):
                return "postgresql://" + v_clean[len("postgres://"):]
            return v_clean
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    model_config = SettingsConfigDict(
        env_file=str(loaded_file) if loaded_file else str(BACKEND_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
