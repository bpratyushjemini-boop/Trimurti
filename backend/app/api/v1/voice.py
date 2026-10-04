"""
NARAD Phase 3 — Mobile Voice API Router.
Provider-agnostic speech boundaries for iOS:
  - Voice Pipeline Status (STT + TTS engine readiness)
  - Speech-to-Text Transcription
  - Text-to-Speech Synthesis
"""

import base64
import uuid
from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.stt.manager import stt_manager
from app.services.tts.manager import tts_manager
from app.api.v1.schemas import (
    VoiceStatusResponse,
    TranscriptionResponse,
    ErrorResponse,
)

router = APIRouter(prefix="/voice", tags=["v1 - Voice"])


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to synthesize to speech")
    language: Optional[str] = Field("auto", description="Target language: en, hi, hinglish, or auto")
    voice: Optional[str] = Field("auto", description="Preferred voice profile or engine")
    output_format: Optional[str] = Field("wav", description="Audio format: wav")


# =============================================================================
# 1. VOICE STATUS
# =============================================================================

@router.get(
    "/status",
    response_model=VoiceStatusResponse,
    summary="Voice Stack Health & Hardware Readiness"
)
def get_voice_status():
    """
    Returns engine availability, compute hardware, and supported languages
    without locking the iOS client to a single vendor or provider.
    """
    stt_status = stt_manager.get_status()
    tts_status = tts_manager.get_status()

    return VoiceStatusResponse(
        stt_ready=bool(stt_status.ready or stt_status.installed),
        stt_engine=getattr(stt_status, "engine", "local_whisper"),
        stt_device=getattr(stt_status, "device", "cpu"),
        tts_ready=bool(tts_status.ready or tts_status.installed),
        tts_engine=getattr(tts_status, "provider", "chatterbox"),
        tts_device=getattr(tts_status, "device", "cpu"),
        supported_languages=["en", "hi", "hinglish"],
        local_voice_enabled=bool(getattr(settings, "TTS_LOCAL", True)),
    )


# =============================================================================
# 2. SPEECH-TO-TEXT (TRANSCRIBE)
# =============================================================================

@router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="Transcribe Audio Recording"
)
async def transcribe_audio(
    request: Request,
    file: UploadFile = File(..., description="Audio file payload (WAV, MP3, M4A)"),
    language: Optional[str] = Form("auto", description="Optional language hint (auto, en, hi)"),
):
    """
    Transcribes audio bytes recorded from the mobile microphone.
    Supports English, Hindi, and Hinglish.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    stt_status = stt_manager.get_status()

    audio_bytes = await file.read()
    if not audio_bytes or len(audio_bytes) < 64:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "INVALID_AUDIO",
                    "message": "Audio file is empty or corrupted.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": stt_status.engine,
                }
            }
        )

    filename = file.filename or "recording.wav"
    ext = filename.split(".")[-1] if "." in filename else "wav"

    try:
        result = await stt_manager.transcribe(
            audio_bytes=audio_bytes,
            file_format=ext,
            language=language or "auto",
        )
        return TranscriptionResponse(
            text=result.text,
            language=result.language,
            duration=result.duration_seconds or 0.0,
            engine=result.engine,
            success=True,
        )
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "STT_UNAVAILABLE",
                    "message": f"Speech transcription failed: {str(exc)}",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": True,
                    "provider": stt_status.engine,
                }
            }
        )


# =============================================================================
# 3. TEXT-TO-SPEECH (SYNTHESIZE)
# =============================================================================

@router.post(
    "/synthesize",
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="Synthesize Text into Speech Audio"
)
async def synthesize_speech(
    payload: SynthesizeRequest,
    request: Request,
):
    """
    Synthesizes speech from input text.
    Returns standard audio stream (audio/wav) playable by iOS AVAudioPlayer,
    or JSON base64 when requested.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    clean_text = payload.text.strip()
    if not clean_text:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "EMPTY_TEXT",
                    "message": "Text for synthesis cannot be empty.",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": False,
                    "provider": None,
                }
            }
        )

    try:
        tts_res = await tts_manager.synthesize(
            text=clean_text,
            language=payload.language or "auto",
        )

        accept_header = request.headers.get("Accept", "")
        if "application/json" in accept_header:
            return {
                "audio_base64": base64.b64encode(tts_res.audio_bytes).decode("ascii"),
                "format": tts_res.format,
                "sample_rate": tts_res.sample_rate,
                "duration_seconds": tts_res.duration_seconds,
                "provider": tts_res.provider,
                "language": tts_res.language,
            }

        return Response(
            content=tts_res.audio_bytes,
            media_type=f"audio/{tts_res.format}",
            headers={
                "Content-Disposition": f'inline; filename="narad_speech.{tts_res.format}"',
                "X-Audio-Duration": str(tts_res.duration_seconds or 0.0),
                "X-Audio-Engine": tts_res.provider,
            }
        )
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "TTS_UNAVAILABLE",
                    "message": f"Speech synthesis failed: {str(exc)}",
                    "request_id": req_id,
                    "task_id": None,
                    "retryable": True,
                    "provider": "chatterbox",
                }
            }
        )
