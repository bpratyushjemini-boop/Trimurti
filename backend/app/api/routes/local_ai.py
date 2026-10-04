"""
NARAD V7.1 — Local AI Router.
Exposes status, local model inspection, on-device text generation, and local embeddings computation.
All endpoints run on local Mac hardware with zero cloud API keys.
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.local_ai.cache import hf_cache_manager

logger = logging.getLogger("narad.api.local_ai")

router = APIRouter(prefix="/local-ai", tags=["Local AI"])


class LocalGenerateRequest(BaseModel):
    prompt: str = Field(..., description="Prompt text for on-device inference")
    max_tokens: int = Field(default=128, ge=1, le=512)
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)


class LocalEmbeddingRequest(BaseModel):
    text: str = Field(..., description="Text to encode into dense vector embeddings")


@router.get("/status", status_code=status.HTTP_200_OK)
def get_local_ai_status():
    """
    Returns live on-device AI status:
    - LLM status (SmolLM2-135M on CPU/MPS, cache hit/miss, load ms, inference ms)
    - Hugging Face Hub cache directory and disk footprint
    - Knowledge Base local embedding provider status
    - Local vision provider interface status
    """
    is_cloud = (
        settings.is_cloud
        or getattr(settings, "NARAD_RUNTIME_MODE", "hybrid").lower() == "cloud"
    )
    if is_cloud:
        return {
            "llm": {
                "status": "UNAVAILABLE",
                "model": getattr(settings, "HUGGINGFACE_LOCAL_MODEL", "HuggingFaceTB/SmolLM2-135M-Instruct"),
                "device": "NONE",
                "mps_available": False,
                "is_loaded": False,
                "last_error": "Local AI is unavailable in CLOUD mode (Mac node offline)."
            },
            "cache": {
                "cache_dir": hf_cache_manager.get_cache_dir(),
                "models_cached": [],
            },
            "embeddings": {
                "active_provider": "huggingface",
                "provider_status": {"device": "NONE", "ready": False},
                "ready": False
            },
            "vision": {
                "provider": "huggingface_vision",
                "model": "HuggingFaceTB/SmolVLM-Instruct",
                "device": "NONE",
                "status": "UNAVAILABLE",
                "is_available": False
            },
        }

    from app.services.local_ai.manager import local_ai_manager
    from app.services.embeddings.manager import embedding_manager
    from app.services.vision.huggingface_vision import local_hf_vision_provider

    return {
        "llm": local_ai_manager.get_status_info(),
        "cache": {
            "cache_dir": hf_cache_manager.get_cache_dir(),
            "models_cached": hf_cache_manager.get_cached_models(),
        },
        "embeddings": embedding_manager.get_status(),
        "vision": local_hf_vision_provider.get_status(),
    }


@router.post("/generate", status_code=status.HTTP_200_OK)
def generate_local_response(payload: LocalGenerateRequest):
    """
    Executes local on-device generation with real latency measurements.
    """
    is_cloud = (
        settings.is_cloud
        or getattr(settings, "NARAD_RUNTIME_MODE", "hybrid").lower() == "cloud"
    )
    if is_cloud:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local AI generation is unavailable in CLOUD mode (Mac node offline)."
        )

    try:
        from app.services.local_ai.manager import local_ai_manager
        messages = [{"role": "user", "content": payload.prompt}]
        return local_ai_manager.generate(
            messages=messages,
            max_tokens=payload.max_tokens,
            temperature=payload.temperature
        )
    except Exception as e:
        logger.error("Local generation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Local generation failed: {str(e)}"
        ) from e


@router.post("/embeddings", status_code=status.HTTP_200_OK)
def compute_local_embeddings(payload: LocalEmbeddingRequest):
    """
    Computes dense vector embedding for input text using local Hugging Face model.
    """
    is_cloud = (
        settings.is_cloud
        or getattr(settings, "NARAD_RUNTIME_MODE", "hybrid").lower() == "cloud"
    )
    if is_cloud:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local embeddings computation is unavailable in CLOUD mode (Mac node offline)."
        )

    try:
        from app.services.embeddings.manager import embedding_manager
        vec = embedding_manager.embed_query(payload.text)
        if vec is None:
            raise RuntimeError("Embedding computation returned None.")
        return {
            "model": embedding_manager.active_provider.model_name,
            "dimension": len(vec),
            "vector_sample": vec[:8],
            "full_dimension": len(vec)
        }
    except Exception as e:
        logger.error("Local embedding computation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Local embedding computation failed: {str(e)}"
        ) from e


@router.post("/load", status_code=status.HTTP_200_OK)
def preload_local_model():
    """
    Pre-warms the local model into memory so subsequent requests incur zero cold-start delay.
    """
    is_cloud = (
        settings.is_cloud
        or getattr(settings, "NARAD_RUNTIME_MODE", "hybrid").lower() == "cloud"
    )
    if is_cloud:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local model pre-warming is unavailable in CLOUD mode (Mac node offline)."
        )

    from app.services.local_ai.manager import local_ai_manager
    success = local_ai_manager.load_model()
    if not success:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to load local model: {local_ai_manager._last_error}"
        )
    return {
        "status": "ready",
        "message": f"Model '{local_ai_manager.model_id}' successfully loaded in memory.",
        "telemetry": local_ai_manager.get_status_info()
    }
