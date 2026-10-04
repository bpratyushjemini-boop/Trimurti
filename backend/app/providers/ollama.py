"""
NARAD V7.2 — Native Ollama Local Fast Model Provider.
Provides ultra-fast on-device inference using Ollama daemon (e.g. qwen3.5:0.8b).
Dedicated for lightweight tasks (intent classification, extraction, formatting, fast Q&A).
Integrates seamlessly into the BaseLLMProvider health, latency, and failover architecture.
"""

import time
import json
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
import httpx

from app.providers.base import (
    BaseLLMProvider,
    HEALTH_AVAILABLE,
    HEALTH_UNAVAILABLE,
    HEALTH_NOT_CONFIGURED,
)
from app.core.config import settings

logger = logging.getLogger("narad.providers.ollama")


class OllamaProvider(BaseLLMProvider):
    """
    Native Ollama Local Fast Provider for NARAD.
    Directly communicates with the local Ollama daemon over HTTP REST.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        super().__init__()
        self._base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self._model = model or settings.OLLAMA_MODEL
        self._timeout = timeout or settings.OLLAMA_TIMEOUT
        self._cached_liveness: Optional[bool] = None
        self._last_liveness_check: float = 0.0
        self._cached_installed_models: List[str] = []

    @property
    def provider_id(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return "Ollama (Local Fast)"

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def default_model(self) -> str:
        return self._model

    def is_configured(self) -> bool:
        """
        Returns True if Ollama is enabled and the daemon is reachable.
        Caches daemon liveness check for 5 seconds to prevent network thrashing.
        """
        if settings.is_cloud:
            return False
        if getattr(settings, "NARAD_RUNTIME_MODE", "hybrid").lower() == "cloud":
            return False
        if not getattr(settings, "OLLAMA_ENABLED", True):
            return False

        now = time.time()
        if self._cached_liveness is not None and (now - self._last_liveness_check) < 5.0:
            return self._cached_liveness

        # Perform quick synchronous liveness check with short timeout
        try:
            with httpx.Client(timeout=1.5) as client:
                res = client.get(f"{self._base_url}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    models = [m.get("name") for m in data.get("models", [])]
                    self._cached_installed_models = models
                    self._cached_liveness = True
                    self._last_liveness_check = now
                    return True
        except Exception as e:
            logger.debug(f"Ollama liveness check failed: {e}")

        self._cached_liveness = False
        self._cached_installed_models = []
        self._last_liveness_check = now
        return False

    async def check_health_async(self) -> Dict[str, Any]:
        """Async deep health check returning detailed status and available models."""
        if not getattr(settings, "OLLAMA_ENABLED", True):
            return {
                "status": "DISABLED",
                "healthy": False,
                "models": [],
                "base_url": self._base_url
            }

        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self._base_url}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    models = [m.get("name") for m in data.get("models", [])]
                    self._cached_installed_models = models
                    self._cached_liveness = True
                    self._last_liveness_check = time.time()
                    has_target_model = any(self._model in m for m in models)
                    return {
                        "status": "ONLINE" if has_target_model else "MODEL_MISSING",
                        "healthy": True,
                        "models": models,
                        "target_model": self._model,
                        "model_ready": has_target_model,
                        "base_url": self._base_url
                    }
        except Exception as e:
            self._cached_liveness = False
            self._cached_installed_models = []
            self._last_liveness_check = time.time()
            return {
                "status": "UNREACHABLE",
                "healthy": False,
                "error": str(e),
                "models": [],
                "base_url": self._base_url
            }

        return {
            "status": "UNAVAILABLE",
            "healthy": False,
            "models": [],
            "base_url": self._base_url
        }

    def get_available_models(self) -> List[str]:
        if self._cached_installed_models:
            return self._cached_installed_models
        if self.is_configured():
            return self._cached_installed_models or [self._model]
        return []

    def supports_tools(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return False

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate response locally via Ollama /api/chat.
        Uses think: False by default to achieve sub-second execution for local-fast tasks.
        """
        target_model = model or self._model
        t_start = time.perf_counter()

        # Build Ollama chat payload
        payload = {
            "model": target_model,
            "messages": messages,
            "stream": False,
            # Bypasses thinking loop for blazing fast classification/extraction
            "think": kwargs.get("think", False),
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }

        # Optional tool declarations if provided
        if tools and self.supports_tools():
            payload["tools"] = tools

        url = f"{self._base_url}/api/chat"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

            latency_ms = int((time.perf_counter() - t_start) * 1000)
            msg = data.get("message", {})
            content = msg.get("content", "")

            prompt_tokens = data.get("prompt_eval_count", 0)
            completion_tokens = data.get("eval_count", 0)

            self.record_success(latency_ms, tokens=prompt_tokens + completion_tokens)

            result = {
                "content": content,
                "provider": self.provider_id,
                "model": target_model,
                "latency_ms": latency_ms,
                "status": "success",
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens
                },
                "total_duration_ns": data.get("total_duration", 0),
                "eval_duration_ns": data.get("eval_duration", 0),
            }

            # If tool calls were generated by Ollama
            if "tool_calls" in msg:
                result["tool_calls"] = msg["tool_calls"]

            return result

        except httpx.ConnectError as e:
            latency_ms = int((time.perf_counter() - t_start) * 1000)
            self.record_failure(
                f"Ollama daemon unreachable at {self._base_url}: {e}",
                is_transient=True,
                cooldown_seconds=15.0,
                health_state=HEALTH_UNAVAILABLE
            )
            self._cached_liveness = False
            logger.warning(f"Ollama connection error: {e}")
            return {
                "content": f"⚠️ **Ollama daemon unreachable at {self._base_url}:** {e}",
                "provider": self.provider_id,
                "model": target_model,
                "latency_ms": latency_ms,
                "status": "unreachable",
                "is_transient": True,
                "error": str(e),
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

        except httpx.TimeoutException as e:
            latency_ms = int((time.perf_counter() - t_start) * 1000)
            self.record_failure(
                f"Ollama request timed out after {self._timeout}s",
                is_transient=True,
                cooldown_seconds=20.0,
                health_state=HEALTH_UNAVAILABLE
            )
            logger.warning(f"Ollama timeout error: {e}")
            return {
                "content": f"⚠️ **Ollama request timed out after {self._timeout}s**",
                "provider": self.provider_id,
                "model": target_model,
                "latency_ms": latency_ms,
                "status": "timeout",
                "is_transient": True,
                "error": str(e),
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

        except Exception as e:
            latency_ms = int((time.perf_counter() - t_start) * 1000)
            self.record_failure(
                str(e),
                is_transient=True,
                cooldown_seconds=15.0,
                health_state=HEALTH_UNAVAILABLE
            )
            logger.error(f"Ollama generation failed: {e}")
            return {
                "content": f"⚠️ **Ollama generation failed:** {e}",
                "provider": self.provider_id,
                "model": target_model,
                "latency_ms": latency_ms,
                "status": "server_error",
                "is_transient": True,
                "error": str(e),
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

    async def stream_response(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream response chunks asynchronously from Ollama /api/chat."""
        target_model = model or self._model
        t_start = time.perf_counter()

        payload = {
            "model": target_model,
            "messages": messages,
            "stream": True,
            "think": kwargs.get("think", False),
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }

        url = f"{self._base_url}/api/chat"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream("POST", url, json=payload) as stream_resp:
                    stream_resp.raise_for_status()
                    async for line in stream_resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk_data = json.loads(line)
                            chunk_msg = chunk_data.get("message", {})
                            content_piece = chunk_msg.get("content", "")
                            if content_piece:
                                yield content_piece
                            if chunk_data.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue

            latency_ms = int((time.perf_counter() - t_start) * 1000)
            self.record_success(latency_ms)

        except Exception as e:
            latency_ms = int((time.perf_counter() - t_start) * 1000)
            self.record_failure(
                str(e),
                is_transient=True,
                cooldown_seconds=15.0,
                health_state=HEALTH_UNAVAILABLE
            )
            logger.error(f"Ollama streaming failed: {e}")
            raise
