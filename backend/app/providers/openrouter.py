"""
OpenRouter LLM Provider Implementation for NARAD Core.
Connects to the OpenRouter unified API gateway (https://openrouter.ai/api/v1).
Supports OpenAI-compatible schemas, multi-turn Krīya tool-calling loop,
synthesis pass, health tracking, and failover integration.
"""

import os
import re
import json
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
import httpx

from app.providers.base import BaseLLMProvider
from app.core.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_OPENROUTER_MODELS = [
    "meta-llama/llama-3.3-70b-instruct",
    "anthropic/claude-3.5-sonnet",
    "deepseek/deepseek-r1",
    "google/gemini-2.5-flash"
]


class OpenRouterProvider(BaseLLMProvider):
    """
    OpenRouter API provider implementation for NARAD Core.
    Acts as a gateway to multi-vendor models with unified tool calling.
    """

    def __init__(self):
        super().__init__()

    @property
    def provider_id(self) -> str:
        return "openrouter"

    @property
    def display_name(self) -> str:
        return "OpenRouter"

    def get_available_models(self) -> List[str]:
        return list(DEFAULT_OPENROUTER_MODELS)

    def supports_vision(self) -> bool:
        return True

    def _get_api_key(self) -> str:
        # 1. Check on-disk backend/.env first
        try:
            from dotenv import dotenv_values
            from app.core.config import BACKEND_ENV_PATH, ROOT_ENV_PATH
            for env_path in [BACKEND_ENV_PATH, ROOT_ENV_PATH]:
                if env_path.is_file() and env_path.stat().st_size > 0:
                    vals = dotenv_values(env_path)
                    disk_key = (vals.get("OPENROUTER_API_KEY") or "").strip().strip('"\'')
                    if disk_key:
                        settings.OPENROUTER_API_KEY = disk_key
                        os.environ["OPENROUTER_API_KEY"] = disk_key
                        return disk_key
        except Exception:
            pass

        # 2. Fall back to settings / env
        key = (settings.OPENROUTER_API_KEY or os.environ.get("OPENROUTER_API_KEY", "")).strip().strip('"\'')
        if key:
            return key
        return ""

    def is_configured(self) -> bool:
        return bool(self._get_api_key())

    def _format_messages_for_openrouter(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format messages for OpenAI-compatible OpenRouter schema."""
        formatted = []
        for m in messages:
            role = str(m.get("role", "user")).lower().strip()
            if role == "tool":
                formatted.append({
                    "role": "tool",
                    "tool_call_id": str(m.get("tool_call_id", "")),
                    "name": str(m.get("name", "")),
                    "content": str(m.get("content", ""))
                })
                continue

            content = m.get("content")
            if role in ("assistant", "model"):
                clean_role = "assistant"
                tool_calls = m.get("tool_calls")
                if tool_calls:
                    formatted.append({
                        "role": "assistant",
                        "content": content if content is not None else None,
                        "tool_calls": tool_calls
                    })
                    continue
            elif role == "system":
                clean_role = "system"
            else:
                clean_role = "user"

            if content is None:
                continue
            if isinstance(content, str) and not content.strip():
                continue

            if isinstance(content, list):
                formatted.append({
                    "role": clean_role,
                    "content": content
                })
            else:
                formatted.append({
                    "role": clean_role,
                    "content": str(content).strip()
                })

        if not formatted:
            formatted.append({"role": "user", "content": "Hello"})
        return formatted

    def _build_fallback_synthesis(self, executed_tools: List[Dict[str, Any]]) -> str:
        """Deterministic synthesis from executed tool results."""
        # 1. Web search synthesis
        seen_urls = set()
        search_items = []
        for t in executed_tools:
            if t.get("name") == "web_search":
                res = t.get("result")
                if isinstance(res, dict) and res.get("status") == "success":
                    for item in res.get("results", []):
                        url = str(item.get("url", "")).strip()
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            search_items.append(item)

        if search_items:
            lines = ["Here is what I found from verified live web search results:\n"]
            for item in search_items[:5]:
                title = item.get("title", "Reference")
                url = item.get("url", "")
                source = item.get("source", "")
                snippet = item.get("snippet", "")
                lines.append(f"• **[{title}]({url})** (Source: `{source}`)\n  {snippet}\n")
            return "\n".join(lines).strip()

        # 2. Time/Date synthesis
        for t in executed_tools:
            if t.get("name") == "get_current_time":
                res = t.get("result", {})
                loc = res.get("location", "Current location")
                cur_time = res.get("current_time", "")
                cur_date = res.get("current_date", "")
                tz_abbr = res.get("timezone_abbreviation", "")
                tz_name = res.get("resolved_timezone", "")
                return f"The current time in **{loc}** is **{cur_time} {tz_abbr}** ({tz_name}) on **{cur_date}**."
            elif t.get("name") == "get_current_date":
                res = t.get("result", {})
                loc = res.get("location", "Current location")
                cur_date = res.get("current_date", "")
                tz_name = res.get("resolved_timezone", "")
                return f"Today in **{loc}** is **{cur_date}** ({tz_name})."

        # 3. Calculator synthesis
        for t in executed_tools:
            if t.get("name") == "calculator":
                res = t.get("result", {})
                if res.get("status") == "success":
                    expr = res.get("expression", "")
                    val = res.get("result", "")
                    return f"Calculation result: `{expr}` = **{val}**"
                return f"Calculation failed: {res.get('error', 'Unknown math error')}"

        # 4. Memory synthesis
        for t in executed_tools:
            name = t.get("name", "")
            res = t.get("result", {})
            if name == "retrieve_memory":
                if res.get("found"):
                    return f"Stored memory for `{res.get('key')}`: **{res.get('value')}**"
                return f"I do not have `{res.get('key')}` stored in Smṛti."
            elif name in ("save_memory", "delete_memory"):
                return res.get("message", "Updated Smṛti.")

        # 5. Knowledge Base synthesis
        for t in executed_tools:
            if t.get("name") == "search_knowledge":
                res = t.get("result", {})
                if isinstance(res, dict) and res.get("status") == "success":
                    items = res.get("results", [])
                    if items:
                        lines = ["Based on your local Knowledge Base documents:\n"]
                        for it in items[:3]:
                            d_name = it.get("document_name", "Document")
                            passage = it.get("passage", "").strip()
                            lines.append(f"• **[{d_name}]**:\n  {passage}\n")
                        return "\n".join(lines).strip()
                    return "UNKNOWN: The document does not mention the requested information."

        return "Successfully executed tool actions and verified data."

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        start_time = time.perf_counter()
        api_key = self._get_api_key()
        target_model = model or DEFAULT_OPENROUTER_MODELS[0]

        if not api_key:
            return {
                "content": (
                    "⚠️ **OPENROUTER_API_KEY is not configured.**\n\n"
                    "To activate OpenRouter multi-provider access in NARAD:\n"
                    "1. Obtain an API key from OpenRouter: https://openrouter.ai/keys\n"
                    "2. Add `OPENROUTER_API_KEY=your_key_here` to `backend/.env`.\n"
                    "3. Send your directive again."
                ),
                "provider": self.provider_id,
                "model": target_model,
                "status": "unconfigured",
                "is_transient": False,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

        formatted_contents = self._format_messages_for_openrouter(messages)

        # Enforce NARAD system prompt if absent
        has_system = any(m.get("role") == "system" for m in formatted_contents)
        if not has_system:
            from app.core.prompts import build_narad_system_prompt
            system_prompt = build_narad_system_prompt(
                provider_id=self.provider_id,
                model_name=target_model
            )
            formatted_contents.insert(0, {"role": "system", "content": system_prompt})

        # Resolve available tools
        from app.services.kriya import kriya_dispatcher
        available_tools = tools if tools is not None else kriya_dispatcher.get_schemas(format="openai")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "http://127.0.0.1:8000",
            "X-Title": "NARAD AI Core",
            "Content-Type": "application/json"
        }

        MAX_TOOL_ITERATIONS = 5
        iteration = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        executed_tools: List[Dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=45.0) as http_client:
                while iteration < MAX_TOOL_ITERATIONS:
                    iteration += 1

                    payload: Dict[str, Any] = {
                        "model": target_model,
                        "messages": formatted_contents,
                        "temperature": temperature,
                        "max_tokens": max_tokens
                    }
                    if available_tools:
                        payload["tools"] = available_tools
                        payload["tool_choice"] = "auto"

                    response = await http_client.post(OPENROUTER_BASE_URL, headers=headers, json=payload)

                    if response.status_code != 200:
                        err_text = response.text
                        try:
                            err_json = response.json()
                            err_text = err_json.get("error", {}).get("message", response.text)
                        except Exception:
                            pass

                        # V6.1 error classification with fine-grained health states
                        status_code_num = response.status_code
                        if status_code_num in (401, 403):
                            from app.providers.base import HEALTH_AUTH_ERROR
                            is_transient = False
                            status_code = "auth_error"
                            cooldown = 0.0
                            self.record_failure(err_text, is_transient=False, cooldown_seconds=0.0, health_state=HEALTH_AUTH_ERROR)
                        elif status_code_num == 400:
                            is_transient = False
                            status_code = "client_error"
                            cooldown = 0.0
                            self.record_failure(err_text, is_transient=False, cooldown_seconds=0.0)
                        elif status_code_num == 402 or "credit" in err_text.lower():
                            from app.providers.base import HEALTH_QUOTA_EXHAUSTED
                            is_transient = True
                            status_code = "quota_exhausted"
                            cooldown = 120.0
                            self.record_failure(err_text, is_transient=True, cooldown_seconds=cooldown, health_state=HEALTH_QUOTA_EXHAUSTED)
                        elif status_code_num == 429:
                            from app.providers.base import HEALTH_RATE_LIMITED
                            is_transient = True
                            status_code = "rate_limit"
                            cooldown = 60.0
                            self.record_failure(err_text, is_transient=True, cooldown_seconds=cooldown, health_state=HEALTH_RATE_LIMITED)
                        elif status_code_num in (500, 502, 503, 504):
                            from app.providers.base import HEALTH_DEGRADED
                            is_transient = True
                            status_code = "server_error"
                            cooldown = 45.0
                            self.record_failure(err_text, is_transient=True, cooldown_seconds=cooldown, health_state=HEALTH_DEGRADED)
                        else:
                            from app.providers.base import HEALTH_UNAVAILABLE
                            is_transient = status_code_num >= 500
                            status_code = "api_error"
                            cooldown = 30.0 if is_transient else 0.0
                            self.record_failure(err_text, is_transient=is_transient, cooldown_seconds=cooldown, health_state=HEALTH_UNAVAILABLE)
                        latency_ms = int((time.perf_counter() - start_time) * 1000)

                        logger.error(f"OpenRouter returned HTTP {status_code_num} [{status_code}]: {err_text}")
                        return {
                            "content": f"⚠️ **OPENROUTER REQUEST FAILED (HTTP {status_code_num}):** {err_text}",
                            "provider": self.provider_id,
                            "model": target_model,
                            "latency_ms": latency_ms,
                            "status": status_code,
                            "is_transient": is_transient,
                            "error": err_text,
                            "usage": {"prompt_tokens": 0, "completion_tokens": 0}
                        }

                    data = response.json()
                    usage = data.get("usage", {})
                    total_prompt_tokens += usage.get("prompt_tokens", 0)
                    total_completion_tokens += usage.get("completion_tokens", 0)

                    choices = data.get("choices", [])
                    if not choices:
                        break

                    choice = choices[0]
                    message = choice.get("message", {})
                    tool_calls = message.get("tool_calls")

                    if not tool_calls:
                        resp_content = (message.get("content") or "").strip()
                        if resp_content:
                            latency_ms = int((time.perf_counter() - start_time) * 1000)
                            self.record_success(latency_ms)
                            return {
                                "content": resp_content,
                                "provider": self.provider_id,
                                "model": target_model,
                                "latency_ms": latency_ms,
                                "tools_executed": executed_tools,
                                "usage": {
                                    "prompt_tokens": total_prompt_tokens,
                                    "completion_tokens": total_completion_tokens,
                                    "total_tokens": total_prompt_tokens + total_completion_tokens
                                },
                                "status": "success"
                            }
                        break

                    # Append assistant message with tool calls
                    assistant_turn = {
                        "role": "assistant",
                        "content": message.get("content"),
                        "tool_calls": tool_calls
                    }
                    formatted_contents.append(assistant_turn)

                    # Execute tools
                    for tc in tool_calls:
                        tc_id = tc.get("id", f"call_{len(executed_tools)}")
                        fn = tc.get("function", {})
                        fn_name = fn.get("name", "")
                        fn_args_raw = fn.get("arguments", "{}")

                        try:
                            fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                        except Exception:
                            fn_args = {}

                        tool_result = await kriya_dispatcher.execute_tool(fn_name, fn_args)
                        executed_tools.append({
                            "name": fn_name,
                            "arguments": fn_args,
                            "result": tool_result
                        })

                        tool_result_str = json.dumps(tool_result) if isinstance(tool_result, (dict, list)) else str(tool_result)
                        formatted_contents.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": fn_name,
                            "content": tool_result_str
                        })

                # Synthesis pass if tools were executed
                final_text = ""
                if executed_tools:
                    synthesis_directive = (
                        "All requested tool executions are complete. Synthesize a concise, clear final answer for the user "
                        "based strictly on the tool results above. Do NOT call any further tools; output only your final answer."
                    )
                    formatted_contents.append({"role": "user", "content": synthesis_directive})

                    synth_payload = {
                        "model": target_model,
                        "messages": formatted_contents,
                        "temperature": temperature,
                        "max_tokens": min(max_tokens, 512)
                    }
                    try:
                        synth_resp = await http_client.post(OPENROUTER_BASE_URL, headers=headers, json=synth_payload)
                        if synth_resp.status_code == 200:
                            s_data = synth_resp.json()
                            s_choices = s_data.get("choices", [])
                            if s_choices:
                                s_content = s_choices[0].get("message", {}).get("content", "")
                                if s_content and s_content.strip():
                                    final_text = s_content.strip()
                    except Exception as s_err:
                        logger.warning(f"[OpenRouterProvider] Synthesis pass error: {s_err}")

                if not final_text:
                    if executed_tools:
                        final_text = self._build_fallback_synthesis(executed_tools)
                    else:
                        final_text = "I processed your request, but could not produce a text response."

                latency_ms = int((time.perf_counter() - start_time) * 1000)
                self.record_success(latency_ms)

                return {
                    "content": final_text,
                    "provider": self.provider_id,
                    "model": target_model,
                    "latency_ms": latency_ms,
                    "tools_executed": executed_tools,
                    "usage": {
                        "prompt_tokens": total_prompt_tokens,
                        "completion_tokens": total_completion_tokens,
                        "total_tokens": total_prompt_tokens + total_completion_tokens
                    },
                    "status": "success"
                }

        except httpx.TimeoutException as te:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            self.record_failure(str(te), is_transient=True, cooldown_seconds=30.0)
            logger.error(f"OpenRouter request timed out: {te}")
            return {
                "content": f"⚠️ **OPENROUTER REQUEST FAILED (TIMEOUT):** Connection timed out.",
                "provider": self.provider_id,
                "model": target_model,
                "latency_ms": latency_ms,
                "status": "timeout",
                "is_transient": True,
                "error": str(te),
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            err_msg = str(e)
            is_transient = "connect" in err_msg.lower() or "timeout" in err_msg.lower()
            self.record_failure(err_msg, is_transient=is_transient, cooldown_seconds=30.0)
            logger.error(f"OpenRouter unexpected exception: {e}", exc_info=True)
            return {
                "content": f"⚠️ **OPENROUTER REQUEST FAILED:** {err_msg}",
                "provider": self.provider_id,
                "model": target_model,
                "latency_ms": latency_ms,
                "status": "api_error",
                "is_transient": is_transient,
                "error": err_msg,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

    async def stream_response(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        result = await self.generate_response(messages, model, temperature, max_tokens, **kwargs)
        words = result.get("content", "").split(" ")
        for word in words:
            yield word + " "
            await asyncio.sleep(0.01)
