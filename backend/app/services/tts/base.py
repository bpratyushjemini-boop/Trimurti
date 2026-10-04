"""
TTS Provider Abstraction Layer for NARAD Vāṇī.
Defines base interfaces, telemetry models, and standard contracts for local/cloud TTS engines.
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel, Field


class TTSStatus(BaseModel):
    provider: str = Field(default="chatterbox", description="Active TTS provider identifier")
    installed: bool = Field(default=False, description="Whether engine package is installed in current Python environment")
    model_loaded: bool = Field(default=False, description="Whether weights are cached/loaded in memory")
    ready: bool = Field(default=False, description="Whether TTS is ready to synthesize immediately")
    mode: str = Field(default="local", description="'local' or 'cloud'")
    device: str = Field(default="cpu", description="Hardware device: mps, cpu, cuda")
    supported_languages: List[str] = Field(default_factory=lambda: ["en", "hi", "hinglish"], description="List of supported ISO language codes")
    initialization_time: Optional[float] = Field(default=None, description="Model load time in seconds")
    generation_time: Optional[float] = Field(default=None, description="Last audio generation time in seconds")
    error: Optional[str] = Field(default=None, description="Diagnostic error reason if not ready")
    active_fallback: bool = Field(default=False, description="Whether current speech requests are falling back to browser synthesis")
    fallback_provider: Optional[str] = Field(default="browser_speech_synthesis", description="Fallback provider name")
    available_engines: List[str] = Field(default_factory=lambda: ["chatterbox", "indicvoice"], description="List of installed engine backends")
    engines: Optional[dict] = Field(default=None, description="Per-engine status map (chatterbox, indicvoice)")


class TTSResult(BaseModel):
    audio_bytes: bytes
    format: str = "wav"
    sample_rate: int = 24000
    duration_seconds: Optional[float] = None
    generation_time: Optional[float] = None
    provider: str = "chatterbox"
    language: str = "en"
    device: str = "cpu"


class BaseTTSProvider(ABC):
    """
    Abstract contract for all NARAD Text-to-Speech engines.
    Ensures provider-agnostic extensibility.
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        pass

    @abstractmethod
    def get_status(self) -> TTSStatus:
        """Return the current health, availability, and hardware status of this provider."""
        pass

    @abstractmethod
    async def synthesize(self, text: str, language: str = "auto") -> TTSResult:
        """
        Synthesize text into raw audio bytes.
        Must raise an informative exception rather than returning mock/fake audio if unavailable.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Quick boolean probe indicating whether this engine can be executed."""
        pass
