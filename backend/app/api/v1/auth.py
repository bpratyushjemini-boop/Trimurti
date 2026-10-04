"""
NARAD Phase 3 — Mobile Authentication Handshake Router.
Single-user owner authentication for iOS client.
No multi-user accounts, subscriptions, or SaaS billing.
"""

import uuid
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.v1.schemas import AuthVerifyResponse, ErrorResponse

router = APIRouter(prefix="/auth", tags=["v1 - Authentication"])


@router.post(
    "/verify",
    response_model=AuthVerifyResponse,
    responses={401: {"model": ErrorResponse}},
    summary="Single-User Mobile Auth Handshake"
)
async def verify_auth(request: Request):
    """
    Validates single-user API token for the iOS mobile client.
    Returns authentication state, user identity ('owner'), and active runtime mode.
    """
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    api_key = getattr(settings, "NARAD_API_KEY", "")

    # If no API key is configured on server, access is granted to local/private owner
    if not api_key or not api_key.strip():
        return AuthVerifyResponse(
            authenticated=True,
            user="owner",
            system=settings.APP_NAME,
            runtime_mode=settings.NARAD_RUNTIME_MODE,
            token_valid=True,
        )

    # Inspect Bearer token or X-Narad-Key header
    auth_header = request.headers.get("Authorization", "")
    key_header = request.headers.get("X-Narad-Key", "")
    provided_token = ""

    if auth_header.startswith("Bearer "):
        provided_token = auth_header[len("Bearer "):].strip()
    elif key_header:
        provided_token = key_header.strip()

    if provided_token == api_key:
        return AuthVerifyResponse(
            authenticated=True,
            user="owner",
            system=settings.APP_NAME,
            runtime_mode=settings.NARAD_RUNTIME_MODE,
            token_valid=True,
        )

    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={
            "error": {
                "code": "AUTH_REQUIRED",
                "message": "Invalid authentication token provided.",
                "request_id": req_id,
                "task_id": None,
                "retryable": False,
                "provider": None,
            }
        },
        headers={"WWW-Authenticate": "Bearer"},
    )
