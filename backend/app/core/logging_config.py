"""
NARAD Phase 2.5 — Structured Observability & Telemetry Logging.
Provides structured telemetry logs for:
  - request
  - session
  - task
  - provider
  - model
  - latency
  - tool
  - error
  - completion
Scrubs all API keys, bearer tokens, and sensitive headers.
"""

import time
import json
import logging
import uuid
from typing import Optional, Dict, Any
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

from app.core.security import redact_sensitive_str

logger = logging.getLogger("narad.observability")


def log_telemetry_event(
    event_type: str,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    latency_ms: Optional[int] = None,
    tool: Optional[str] = None,
    error: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
):
    """Emit a structured observability event without leaking sensitive credentials."""
    payload: Dict[str, Any] = {
        "telemetry_event": event_type,
        "timestamp": time.time(),
    }
    if session_id:
        payload["session_id"] = session_id
    if task_id:
        payload["task_id"] = task_id
    if provider:
        payload["provider"] = provider
    if model:
        payload["model"] = model
    if latency_ms is not None:
        payload["latency_ms"] = latency_ms
    if tool:
        payload["tool"] = tool
    if error:
        payload["error"] = redact_sensitive_str(str(error))
    if extra:
        safe_extra = {}
        for k, v in extra.items():
            if any(s in k.lower() for s in ("key", "token", "password", "secret", "auth")):
                safe_extra[k] = "[REDACTED]"
            else:
                safe_extra[k] = redact_sensitive_str(str(v)) if isinstance(v, str) else v
        payload["extra"] = safe_extra

    logger.info(json.dumps(payload))


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Logs structured request completion telemetry for every incoming HTTP transaction."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"

        # Extract client IP safely
        client_ip = request.client.host if request.client else "unknown"

        # Read session/task query params if available
        session_id = request.query_params.get("session_id") or request.query_params.get("chat_id")
        task_id = request.query_params.get("task_id")

        try:
            response = await call_next(request)
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Avoid logging raw health checks every second in high-verbosity
            if request.url.path not in ("/health", "/ready"):
                log_telemetry_event(
                    event_type="request_completion",
                    session_id=session_id,
                    task_id=task_id,
                    latency_ms=duration_ms,
                    extra={
                        "request_id": req_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "client_ip": client_ip,
                    }
                )
            return response

        except Exception as exc:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            log_telemetry_event(
                event_type="request_error",
                session_id=session_id,
                task_id=task_id,
                latency_ms=duration_ms,
                error=str(exc),
                extra={
                    "request_id": req_id,
                    "method": request.method,
                    "path": request.url.path,
                    "client_ip": client_ip,
                }
            )
            raise exc
