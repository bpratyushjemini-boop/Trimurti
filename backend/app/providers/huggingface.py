"""
NARAD V7.1 — Hugging Face Local AI Provider.
Integrates local on-device Hugging Face models into the unified BaseLLMProvider interface.
Does not replace existing cloud providers; provides an offline, privacy-first local option.
"""

import time
import asyncio
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator

from app.providers.base import BaseLLMProvider
from app.core.config import settings

logger = logging.getLogger("narad.providers.huggingface")


class LocalHuggingFaceProvider(BaseLLMProvider):
    """
    On-device Hugging Face LLM Provider for NARAD.
    Provides zero-cost, local offline inference with real execution telemetry.
    """

    def __init__(self, model_name: Optional[str] = None):
        super().__init__()
        self._model_name = model_name or getattr(
            settings, "HUGGINGFACE_LOCAL_MODEL", "HuggingFaceTB/SmolLM2-135M-Instruct"
        )

    @property
    def provider_id(self) -> str:
        return "huggingface"

    @property
    def display_name(self) -> str:
        return "Hugging Face (Local)"

    def is_configured(self) -> bool:
        """Returns True if local Hugging Face subsystem is enabled and available in this environment."""
        if settings.is_cloud:
            return False
        if getattr(settings, "NARAD_RUNTIME_MODE", "hybrid").lower() == "cloud":
            return False
        if not getattr(settings, "HUGGINGFACE_LOCAL_ENABLED", True):
            return False
        try:
            from app.services.local_ai.manager import is_torch_available
            return is_torch_available()
        except ImportError:
            return False

    def get_available_models(self) -> List[str]:
        return [self._model_name]

    def supports_tools(self) -> bool:
        # Lightweight local models are optimized for text generation, not function calling
        return False

    def supports_streaming(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return False

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 256,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate response locally via local_ai_manager."""
        if not self.is_configured():
            return {
                "content": "⚠️ Hugging Face Local AI is unavailable in CLOUD mode or when PyTorch is not installed.",
                "provider": self.provider_id,
                "model": model or self._model_name,
                "latency_ms": 0,
                "status": "not_configured"
            }

        t_start = time.perf_counter()
        try:
            from app.services.local_ai.manager import local_ai_manager
            # Run CPU inference in threadpool so as not to block FastAPI event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: local_ai_manager.generate(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs
                )
            )
            latency_ms = int((time.perf_counter() - t_start) * 1000)
            self.record_success(latency_ms)
            result["latency_ms"] = latency_ms
            return result

        except Exception as e:
            latency_ms = int((time.perf_counter() - t_start) * 1000)
            self.record_failure(str(e), is_transient=True, cooldown_seconds=15.0)
            logger.error("Local Hugging Face generation error: %s", e)
            raise

    async def stream_response(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 256,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream locally generated response."""
        res = await self.generate_response(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        content = res.get("content", "")
        # Stream out words with brief conversational cadence
        words = content.split(" ")
        for i, word in enumerate(words):
            chunk = word if i == len(words) - 1 else word + " "
            yield chunk
            await asyncio.sleep(0.015)
