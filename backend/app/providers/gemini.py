import os
import asyncio
import json
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
import httpx

from app.providers.base import BaseLLMProvider
from app.core.config import settings

logger = logging.getLogger(__name__)

class GeminiProvider(BaseLLMProvider):
    """
    Google Gemini AI model provider implementation for NARAD Core.
    Supports modern Gemini models (default: gemini-2.5-flash).
    Uses the official google-genai SDK with an asynchronous HTTPX REST fallback.
    """

    @property
    def provider_id(self) -> str:
        return "gemini"

    @property
    def display_name(self) -> str:
        return "Google Gemini"

    def _get_api_key(self) -> str:
        # Check in-memory settings / process environment (clean quotes and whitespace)
        key = (settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")).strip().strip('"\'')
        if key:
            return key

        # Dynamic disk check so saving backend/.env immediately takes effect without server restart
        try:
            from dotenv import dotenv_values
            from app.core.config import BACKEND_ENV_PATH, ROOT_ENV_PATH
            for env_path in [BACKEND_ENV_PATH, ROOT_ENV_PATH]:
                if env_path.is_file() and env_path.stat().st_size > 0:
                    vals = dotenv_values(env_path)
                    disk_key = (vals.get("GEMINI_API_KEY") or "").strip().strip('"\'')
                    if disk_key:
                        settings.GEMINI_API_KEY = disk_key
                        os.environ["GEMINI_API_KEY"] = disk_key
                        return disk_key
        except Exception:
            pass

        return ""

    def is_configured(self) -> bool:
        return bool(self._get_api_key())

    def _format_messages_for_gemini(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Convert standard OpenAI-style [{role, content}] format
        to Gemini's required [{role: 'user'|'model', parts: [{text: ...}]}] format.
        Ensures turns strictly alternate between 'user' and 'model'.
        """
        formatted = []
        for m in messages:
            content = m.get("content", "").strip()
            if not content:
                continue
            
            role = m.get("role", "user")
            gemini_role = "model" if role in ("assistant", "model") else "user"
            
            if formatted and formatted[-1]["role"] == gemini_role:
                formatted[-1]["parts"][0]["text"] += f"\n\n{content}"
            else:
                formatted.append({
                    "role": gemini_role,
                    "parts": [{"text": content}]
                })
        
        # Ensure conversation begins with a 'user' turn
        if formatted and formatted[0]["role"] != "user":
            formatted.insert(0, {"role": "user", "parts": [{"text": "Session initialized."}]})

        return formatted

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> Dict[str, Any]:
        api_key = self._get_api_key()
        target_model = model or settings.NARAD_DEFAULT_MODEL or "gemini-2.5-flash"

        # Check configuration
        if not api_key:
            return {
                "content": (
                    "⚠️ **GEMINI_API_KEY is not configured.**\n\n"
                    "To activate real Gemini AI intelligence in NARAD:\n"
                    "1. Obtain a free API key from Google AI Studio: https://aistudio.google.com/app/apikey\n"
                    "2. Create or update `backend/.env` with:\n"
                    "   `GEMINI_API_KEY=your_actual_key_here`\n"
                    "3. Send your message again.\n\n"
                    "*All API keys remain strictly local in your private environment vault.*"
                ),
                "provider": self.provider_id,
                "model": target_model,
                "status": "unconfigured",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

        formatted_contents = self._format_messages_for_gemini(messages)
        if not formatted_contents:
            return {
                "content": "No content provided for synthesis.",
                "provider": self.provider_id,
                "model": target_model,
                "status": "error",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

        # 1. Attempt official google-genai SDK first
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            
            # Run blocking SDK call in worker thread pool
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=target_model,
                contents=formatted_contents,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens
                )
            )

            response_text = response.text or ""
            usage = {}
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = {
                    "prompt_tokens": getattr(response.usage_metadata, 'prompt_token_count', 0) or 0,
                    "completion_tokens": getattr(response.usage_metadata, 'candidates_token_count', 0) or 0,
                    "total_tokens": getattr(response.usage_metadata, 'total_token_count', 0) or 0
                }

            return {
                "content": response_text,
                "provider": self.provider_id,
                "model": target_model,
                "usage": usage,
                "status": "success"
            }

        except Exception as sdk_err:
            logger.warning(f"google-genai SDK call failed: {sdk_err}. Attempting HTTPX REST fallback...")

            # 2. Asynchronous REST Fallback via HTTPX
            try:
                endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent"
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key
                }
                payload = {
                    "contents": formatted_contents,
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": max_tokens
                    }
                }

                async with httpx.AsyncClient(timeout=30.0) as http_client:
                    res = await http_client.post(endpoint, headers=headers, json=payload)
                    
                    if res.status_code != 200:
                        error_detail = res.text
                        try:
                            err_json = res.json()
                            error_detail = err_json.get("error", {}).get("message", res.text)
                        except Exception:
                            pass
                        
                        logger.error(f"Gemini API returned error HTTP {res.status_code}: {error_detail}")
                        return {
                            "content": f"⚠️ **GEMINI REQUEST FAILED (HTTP {res.status_code}):** {error_detail}\n\n*Please ensure a valid Gemini API key from Google AI Studio (https://aistudio.google.com/app/apikey) is set in `backend/.env`.*",
                            "provider": self.provider_id,
                            "model": target_model,
                            "status": "api_error",
                            "usage": {"prompt_tokens": 0, "completion_tokens": 0}
                        }

                    data = res.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        return {
                            "content": "Received empty candidate response from Gemini API.",
                            "provider": self.provider_id,
                            "model": target_model,
                            "status": "empty_response",
                            "usage": {"prompt_tokens": 0, "completion_tokens": 0}
                        }

                    parts = candidates[0].get("content", {}).get("parts", [])
                    extracted_text = "".join(p.get("text", "") for p in parts)
                    usage_meta = data.get("usageMetadata", {})
                    usage = {
                        "prompt_tokens": usage_meta.get("promptTokenCount", 0),
                        "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
                        "total_tokens": usage_meta.get("totalTokenCount", 0)
                    }

                    return {
                        "content": extracted_text,
                        "provider": self.provider_id,
                        "model": target_model,
                        "usage": usage,
                        "status": "success"
                    }

            except Exception as http_err:
                logger.error(f"HTTPX fallback call failed: {http_err}", exc_info=True)
                return {
                    "content": f"⚠️ **GEMINI REQUEST FAILED (Connection Error):** Unable to reach Gemini API endpoint: {str(http_err)}",
                    "provider": self.provider_id,
                    "model": target_model,
                    "status": "network_error",
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0}
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
        words = result.get("content", "").split(" ")
        for word in words:
            yield word + " "
            await asyncio.sleep(0.02)
