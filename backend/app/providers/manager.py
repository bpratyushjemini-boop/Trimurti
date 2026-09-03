from typing import Dict, List, Any, Optional, AsyncGenerator
import asyncio
from app.providers.base import BaseLLMProvider

class StubProvider(BaseLLMProvider):
    """
    Default foundational provider for Milestone 1.
    Demonstrates model-agnostic structure and response dispatching
    without requiring external API keys or live network dependencies.
    """

    @property
    def provider_id(self) -> str:
        return "mock-narad"

    @property
    def display_name(self) -> str:
        return "NARAD Simulated Core (Milestone 1)"

    def is_configured(self) -> bool:
        return True

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> Dict[str, Any]:
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "")
                break

        response_text = (
            f"[NARAD CORE :: TELEMETRY ONLINE]\n"
            f"Transceiver received input: \"{last_user_msg}\"\n\n"
            f"Foundations verified. SQLite persistence, modular provider registry, "
            f"and JARVIS HUD interface are operating within normal parameters. "
            f"Live AI provider modules (Gemini, Groq, OpenRouter, Claude, OpenAI) "
            f"will be connected in subsequent milestones."
        )

        return {
            "content": response_text,
            "provider": self.provider_id,
            "model": model or "narad-v1-foundation",
            "usage": {"prompt_tokens": len(last_user_msg.split()), "completion_tokens": len(response_text.split())}
        }

    async def stream_response(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        result = await self.generate_response(messages, model, temperature, max_tokens, **kwargs)
        words = result["content"].split(" ")
        for word in words:
            yield word + " "
            await asyncio.sleep(0.04)

class ProviderManager:
    """
    Central registry and dispatcher for AI model providers.
    Allows runtime provider selection without modifying API or client logic.
    """

    def __init__(self):
        self._providers: Dict[str, BaseLLMProvider] = {}
        self._active_provider_id: str = "mock-narad"
        
        # Register default foundational provider
        self.register_provider(StubProvider())

    def register_provider(self, provider: BaseLLMProvider):
        self._providers[provider.provider_id] = provider

    def get_provider(self, provider_id: Optional[str] = None) -> BaseLLMProvider:
        pid = provider_id or self._active_provider_id
        if pid not in self._providers:
            # Fallback to active or first available
            return self._providers.get(self._active_provider_id)
        return self._providers[pid]

    def set_active_provider(self, provider_id: str) -> bool:
        if provider_id in self._providers:
            self._active_provider_id = provider_id
            return True
        return False

    def list_providers(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": p.provider_id,
                "display_name": p.display_name,
                "is_configured": p.is_configured(),
                "is_active": p.provider_id == self._active_provider_id
            }
            for p in self._providers.values()
        ]

# Global singleton provider manager instance
provider_manager = ProviderManager()
