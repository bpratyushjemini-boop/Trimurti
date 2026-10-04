import os
import time
import re
import asyncio
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator

from app.providers.base import BaseLLMProvider
from app.core.config import settings

logger = logging.getLogger(__name__)

class GroqProvider(BaseLLMProvider):
    """
    Groq LPU Inference Engine provider implementation for NARAD Core.
    High-throughput, ultra-low-latency execution of open models (default: openai/gpt-oss-120b).
    Uses the official groq Python SDK.
    """

    def __init__(self):
        super().__init__()

    @property
    def provider_id(self) -> str:
        return "groq"

    @property
    def display_name(self) -> str:
        return "Groq LPU"

    def get_available_models(self) -> List[str]:
        return [
            "openai/gpt-oss-120b",
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant"
        ]

    def _get_api_key(self) -> str:
        # 1. Check on-disk backend/.env first using dotenv_values (guarantees latest key from disk)
        try:
            from dotenv import dotenv_values
            from app.core.config import BACKEND_ENV_PATH, ROOT_ENV_PATH
            for env_path in [BACKEND_ENV_PATH, ROOT_ENV_PATH]:
                if env_path.is_file() and env_path.stat().st_size > 0:
                    vals = dotenv_values(env_path)
                    disk_key = (vals.get("GROQ_API_KEY") or "").strip().strip('"\'')
                    if disk_key:
                        settings.GROQ_API_KEY = disk_key
                        os.environ["GROQ_API_KEY"] = disk_key
                        return disk_key
        except Exception:
            pass

        # 2. Fall back to in-memory settings / process environment
        key = (settings.GROQ_API_KEY or os.environ.get("GROQ_API_KEY", "")).strip().strip('"\'')
        if key:
            return key

        return ""

    def is_configured(self) -> bool:
        return bool(self._get_api_key())

    def _format_messages_for_groq(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert standard messages into Groq's OpenAI-compatible schema:
        [{role: 'system' | 'user' | 'assistant' | 'tool', ...}]
        """
        formatted = []
        for m in messages:
            role = str(m.get("role", "user")).lower().strip()

            # Handle tool execution result messages
            if role == "tool":
                formatted.append({
                    "role": "tool",
                    "tool_call_id": str(m.get("tool_call_id", "")),
                    "name": str(m.get("name", "")),
                    "content": str(m.get("content", ""))
                })
                continue

            content = m.get("content")

            # Handle assistant messages (which may contain tool_calls)
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

            if content is None or (isinstance(content, str) and not content.strip()):
                continue

            formatted.append({
                "role": clean_role,
                "content": str(content).strip()
            })

        # Ensure at least one user message if list is empty
        if not formatted:
            formatted.append({"role": "user", "content": "Hello"})

        return formatted

    def _build_fallback_synthesis(self, executed_tools: List[Dict[str, Any]]) -> str:
        """
        Builds an authoritative natural-language answer directly from executed tool results
        when the model completion fails to emit content. Combines, deduplicates, and formats
        verified citations and claims without fabricating sources.
        """
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

        # 2. Time and date synthesis
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
                else:
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
                    else:
                        return "UNKNOWN: The document does not mention the requested information."
                elif isinstance(res, dict) and res.get("status") == "empty":
                    return "UNKNOWN: The document does not mention the requested information."

        return "Successfully executed tool actions and verified data."

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        start_time = time.perf_counter()
        api_key = self._get_api_key()
        target_model = model or settings.NARAD_DEFAULT_MODEL or "openai/gpt-oss-120b"

        # Check configuration
        if not api_key:
            return {
                "content": (
                    "⚠️ **GROQ_API_KEY is not configured.**\n\n"
                    "To activate ultra-fast Groq LPU inference in NARAD:\n"
                    "1. Obtain an API key from Groq Console: https://console.groq.com/keys\n"
                    "2. Update `backend/.env` with:\n"
                    "   `GROQ_API_KEY=your_actual_key_here`\n"
                    "3. Send your message again.\n\n"
                    "*All API keys remain strictly local in your private environment vault.*"
                ),
                "provider": self.provider_id,
                "model": target_model,
                "status": "unconfigured",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

        formatted_contents = self._format_messages_for_groq(messages)

        # Enforce NARAD system prompt if not already present
        has_system = any(m.get("role") == "system" for m in formatted_contents)
        if not has_system:
            from app.core.prompts import build_narad_system_prompt
            system_prompt = build_narad_system_prompt(
                provider_id=self.provider_id,
                model_name=target_model
            )
            formatted_contents.insert(0, {"role": "system", "content": system_prompt})

        # Resolve available tools from Krīya dispatcher or kwargs
        from app.services.kriya import kriya_dispatcher
        available_tools = tools if tools is not None else kriya_dispatcher.get_schemas(format="openai")

        MAX_TOOL_ITERATIONS = 5
        iteration = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        executed_tools: List[Dict[str, Any]] = []

        try:
            import json
            from groq import Groq

            client = Groq(api_key=api_key, max_retries=1, timeout=20.0)

            while iteration < MAX_TOOL_ITERATIONS:
                iteration += 1

                call_kwargs = {
                    "model": target_model,
                    "messages": formatted_contents,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }

                # Supply available tools with tool_choice="auto"
                if available_tools:
                    call_kwargs["tools"] = available_tools
                    call_kwargs["tool_choice"] = "auto"

                # Run blocking SDK call in worker thread pool with rate-limit backoff retry
                from groq import RateLimitError
                retries = 0
                while True:
                    try:
                        response = await asyncio.to_thread(
                            client.chat.completions.create,
                            **call_kwargs
                        )
                        break
                    except RateLimitError as rle:
                        err_str = str(rle).lower()
                        # If daily token quota reached on 120b, auto-switch to 20b model with independent quota
                        if "tokens per day" in err_str and call_kwargs.get("model") == "openai/gpt-oss-120b":
                            logger.warning(
                                "[GroqProvider] Daily token limit reached for openai/gpt-oss-120b. "
                                "Auto-switching to openai/gpt-oss-20b (separate quota)..."
                            )
                            target_model = "openai/gpt-oss-20b"
                            call_kwargs["model"] = "openai/gpt-oss-20b"
                            continue

                        # If token per day quota exceeded due to conservative token reservation, lower reservation once
                        cur_max = call_kwargs.get("max_tokens", 512)
                        if "tokens per day" in err_str and cur_max > 128:
                            if cur_max > 512:
                                call_kwargs["max_tokens"] = 512
                            elif cur_max > 256:
                                call_kwargs["max_tokens"] = 256
                            else:
                                call_kwargs["max_tokens"] = 128
                            logger.info(f"[GroqProvider] Adjusted max_tokens to {call_kwargs['max_tokens']} to fit within remaining token quota.")
                            continue

                        retries += 1
                        if retries > 2:
                            raise
                        wait_sec = 2.0 * retries
                        try:
                            msg = str(rle)
                            m_time = re.search(r'try again in (?:(\d+)m)?([\d\.]+)s', msg)
                            if m_time:
                                mins = float(m_time.group(1) or 0)
                                secs = float(m_time.group(2) or 0)
                                wait_sec = min(mins * 60.0 + secs + 0.5, 10.0)
                        except Exception:
                            pass
                        logger.warning(f"[GroqProvider] Rate limit hit (retry {retries}/2). Waiting {wait_sec:.1f}s...")
                        await asyncio.sleep(wait_sec)

                if hasattr(response, "usage") and response.usage:
                    total_prompt_tokens += getattr(response.usage, "prompt_tokens", 0) or 0
                    total_completion_tokens += getattr(response.usage, "completion_tokens", 0) or 0

                choice = response.choices[0] if response.choices else None
                if not choice or not choice.message:
                    break

                message = choice.message
                tool_calls = getattr(message, "tool_calls", None)

                # If no tool calls, model provided normal text answer
                if not tool_calls:
                    response_text = (message.content or "").strip()
                    # If model returned text, return immediately
                    if response_text:
                        latency_ms = int((time.perf_counter() - start_time) * 1000)
                        self.record_success(latency_ms)
                        return {
                            "content": response_text,
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
                    # If no text returned and no tool calls, exit loop to fallback
                    break

                # Model invoked tools: preserve assistant message with tool_calls in history
                logger.info(
                    f"Groq iteration {iteration}: model requested {len(tool_calls)} tool call(s): "
                    f"{[tc.function.name for tc in tool_calls]}"
                )

                assistant_turn = {
                    "role": "assistant",
                    "content": message.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in tool_calls
                    ]
                }
                formatted_contents.append(assistant_turn)

                # Execute each tool call and append role="tool" message
                for tc in tool_calls:
                    tool_call_id = tc.id
                    fn_name = tc.function.name
                    fn_args_raw = tc.function.arguments

                    try:
                        if isinstance(fn_args_raw, str):
                            fn_args = json.loads(fn_args_raw) if fn_args_raw.strip() else {}
                        elif isinstance(fn_args_raw, dict):
                            fn_args = fn_args_raw
                        else:
                            fn_args = {}
                    except Exception as e:
                        logger.warning(f"Could not parse arguments for tool {fn_name}: {e}")
                        fn_args = {"raw_input": fn_args_raw}

                    # Execute safely through Krīya tool dispatcher
                    tool_result = await kriya_dispatcher.execute_tool(fn_name, fn_args)
                    executed_tools.append({
                        "name": fn_name,
                        "arguments": fn_args,
                        "result": tool_result
                    })

                    if isinstance(tool_result, (dict, list)):
                        tool_result_str = json.dumps(tool_result)
                    else:
                        tool_result_str = str(tool_result)

                    formatted_contents.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": fn_name,
                        "content": tool_result_str
                    })

            # If tools were executed, ensure a final synthesized answer is produced
            final_text = ""
            if executed_tools:
                logger.info(f"[GroqProvider] Invoking dedicated synthesis pass for {len(executed_tools)} executed tool(s)...")

                has_kb = any(t.get("name") == "search_knowledge" for t in executed_tools)
                has_web = any(t.get("name") == "web_search" for t in executed_tools)

                if has_kb and not has_web:
                    synthesis_directive = (
                        "All requested local document searches are complete. Synthesize your final answer "
                        "for the user based strictly on the retrieved document passages above. "
                        "State the exact facts found and cite the document name. "
                        "If the requested fact is NOT mentioned in the retrieved passages, state: "
                        "'UNKNOWN: The document does not mention [topic]'. "
                        "Do NOT invent or extrapolate facts. Do NOT call any further tools; output only your final answer."
                    )
                elif has_web:
                    synthesis_directive = (
                        "All requested searches and tool executions are complete. Synthesize a comprehensive, "
                        "natural-language final answer for the user based strictly on the retrieved results above. "
                        "Include real source domain names and URLs for all relevant claims, combine and deduplicate "
                        "findings if multiple searches were performed, and clearly distinguish verified web information "
                        "from your analysis. Do NOT call any further tools; output only your final synthesized answer."
                    )
                else:
                    synthesis_directive = (
                        "All requested tool executions are complete. Synthesize a concise, clear final answer for the user "
                        "based strictly on the tool results above. Do NOT call any further tools; output only your final answer."
                    )

                formatted_contents.append({
                    "role": "user",
                    "content": synthesis_directive
                })

                synth_kwargs = {
                    "model": target_model,
                    "messages": formatted_contents,
                    "temperature": temperature,
                    "max_tokens": min(max_tokens, 400)
                }
                if available_tools:
                    synth_kwargs["tools"] = available_tools
                    synth_kwargs["tool_choice"] = "auto"

                try:
                    synth_resp = await asyncio.to_thread(
                        client.chat.completions.create,
                        **synth_kwargs
                    )
                    if hasattr(synth_resp, "usage") and synth_resp.usage:
                        total_prompt_tokens += getattr(synth_resp.usage, "prompt_tokens", 0) or 0
                        total_completion_tokens += getattr(synth_resp.usage, "completion_tokens", 0) or 0

                    if synth_resp.choices and synth_resp.choices[0].message:
                        synth_msg = synth_resp.choices[0].message
                        if synth_msg.content and synth_msg.content.strip():
                            final_text = synth_msg.content.strip()
                except Exception as synth_err:
                    logger.warning(f"[GroqProvider] Synthesis completion call encountered error: {synth_err}")

            # Fallback synthesis: if final_text is still empty, synthesize directly from executed tools
            if not final_text:
                if executed_tools:
                    final_text = self._build_fallback_synthesis(executed_tools)
                elif choice and choice.message and choice.message.content:
                    final_text = choice.message.content.strip()
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

        except Exception as err:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            error_msg = str(err)
            err_lower = error_msg.lower()

            # V6.1 error classification with fine-grained health states:
            # 401/403 Auth    → AUTH_ERROR  (permanent, no failover, no cooldown)
            # 429 Rate Limit  → RATE_LIMITED (transient, short cooldown)
            # Quota Exhausted → QUOTA_EXHAUSTED (transient, long cooldown)
            # Timeout/Network → UNAVAILABLE (transient)
            # 500/5xx Server  → DEGRADED (transient)
            # 400 Bad Request → non-transient client bug (expose, no failover)
            is_auth  = "401" in error_msg or "403" in error_msg or "invalid_api_key" in err_lower or "authentication" in err_lower
            is_400   = "400" in error_msg or "bad request" in err_lower or "invalid_request_error" in err_lower
            is_quota = "tokens per day" in err_lower or ("quota" in err_lower and "429" not in error_msg)
            is_429   = "429" in error_msg or "rate limit" in err_lower or "rate_limit" in err_lower
            is_timeout = "timeout" in err_lower or "timed out" in err_lower or "connection" in err_lower
            is_5xx = any(code in error_msg for code in ["500", "502", "503", "504"]) or "server error" in err_lower

            if is_auth:
                from app.providers.base import HEALTH_AUTH_ERROR
                is_transient = False
                status_code = "auth_error"
                cooldown = 0.0
                self.record_failure(error_msg, is_transient=False, cooldown_seconds=0.0, health_state=HEALTH_AUTH_ERROR)
            elif is_quota:
                from app.providers.base import HEALTH_QUOTA_EXHAUSTED
                is_transient = True
                status_code = "quota_exhausted"
                cooldown = 86400.0  # 24h
                self.record_failure(error_msg, is_transient=True, cooldown_seconds=cooldown, health_state=HEALTH_QUOTA_EXHAUSTED)
            elif is_400:
                is_transient = False
                status_code = "client_error"
                cooldown = 0.0
                self.record_failure(error_msg, is_transient=False, cooldown_seconds=0.0)
            elif is_429:
                from app.providers.base import HEALTH_RATE_LIMITED
                is_transient = True
                status_code = "rate_limit"
                cooldown = 60.0
                self.record_failure(error_msg, is_transient=True, cooldown_seconds=cooldown, health_state=HEALTH_RATE_LIMITED)
            elif is_timeout:
                from app.providers.base import HEALTH_UNAVAILABLE
                is_transient = True
                status_code = "timeout"
                cooldown = 30.0
                self.record_failure(error_msg, is_transient=True, cooldown_seconds=cooldown, health_state=HEALTH_UNAVAILABLE)
            elif is_5xx:
                from app.providers.base import HEALTH_DEGRADED
                is_transient = True
                status_code = "server_error"
                cooldown = 45.0
                self.record_failure(error_msg, is_transient=True, cooldown_seconds=cooldown, health_state=HEALTH_DEGRADED)
            else:
                from app.providers.base import HEALTH_UNAVAILABLE
                is_transient = True
                status_code = "api_error"
                cooldown = 30.0
                self.record_failure(error_msg, is_transient=True, cooldown_seconds=cooldown, health_state=HEALTH_UNAVAILABLE)

            logger.error(f"Groq API call failed [{status_code}, transient={is_transient}]: {error_msg}", exc_info=True)

            return {
                "content": f"⚠️ **GROQ REQUEST FAILED ({status_code.upper()}):** {error_msg}",
                "provider": self.provider_id,
                "model": target_model,
                "latency_ms": latency_ms,
                "status": status_code,
                "is_transient": is_transient,
                "error": error_msg,
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
            await asyncio.sleep(0.01)
