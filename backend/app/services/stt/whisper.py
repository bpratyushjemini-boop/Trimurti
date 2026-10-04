"""
Local Faster-Whisper STT Provider for NARAD Vāṇī.
High-speed, offline speech recognition for English, Hindi, and Hinglish.
Zero paid cloud API required.
"""
import io
import os
import sys
import time
import logging
import asyncio
import tempfile
from typing import Optional

from app.services.stt.base import BaseSTTProvider, STTStatus, STTResult

logger = logging.getLogger(__name__)


class LocalWhisperSTTProvider(BaseSTTProvider):
    """
    Local implementation of faster-whisper on Apple Silicon / CPU.
    Keeps model loaded in memory for low latency.
    """

    def __init__(self, model_size: str = "tiny", device: str = "auto", compute_type: str = "int8"):
        self.model_size = model_size
        self.compute_type = compute_type
        self.target_device = device
        self._model = None
        self._load_error: Optional[str] = None
        self._init_latency: Optional[float] = None
        self._check_environment()

    def _check_environment(self) -> None:
        try:
            import faster_whisper
            self._load_error = None
        except ImportError:
            self._load_error = "faster-whisper is not installed. Install via: pip install faster-whisper"

    def _resolve_device(self) -> str:
        # CTranslate2 on macOS Apple Silicon operates at high efficiency on CPU using NEON/Accelerate
        if self.target_device and self.target_device != "auto":
            return self.target_device
        return "cpu"

    def is_available(self) -> bool:
        self._check_environment()
        return self._load_error is None

    def _ensure_model_loaded(self):
        if self._model is not None:
            return self._model

        if not self.is_available():
            raise RuntimeError(f"Local Whisper cannot initialize: {self._load_error}")

        t0 = time.time()
        try:
            from faster_whisper import WhisperModel
            resolved_device = self._resolve_device()
            logger.info("Initializing faster-whisper model '%s' on %s (%s)...", self.model_size, resolved_device, self.compute_type)
            self._model = WhisperModel(
                self.model_size,
                device=resolved_device,
                compute_type=self.compute_type
            )
            self._init_latency = round(time.time() - t0, 3)
            logger.info("faster-whisper model loaded in %.3fs", self._init_latency)
            return self._model
        except Exception as e:
            self._load_error = f"Model load failed: {str(e)}"
            logger.exception("Failed to load faster-whisper model:")
            raise RuntimeError(self._load_error) from e

    def get_status(self) -> STTStatus:
        self._check_environment()
        resolved_device = self._resolve_device()
        is_ready = self._model is not None or self.is_available()

        return STTStatus(
            engine="local_whisper",
            installed=self.is_available(),
            model_loaded=self._model is not None,
            ready=is_ready,
            device=resolved_device,
            supported_languages=["en", "hi", "hinglish", "auto"],
            error=self._load_error,
            active_fallback=not self.is_available()
        )

    async def transcribe(self, audio_bytes: bytes, file_format: str = "wav", language: str = "auto") -> STTResult:
        if not audio_bytes or len(audio_bytes) < 100:
            raise ValueError("Audio data is empty or too short for transcription.")

        def _transcribe_sync():
            model = self._ensure_model_loaded()
            
            # Temporary file with guaranteed cleanup
            suffix = f".{file_format.lstrip('.')}" if file_format else ".wav"
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
                    tf.write(audio_bytes)
                    temp_path = tf.name

                t_start = time.time()
                
                # Language handling
                lang_param = None if language in ("auto", "hinglish", None, "") else language
                
                # Transcribe with faster-whisper
                segments, info = model.transcribe(
                    temp_path,
                    language=lang_param,
                    beam_size=5,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=500)
                )

                transcribed_text = " ".join(seg.text.strip() for seg in segments).strip()
                latency = round(time.time() - t_start, 3)

                detected_lang = info.language or "en"
                prob = round(float(info.language_probability), 3) if info.language_probability else 1.0

                # Check if Romanized Hindi / Hinglish is present
                text_lower = transcribed_text.lower()
                hinglish_markers = {
                    "kholo", "chalao", "kya", "hai", "hain", "kaise", "bhai", "karo", "namaste",
                    "aaj", "hum", "kaun", "kahan", "mujhe", "sunao", "band", "ruk", "ruko"
                }
                words = set(text_lower.split())
                if detected_lang == "en" and words.intersection(hinglish_markers):
                    detected_lang = "hinglish"

                return STTResult(
                    text=transcribed_text,
                    language=detected_lang,
                    language_probability=prob,
                    duration_seconds=round(float(info.duration), 2) if info.duration else None,
                    latency_seconds=latency,
                    engine="local_whisper"
                )
            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass

        return await asyncio.to_thread(_transcribe_sync)
