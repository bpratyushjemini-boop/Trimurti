"""
NARAD Phase 3 — Version 1 Master API Router.
Aggregates all mobile-facing endpoints under the /api/v1 namespace.
"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.runtime import router as runtime_router
from app.api.v1.memory import router as memory_router
from app.api.v1.voice import router as voice_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.nodes import router as nodes_router

v1_router = APIRouter()

v1_router.include_router(auth_router)
v1_router.include_router(chat_router)
v1_router.include_router(tasks_router)
v1_router.include_router(runtime_router)
v1_router.include_router(memory_router)
v1_router.include_router(voice_router)
v1_router.include_router(notifications_router)
v1_router.include_router(nodes_router)
