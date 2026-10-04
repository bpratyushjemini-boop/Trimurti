"""
NARAD V7.1 — BaseVisionProvider Interface.
Defines provider-agnostic interface for multimodal vision and screen understanding.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseVisionProvider(ABC):
    """Abstract interface for local or remote multimodal vision understanding providers."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def understand_image(
        self,
        image_bytes: bytes,
        prompt: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Analyze an image or screenshot and return structured understanding."""
        pass
