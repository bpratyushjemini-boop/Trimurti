"""
Vāṇī STT API Router for NARAD.
Exposes status and audio transcription endpoints for local Whisper.
"""
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status

from app.services.stt.base import STTStatus, STTResult
from app.services.stt.manager import stt_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stt", tags=["STT"])


@router.get("/status", response_model=STTStatus, status_code=status.HTTP_200_OK)
def get_stt_status():
    """
    Returns real-time health, installation, and hardware status of local Whisper STT.
    """
    return stt_manager.get_status()


@router.post("/transcribe", response_model=STTResult, status_code=status.HTTP_200_OK)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Optional[str] = Form(default="auto")
):
    """
    Transcribes audio file recorded from browser microphone.
    Supports English, Hindi, and Hinglish.
    """
    status_info = stt_manager.get_status()
    if not status_info.ready and not status_info.installed:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "Local Whisper STT is not ready or dependencies are missing.",
                "reason": status_info.error,
                "engine": status_info.engine,
                "fallback_recommended": True
            }
        )

    try:
        audio_bytes = await file.read()
        filename = file.filename or "recording.wav"
        ext = filename.split(".")[-1] if "." in filename else "wav"
        
        result = await stt_manager.transcribe(
            audio_bytes=audio_bytes,
            file_format=ext,
            language=language or "auto"
        )
        return result
    except Exception as exc:
        logger.exception("Transcription failed in /api/stt/transcribe:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"Speech transcription failed: {str(exc)}",
                "fallback_recommended": True
            }
        ) from exc
