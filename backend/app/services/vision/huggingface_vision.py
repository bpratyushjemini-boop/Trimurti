"""
NARAD V7.1 — Local Hugging Face Vision Provider Interface.
Provider abstraction ready for future lightweight local vision models (e.g. SmolVLM, Moondream2)
without loading massive weights immediately.
"""

import logging
from typing import Dict, Any, Optional

from app.services.vision.base import BaseVisionProvider
from app.services.local_ai.cache import hf_cache_manager
from app.core.config import settings

is_cloud = (
    settings.is_cloud
    or getattr(settings, "NARAD_RUNTIME_MODE", "hybrid").lower() == "cloud"
)

if is_cloud:
    torch = None
    HAS_TORCH = False
else:
    try:
        import torch
        HAS_TORCH = True
    except ImportError:
        torch = None
        HAS_TORCH = False


def is_torch_available() -> bool:
    return HAS_TORCH

logger = logging.getLogger("narad.vision.huggingface")


class LocalHuggingFaceVisionProvider(BaseVisionProvider):
    """
    Local on-device Hugging Face vision provider stub/interface.
    Reports honest status and provides the foundation for future local vision models.
    """

    def __init__(self, model_name: str = "HuggingFaceTB/SmolVLM-Instruct"):
        self._model_name = model_name
        self._is_loaded = False
        if HAS_TORCH and hasattr(torch, "backends") and hasattr(torch.backends, "mps"):
            self._device = "mps" if torch.backends.mps.is_available() else "cpu"
        else:
            self._device = "none"

    @property
    def provider_id(self) -> str:
        return "huggingface_vision"

    @property
    def model_name(self) -> str:
        return self._model_name

    def is_available(self) -> bool:
        if getattr(settings, "ENVIRONMENT", "LOCAL").upper() == "CLOUD":
            return False
        if getattr(settings, "NARAD_RUNTIME_MODE", "hybrid").lower() == "cloud":
            return False
        if not HAS_TORCH:
            return False
        return self._is_loaded

    def get_status(self) -> Dict[str, Any]:
        is_cloud = (
            settings.is_cloud
            or getattr(settings, "NARAD_RUNTIME_MODE", "hybrid").lower() == "cloud"
        )
        if is_cloud or not HAS_TORCH:
            return {
                "provider": self.provider_id,
                "model": self._model_name,
                "device": "NONE",
                "status": "UNAVAILABLE",
                "is_available": False,
                "cached": False,
                "description": "On-device Hugging Face vision provider unavailable in CLOUD mode or without PyTorch."
            }

        return {
            "provider": self.provider_id,
            "model": self._model_name,
            "device": self._device.upper(),
            "status": "READY" if self._is_loaded else "NOT_LOADED",
            "is_available": self.is_available(),
            "cached": hf_cache_manager.is_model_cached(self._model_name),
            "description": "On-device Hugging Face vision provider slot ready for weights initialization."
        }

    async def understand_image(
        self,
        image_bytes: bytes,
        prompt: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Processes image if model is loaded, otherwise instructs fallback to Trinetra cloud vision.
        """
        if not self._is_loaded:
            return {
                "success": False,
                "error": (
                    f"Local vision model '{self._model_name}' is not currently loaded. "
                    "Use Trinetra cloud multimodal router (Gemini) for screen understanding."
                ),
                "fallback_recommended": True,
                "provider": self.provider_id,
                "status": "not_loaded"
            }

        raise NotImplementedError("Local vision inference execution will arrive in subsequent updates.")


# Global singleton
local_hf_vision_provider = LocalHuggingFaceVisionProvider()
