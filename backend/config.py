"""
Configuration compatibility shim forwarding to app.core.config.
Ensures imports of `config` or `backend.config` resolve identically.
"""
from app.core.config import settings, BACKEND_DIR, BACKEND_ENV_PATH

__all__ = ["settings", "BACKEND_DIR", "BACKEND_ENV_PATH"]
