"""
NARAD Phase 2.5 — OpenAI-Compatible Interchangeable Provider Gateway.
Enables NARAD to treat any OpenAI-compatible provider/gateway as a first-class,
interchangeable inference provider with full telemetry, rate-limit tracking,
cooldown enforcement, failure classification, and streaming support.

Applicable for:
  - DeepInfra, Together AI, Fireworks, Mistral, Cerebras, SambaNova
  - Local vLLM / llama.cpp / LM Studio / text-generation-webui
  - Custom cloud gateways and proxies
"""

import time
import json
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
import httpx

from app.providers.base import (
    BaseLLMProvider,
    HEALTH_AVAILABLE,
    HEALTH_RATE_LIMITED,
    HEALTH_QUOTA_EXHAUSTED,
    HEALTH_DEGRADED,
    HEALTH_AUTH_ERROR,
    HEALTH_UNAVAILABLE,
    HEALTH_NOT_CONFIGURED,
)

logger = logging.getLogger("narad.providers.openai_compatible")


class OpenAICompatibleProvider(BaseLLMProvider):
    """
    Standardized, interchangeable OpenAI-compatible gateway connector.
    Treats providers as interchangeable without assuming 'free' means unlimited.
    """

    def __init__(
        self,
        provider_id: str,
        display_name: str,
        base_url: str,
        api_key: str = "",
        default_model: str = "default-model",
        available_models: Optional[List[str]] = None,
        timeout_seconds: float = 45.0,
    ):
        super().__init__()
        self._provider_id = provider_id.lower().strip()
        self._display_name = display_name
        self._base_url = base_url.rstrip("/") if base_url else ""
        self._api_key = api_key
        self._default_model = default_model
        self._available_models = available_models or [default_model]
        self._timeout_seconds = timeout_seconds

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def display_name(self) -> str:
        return self._display_name

    def is_configured(self) -> bool:
        # If running a local unauthenticated gateway, base_url is enough;
        # otherwise requires non-empty base_url and api_key
        if not self._base_url:
            return False
        if "localhost" in self._base_url or "127.0.0.1" in self._base_url:
            return True
        return bool(self._api_key and self._api_key.strip())

    def get_available_models(self) -> List[str]:
        return list(self._available_models)

    def supports_tools(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return False

    def classify_and_record_error(self, status_code: int, error_text: str, latency_ms: int = 0):
        """Classify HTTP errors into appropriate health states and cooldowns."""
        err_lower = error_text.lower()
        if status_code in (401, 403) or "unauthorized" in err_lower or "invalid api key" in err_lower:
            self.record_failure(
                error_msg=f"HTTP {status_code}: {error_text}",
                is_transient=False,
                health_state=HEALTH_AUTH_ERROR
            )
        elif status_code == 429 or "rate limit" in err_lower or "tpm" in err_lower or "rpm" in err_lower:
            self.record_rate_limit(error_msg=f"HTTP 429: {error_text}", retry_after=60.0)
        elif status_code == 402 or "quota" in err_lower or "insufficient funds" in err_lower or "credit" in err_lower:
            self.record_failure(
                error_msg=f"Quota exhausted: {error_text}",
                is_transient=True,
                cooldown_seconds=3600.0,
                health_state=HEALTH_QUOTA_EXHAUSTED
            )
        elif status_code >= 500:
            self.record_failure(
                error_msg=f"Server error {status_code}: {error_text}",
                is_transient=True,
                cooldown_seconds=30.0,
                health_state=HEALTH_UNAVAILABLE
            )
        else:
            self.record_failure(
                error_msg=f"Client error {status_code}: {error_text}",
                is_transient=False,
                health_state=HEALTH_DEGRADED
            )

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute chat completion request against the OpenAI-compatible endpoint."""
        target_model = model or self._default_model
        t0 = time.perf_counter()

        if self.is_in_cooldown():
            raise RuntimeError(f"Provider {self.display_name} is in cooldown. Retry in {int(self._cooldown_until - time.time())}s")

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                resp = await client.post(url, json=payload, headers=headers)
                latency_ms = int((time.perf_counter() - t0) * 1000)

                if resp.status_code != 200:
                    self.classify_and_record_error(resp.status_code, resp.text, latency_ms)
                    return {
                        "content": f"⚠️ [{self.display_name}] Error: HTTP {resp.status_code}",
                        "provider": self.provider_id,
                        "model": target_model,
                        "latency_ms": latency_ms,
                        "status": "error",
                        "is_transient": resp.status_code in (429, 500, 502, 503, 504),
                        "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                    }

                data = resp.json()
                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "")
                usage = data.get("usage", {})
                tokens = usage.get("total_tokens", 0)

                self.record_success(latency_ms=latency_ms, tokens=tokens)

                return {
                    "content": content,
                    "provider": self.provider_id,
                    "model": target_model,
                    "latency_ms": latency_ms,
                    "status": "success",
                    "usage": {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                    }
                }
        except httpx.TimeoutException as te:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            self.record_failure(f"Timeout after {self._timeout_seconds}s", is_transient=True, cooldown_seconds=30.0)
            return {
                "content": f"⚠️ [{self.display_name}] Request timed out.",
                "provider": self.provider_id,
                "model": target_model,
                "latency_ms": latency_ms,
                "status": "error",
                "is_transient": True,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            }
        except Exception as ex:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            self.record_failure(str(ex), is_transient=True, cooldown_seconds=20.0)
            return {
                "content": f"⚠️ [{self.display_name}] Connection error: {str(ex)}",
                "provider": self.provider_id,
                "model": target_model,
                "latency_ms": latency_ms,
                "status": "error",
                "is_transient": True,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            }

    async def stream_response(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream chunks from the OpenAI-compatible SSE streaming endpoint."""
        target_model = model or self._default_model
        url = f"{self._base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    yield f"⚠️ [{self.display_name}] HTTP {resp.status_code}"
                    return

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        raw_data = line[6:].strip()
                        if raw_data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(raw_data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content_piece = delta.get("content")
                            if content_piece:
                                yield content_piece
                        except Exception:
                            continue
