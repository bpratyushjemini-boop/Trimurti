"""
NARAD FastAPI Main Application Entrypoint — Phase 2.5 Production Cloud & Local Architecture.
Prepares NARAD for standalone cloud deployment while fully preserving local Mac features.
"""

import uuid
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Dict, Any

from app.core.config import settings
from app.db.database import init_db, check_db_readiness, get_db_dialect
from app.core.security import SecurityMiddleware, global_exception_handler
from app.core.logging_config import StructuredLoggingMiddleware
from app.api.routes import (
    health,
    chats,
    messages,
    chat,
    knowledge,
    agent,
    tts,
    stt,
    voice,
    local_ai,
    runtime,
    memory,
    tasks,
    events,
    backup,
)
from app.api.v1 import v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database schema and perform migrations
    init_db()
    yield


app = FastAPI(
    title="NARAD API",
    description="Neural Assistant for Rizz & Absolute Destruction — TRIMURTI AI Ecosystem",
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# 1. Custom Global & Validation Exception Handlers for safe client responses
app.add_exception_handler(Exception, global_exception_handler)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    if request.url.path.startswith("/api/v1"):
        first_err = exc.errors()[0] if exc.errors() else {}
        loc = " -> ".join(str(l) for l in first_err.get("loc", []))
        msg = f"Validation failed at '{loc}': {first_err.get('msg', 'Invalid input')}"
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": msg,
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            },
        )
    from fastapi.exception_handlers import request_validation_exception_handler
    return await request_validation_exception_handler(request, exc)

# 2. Production Security & Observability Middlewares
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(SecurityMiddleware)

# 3. CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Register Subsystem API Routers (Internal / Phase 2 HUD)
app.include_router(health.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(chats.router, prefix="/api")
app.include_router(messages.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
app.include_router(agent.router, prefix="/api")
app.include_router(tts.router, prefix="/api")
app.include_router(stt.router, prefix="/api")
app.include_router(voice.router, prefix="/api")
app.include_router(local_ai.router, prefix="/api")
app.include_router(runtime.router, prefix="/api")
app.include_router(memory.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(backup.router, prefix="/api")

# 5. Register Mobile-Facing Version 1 API
app.include_router(v1_router, prefix="/api/v1")


# 5. Cloud Platform Health, Readiness, and Version Probes
@app.get("/health", tags=["Cloud Probe"])
def root_health():
    """Root health probe for cloud platform load balancers (Render, Fly.io, Railway, Kubernetes)."""
    ok, db_status = check_db_readiness()
    return {
        "status": "online" if ok else "degraded",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": db_status,
        "dialect": get_db_dialect(),
    }


@app.get("/ready", tags=["Cloud Probe"])
@app.get("/api/ready", tags=["Cloud Probe"])
def readiness_probe(response: Response) -> Dict[str, Any]:
    """Readiness probe verifying database connectivity and core model routing readiness."""
    db_ok, db_status = check_db_readiness()
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "ready": False,
            "database": db_status,
            "detail": "Database is unreachable",
        }
    return {
        "status": "ready",
        "ready": True,
        "app": settings.APP_NAME,
        "database": db_status,
        "dialect": get_db_dialect(),
        "environment": settings.APP_ENV,
        "runtime_mode": settings.NARAD_RUNTIME_MODE,
    }


@app.get("/version", tags=["Cloud Probe"])
@app.get("/api/version", tags=["Cloud Probe"])
def version_probe():
    """Version metadata endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "phase": "2.5 Production Backend",
        "environment": settings.APP_ENV,
        "runtime_mode": settings.NARAD_RUNTIME_MODE,
        "database_dialect": get_db_dialect(),
    }


@app.get("/")
def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "online",
        "runtime_mode": settings.NARAD_RUNTIME_MODE,
        "documentation": "/docs",
        "health": "/health",
        "ready": "/ready",
        "version_info": "/version",
        "truth": "/api/runtime/truth",
    }
