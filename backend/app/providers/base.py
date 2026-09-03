from abc import ABC, abstractmethod
from typing import List, Dict, Any, AsyncGenerator, Optional

class BaseLLMProvider(ABC):
    """
    Abstract Base Class for all AI model providers in the NARAD ecosystem.
    Model-agnostic design ensures NARAD can swap between Gemini, Groq, OpenRouter,
    Claude, OpenAI, or local engines without changing frontend or agent logic.
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique provider identifier (e.g., 'gemini', 'groq', 'openrouter')."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider label for the HUD."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Returns True if the required environment variable/API key is present."""
        pass

    @abstractmethod
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate a complete text response."""
        pass

    @abstractmethod
    async def stream_response(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens asynchronously."""
        pass
