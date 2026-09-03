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
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "127.0.0.1"

    # SQLite Database
    DATABASE_URL: str = "sqlite:///./narad.db"

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"]

    # AI Provider & Model Router Settings
    GEMINI_API_KEY: str = ""
    NARAD_DEFAULT_PROVIDER: str = "gemini"
    NARAD_DEFAULT_MODEL: str = "gemini-2.5-flash"

    # Future Connector Slots
    OPENROUTER_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

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
