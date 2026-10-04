"""
NARAD Phase 2.5 — Production Security & Protection Layer.
Provides:
  - Single-user API Key / Bearer authentication boundary
  - Sliding-window in-memory rate limiting with Retry-After
  - Request body size limits (default 15MB)
  - Safe error responses (no stack trace exposure)
  - Secret redaction for logs and telemetry
"""

import time
import re
import uuid
import logging
from typing import Dict, Tuple, Optional, Set
from collections import defaultdict
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger("narad.security")

# Endpoints exempt from authentication
PUBLIC_PATHS: Set[str] = {
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    "/api/health",
    "/ready",
    "/api/ready",
    "/version",
    "/api/version",
    "/api/v1/auth/verify",
    "/api/v1/runtime/status",
}

# Regex patterns for redacting API keys
SECRET_PATTERNS = [
    re.compile(r"gsk_[a-zA-Z0-9_-]{20,}", re.IGNORECASE),          # Groq
    re.compile(r"nvapi-[a-zA-Z0-9_-]{20,}", re.IGNORECASE),         # NVIDIA
    re.compile(r"AIzaSy[a-zA-Z0-9_-]{20,}", re.IGNORECASE),        # Gemini
    re.compile(r"sk-or-v1-[a-zA-Z0-9_-]{20,}", re.IGNORECASE),     # OpenRouter
    re.compile(r"sk-[a-zA-Z0-9_-]{20,}", re.IGNORECASE),           # OpenAI
]


def redact_sensitive_str(text: str) -> str:
    """Mask known API key patterns within strings."""
    if not isinstance(text, str):
        return text
    redacted = text
    for pat in SECRET_PATTERNS:
        redacted = pat.sub("[REDACTED_API_KEY]", redacted)
    return redacted


class InvertedTokenBucketRateLimiter:
    """
    Sliding window in-memory rate limiter per client IP or key.
    Tracks requests per 60-second window.
    """

    def __init__(self, limit_per_minute: int = 120):
        self._limit = limit_per_minute
        self._history: Dict[str, list] = defaultdict(list)

    def is_allowed(self, identifier: str) -> Tuple[bool, int]:
        now = time.time()
        window_start = now - 60.0
        # Clean older entries
        self._history[identifier] = [t for t in self._history[identifier] if t > window_start]

        if len(self._history[identifier]) >= self._limit:
            oldest = self._history[identifier][0]
            retry_after = max(1, int(oldest + 60.0 - now))
            return False, retry_after

        self._history[identifier].append(now)
        return True, 0

    def reset(self):
        """Reset all rate limit tracking."""
        self._history.clear()


rate_limiter = InvertedTokenBucketRateLimiter(
    limit_per_minute=getattr(settings, "RATE_LIMIT_PER_MINUTE", 120)
)


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive Security Middleware for NARAD:
      1. Enforces single-user auth if NARAD_API_KEY is configured.
      2. Validates request body size limit.
      3. Applies sliding-window rate limiting.
      4. Injects request-id for trace isolation.
    """

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        path = request.url.path

        # 1. Path exemption check
        is_public = path in PUBLIC_PATHS or path.rstrip("/") in PUBLIC_PATHS

        # 2. Single-user Auth Boundary
        api_key = getattr(settings, "NARAD_API_KEY", "")
        if api_key and api_key.strip() and not is_public:
            # Check Bearer token or X-Narad-Key header
            auth_header = request.headers.get("Authorization", "")
            key_header = request.headers.get("X-Narad-Key", "")
            provided_token = ""
            if auth_header.startswith("Bearer "):
                provided_token = auth_header[len("Bearer "):].strip()
            elif key_header:
                provided_token = key_header.strip()

            if provided_token != api_key:
                logger.warning(f"[Security] Unauthorized access attempt to {path} from {request.client.host if request.client else 'unknown'}")
                if path.startswith("/api/v1"):
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={
                            "error": {
                                "code": "AUTH_REQUIRED",
                                "message": "Invalid or missing NARAD API key. Provide via 'Authorization: Bearer <key>' or 'X-Narad-Key'.",
                                "request_id": req_id,
                                "task_id": None,
                                "retryable": False,
                                "provider": None,
                            }
                        },
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        "error": "Unauthorized",
                        "error_code": "AUTH_REQUIRED",
                        "detail": "Invalid or missing NARAD API key. Provide via 'Authorization: Bearer <key>' or 'X-Narad-Key'.",
                        "request_id": req_id
                    },
                    headers={"WWW-Authenticate": "Bearer"}
                )

        # 3. Request Size Limit Protection
        content_length = request.headers.get("Content-Length")
        max_size = getattr(settings, "MAX_REQUEST_SIZE_BYTES", 15 * 1024 * 1024)
        if content_length:
            try:
                cl_int = int(content_length)
                if cl_int > max_size:
                    logger.warning(f"[Security] Request payload too large ({cl_int} bytes) on {path}")
                    if path.startswith("/api/v1"):
                        return JSONResponse(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            content={
                                "error": {
                                    "code": "PAYLOAD_TOO_LARGE",
                                    "message": f"Request payload exceeds the maximum allowed size of {max_size // (1024 * 1024)}MB.",
                                    "request_id": req_id,
                                    "task_id": None,
                                    "retryable": False,
                                    "provider": None,
                                }
                            }
                        )
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={
                            "error": "Payload Too Large",
                            "error_code": "PAYLOAD_TOO_LARGE",
                            "detail": f"Request payload exceeds the maximum allowed size of {max_size // (1024 * 1024)}MB.",
                            "request_id": req_id
                        }
                    )
            except ValueError:
                pass

        # 4. In-memory Rate Limiting
        if getattr(settings, "RATE_LIMIT_ENABLED", True) and not is_public:
            client_ip = request.client.host if request.client else "127.0.0.1"
            allowed, retry_after = rate_limiter.is_allowed(client_ip)
            if not allowed:
                logger.warning(f"[Security] Rate limit exceeded for {client_ip} on {path}")
                if path.startswith("/api/v1"):
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={
                            "error": {
                                "code": "RATE_LIMITED",
                                "message": f"Rate limit exceeded. Please retry in {retry_after} seconds.",
                                "request_id": req_id,
                                "task_id": None,
                                "retryable": True,
                                "provider": None,
                            }
                        },
                        headers={"Retry-After": str(retry_after)}
                    )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "Too Many Requests",
                        "error_code": "RATE_LIMITED",
                        "detail": f"Rate limit exceeded. Please retry in {retry_after} seconds.",
                        "request_id": req_id,
                        "retry_after": retry_after
                    },
                    headers={"Retry-After": str(retry_after)}
                )

        # Proceed with request
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


async def global_exception_handler(request: Request, exc: Exception):
    """
    Catches all unhandled exceptions.
    Logs full traceback internally but masks internal paths, stack traces,
    and server architecture from external clients.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    logger.error(f"[UnhandledException] Request {req_id} ({request.method} {request.url.path}) failed: {exc}", exc_info=True)

    if request.url.path.startswith("/api/v1"):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An internal server error occurred. Please refer to system logs with request ID.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "error_code": "INTERNAL_SERVER_ERROR",
            "detail": "An internal server error occurred. Please refer to system logs with request ID.",
            "request_id": req_id
        }
    )
