from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.config import settings
from app.db.database import init_db
from app.api.routes import health, chats, messages

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database schema
    init_db()
    yield

app = FastAPI(
    title="NARAD API",
    description="Networked Agent for Retrieval, Analysis & Dissemination - TRIMURTI AI Ecosystem",
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# Setup CORS for frontend desktop client
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(health.router, prefix="/api")
app.include_router(chats.router, prefix="/api")
app.include_router(messages.router, prefix="/api")

@app.get("/")
def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "online",
        "documentation": "/docs"
    }
