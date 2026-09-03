from typing import Dict, List, Any, Optional, AsyncGenerator
import asyncio
from app.providers.base import BaseLLMProvider
from app.providers.gemini import GeminiProvider
from app.core.config import settings

class StubProvider(BaseLLMProvider):
    """
    Fallback diagnostic/simulated provider.
    Used when mock mode is explicitly requested or when running offline tests.
    """

    @property
    def provider_id(self) -> str:
        return "mock-narad"

    @property
    def display_name(self) -> str:
        return "NARAD Simulated Core (Fallback)"

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

        user_query_lower = last_user_msg.lower().strip()

        if any(greet in user_query_lower for greet in ["hello", "hi", "hey", "who are you", "what can you do"]):
            response_text = (
                "Greetings. I am **NARAD**—your private, personal AI assistant and primary interface "
                "for your local TRIMURTI system.\n\n"
                "I am currently operating as a **standalone, single-user system** in Milestone 2 interface mode. "
                "All sessions and messages are stored strictly on your local machine in SQLite with zero cloud data exposure. "
                "In Milestone 3, live multimodal AI providers (Gemini, Claude, OpenAI, and Groq) will be integrated directly into this workspace.\n\n"
                "How may I assist you today?"
            )
        elif "status" in user_query_lower or "system" in user_query_lower:
            response_text = (
                "**NARAD System Status Overview:**\n\n"
                "• **Architecture**: Private Single-User Standalone\n"
                "• **Interface Engine**: React 18 + Vite (JARVIS HUD visual design)\n"
                "• **Local Gateway**: FastAPI 0.110 (127.0.0.1, latency < 2ms)\n"
                "• **Data Storage**: Isolated local SQLite database\n"
                "• **AI Routing Layer**: Model-agnostic dispatcher (Simulated V1 Core active)\n"
                "• **Future Subsystems**: Smriti, Manthan, Kriya (Standby for V2)\n\n"
                "All local diagnostics are nominal. Ready for your directive."
            )
        else:
            response_text = (
                f"Understood. I have logged your directive: **\"{last_user_msg}\"**\n\n"
                "This conversation is stored locally in your private SQLite database. "
                "Currently operating in Milestone 2 interface verification mode with simulated responses. "
                "Live AI reasoning and external tool execution will unlock in upcoming milestones."
            )

        return {
            "content": response_text,
            "provider": self.provider_id,
            "model": model or "narad-core-v1",
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
            await asyncio.sleep(0.02)


class FutureSlotProvider(BaseLLMProvider):
    """
    Reserved provider slot for upcoming milestones (OpenRouter, Groq, Claude, OpenAI).
    """

    def __init__(self, pid: str, name: str, config_key: str):
        self._pid = pid
        self._name = name
        self._config_key = config_key

    @property
    def provider_id(self) -> str:
        return self._pid

    @property
    def display_name(self) -> str:
        return self._name

    def is_configured(self) -> bool:
        val = getattr(settings, self._config_key, "")
        return bool(val and val.strip())

    async def generate_response(self, messages, model=None, **kwargs) -> Dict[str, Any]:
        return {
            "content": f"⚠️ **{self._name} connector slot is reserved.** Integration will arrive in future milestone updates.",
            "provider": self.provider_id,
            "model": model or "unsupported",
            "status": "not_implemented",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0}
        }

    async def stream_response(self, messages, model=None, **kwargs) -> AsyncGenerator[str, None]:
        yield f"⚠️ {self._name} connector is reserved for future integration."


class ProviderManager:
    """
    Central registry and dispatcher for AI model providers.
    Supports runtime provider selection and query delegation.
    """

    def __init__(self):
        self._providers: Dict[str, BaseLLMProvider] = {}
        self._active_provider_id: str = settings.NARAD_DEFAULT_PROVIDER or "gemini"
        
        # 1. Register Primary Gemini Provider
        self.register_provider(GeminiProvider())

        # 2. Register Future Slots
        self.register_provider(FutureSlotProvider("openrouter", "OpenRouter Gateway", "OPENROUTER_API_KEY"))
        self.register_provider(FutureSlotProvider("groq", "Groq LPU", "GROQ_API_KEY"))
        self.register_provider(FutureSlotProvider("claude", "Anthropic Claude", "ANTHROPIC_API_KEY"))
        self.register_provider(FutureSlotProvider("openai", "OpenAI GPT", "OPENAI_API_KEY"))

        # 3. Register Fallback Mock Provider
        self.register_provider(StubProvider())

    def register_provider(self, provider: BaseLLMProvider):
        self._providers[provider.provider_id] = provider

    def get_provider(self, provider_id: Optional[str] = None) -> BaseLLMProvider:
        pid = provider_id or self._active_provider_id
        if pid not in self._providers:
            return self._providers.get(self._active_provider_id) or self._providers.get("gemini")
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
