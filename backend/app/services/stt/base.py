"""
STT Provider Abstraction Layer for NARAD Vāṇī.
Defines base interfaces, telemetry models, and standard contracts for local/cloud STT engines.
"""
from abc import ABC, abstractmethod
from typing import Optional, List
from pydantic import BaseModel, Field


class STTStatus(BaseModel):
    engine: str = Field(default="local_whisper", description="Active STT engine identifier")
    installed: bool = Field(default=False, description="Whether faster-whisper/whisper is installed")
    model_loaded: bool = Field(default=False, description="Whether model weights are loaded in memory")
    ready: bool = Field(default=False, description="Whether STT is ready to transcribe immediately")
    device: str = Field(default="cpu", description="Hardware compute device: cpu, mps, cuda")
    supported_languages: List[str] = Field(default_factory=lambda: ["en", "hi", "hinglish", "auto"])
    error: Optional[str] = Field(default=None, description="Diagnostic error reason if not ready")
    active_fallback: bool = Field(default=False, description="Whether falling back to browser SpeechRecognition")


class STTResult(BaseModel):
    text: str = Field(..., description="Transcribed text string")
    language: str = Field(default="en", description="Detected or requested language code")
    language_probability: float = Field(default=1.0, description="Confidence of detected language")
    duration_seconds: Optional[float] = Field(default=None, description="Audio duration in seconds")
    latency_seconds: float = Field(default=0.0, description="Inference latency in seconds")
    engine: str = Field(default="local_whisper", description="Engine that performed transcription")


class BaseSTTProvider(ABC):
    """
    Abstract contract for all NARAD Speech-to-Text engines.
    """

    @abstractmethod
    def get_status(self) -> STTStatus:
        """Return the current health, availability, and hardware status of this STT engine."""
        pass

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, file_format: str = "wav", language: str = "auto") -> STTResult:
        """
        Transcribe raw audio bytes into text.
        Must raise an informative exception rather than returning mock/fake output if unavailable.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Quick boolean probe indicating whether this engine can transcribe."""
        pass
