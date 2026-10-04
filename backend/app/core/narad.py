"""
NARAD V3.1 — Core Intelligence Orchestration & Intelligent Failover Engine.
Handles conversation context windowing, task-aware model routing,
automatic failover on transient failures (429, timeouts, 5xx),
strict non-failover on 400 client bugs, Smṛti memory integration,
and complete self-awareness telemetry reporting.
"""

import time
import asyncio
import logging
from typing import List, Dict, Any, Optional

from app.core.router import model_router
from app.providers.manager import provider_manager

logger = logging.getLogger(__name__)

# Sliding context window limit (number of recent messages to retain in active prompt)
CONVERSATION_WINDOW_LIMIT = 12


class NaradCore:
    """
    NARAD Core Intelligence Orchestration Service.
    Acts as the single point of entry for conversational synthesis:
    1. Receives directive / message & session context
    2. Applies sliding conversation window
    3. Consults Model Router for task classification & failover chain
    4. Enforces authoritative system prompt with Smṛti persistent facts
    5. Dispatches query to primary provider
    6. Executes automated failover on transient errors (429/timeouts/5xx)
    7. Emits rich self-awareness telemetry (route reason, fallback path, latency)
    """

    async def process_message(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        session_id: Optional[str] = None,
        requested_provider: Optional[str] = None,
        requested_model: Optional[str] = None,
        is_voice: bool = False
    ) -> Dict[str, Any]:
        overall_start_time = time.perf_counter()
        clean_message = message.strip()
        if not clean_message:
            return {
                "response": "Directive cannot be empty.",
                "provider": "narad-core",
                "model": "none",
                "execution_mode": "local",
                "execution": "local",
                "endpoint": "local://narad-subsystem",
                "latency_ms": 0,
                "latency": 0,
                "status": "validation_error",
                "fallback_used": False,
                "fallback": False,
                "fallback_path": None,
                "fallback_reason": None,
                "route_reason": "none",
                "why_this_choice": "Local validation of directive.",
                "tools_executed": [],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

        # 1. Retrieve prior context from Smriti if session_id is provided and history not explicit
        if history is None and session_id:
            try:
                from app.services.smriti import smriti_service
                history = smriti_service.get_conversation_history(session_id=session_id)
            except Exception as smriti_err:
                logger.warning(f"[Smriti] Could not load context for session {session_id}: {smriti_err}")
                history = []

        # 2. Apply Sliding Window Strategy for Conversation Context (Phase 7 & 8)
        # Keeps recent turns for multi-turn pronouns & follow-ups ("that", "it", "continue")
        # without overflowing model context.
        messages: List[Dict[str, str]] = []
        if history:
            # Take only the last CONVERSATION_WINDOW_LIMIT turns
            windowed_history = history[-CONVERSATION_WINDOW_LIMIT:]
            messages.extend(windowed_history)

        # Ensure current message is at the end of the context
        if not messages or messages[-1].get("content") != clean_message or messages[-1].get("role") != "user":
            messages.append({"role": "user", "content": clean_message})

        # =====================================================================
        # NARAD Phase 2: Authoritative Runtime Truth (0 LLM tokens, 0 hallucination)
        # Truth-first ground state for identity, models, locality, and capabilities
        # =====================================================================
        from app.services.runtime_truth import runtime_truth_service
        runtime_res = runtime_truth_service.resolve_runtime_query(
            clean_message,
            session_id=session_id,
            requested_provider=requested_provider,
            requested_model=requested_model,
        )
        if runtime_res:
            return runtime_res

        # =====================================================================
        # Phase 2: Local-First Deterministic Micro-Tasks (0 LLM tokens, <5ms)
        # =====================================================================
        if not requested_provider:
            from app.services.micro_tasks import micro_task_service
            micro_res = micro_task_service.resolve(clean_message, is_voice=is_voice)
            if micro_res:
                micro_res["execution_mode"] = "local"
                micro_res["execution"] = "local"
                micro_res["endpoint"] = "local://deterministic-engine"
                micro_res["latency"] = micro_res.get("latency_ms", 0)
                micro_res["fallback_used"] = False
                micro_res["why_this_choice"] = (
                    "Deterministic local micro-task engine executed on-device without model tokens."
                )
                return micro_res

        # =====================================================================
        # Smṛti 3.0: Direct Natural-Language Memory Directives (0 LLM tokens, 0 hallucination)
        # Handles "Remember that...", "Forget that...", "What do you remember about me?",
        # "Show my memories about NARAD", "Show my stored preferences" deterministically.
        # =====================================================================
        if not requested_provider:
            from app.services.smriti import smriti_service
            mem_cmd = smriti_service.handle_memory_command(clean_message)
            if mem_cmd and mem_cmd.get("handled"):
                total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
                return {
                    "response": mem_cmd["response"],
                    "provider": "smriti",
                    "model": "smriti-v3-memory-engine",
                    "execution_mode": "local",
                    "execution": "local",
                    "endpoint": "local://smriti-memory-engine",
                    "network_required": False,
                    "latency_ms": total_latency_ms,
                    "latency": total_latency_ms,
                    "status": "success",
                    "fallback_used": False,
                    "fallback": False,
                    "fallback_path": None,
                    "fallback_reason": None,
                    "route_reason": "MEMORY_DIRECTIVE",
                    "why_this_choice": "Executed deterministic Smṛti memory command locally without model tokens.",
                    "execution_constraint": "LOCAL_ONLY",
                    "tools_executed": [],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0}
                }

        # =====================================================================
        # Agent Brain: Operational Mode Directives (LOCAL_ONLY / OFFLINE / AUTO)
        # =====================================================================
        msg_normalized = clean_message.strip().rstrip(".!?").lower()
        if msg_normalized.startswith("narad, "):
            msg_normalized = msg_normalized[7:].strip()
        elif msg_normalized.startswith("narad "):
            msg_normalized = msg_normalized[6:].strip()

        # Check for standalone mode switch commands (not queries that just specify local inference)
        is_mode_switch = msg_normalized in (
            "use local-only inference", "use local only inference", "switch to local-only",
            "switch to local-only mode", "set mode local_only", "enable local-only mode",
            "local-only inference", "local only inference", "mode local_only", "go local-only"
        )

        if is_mode_switch:
            from app.services.agent_brain import agent_brain, RuntimeMode
            agent_brain.set_mode(RuntimeMode.LOCAL_ONLY)
            total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
            return {
                "response": "Switched to LOCAL_ONLY mode. All external cloud APIs, cloud models, and web access are now blocked. Using on-device Ollama and local tools only.",
                "provider": "ollama",
                "model": "qwen3.5:0.8b",
                "execution_mode": "local",
                "execution": "local",
                "endpoint": "local://ollama",
                "network_required": False,
                "latency_ms": total_latency_ms,
                "latency": total_latency_ms,
                "status": "success",
                "fallback_used": False,
                "fallback": False,
                "fallback_path": None,
                "fallback_reason": None,
                "route_reason": "LOCAL_MODE_ENABLED",
                "why_this_choice": "User requested LOCAL_ONLY operational mode.",
                "execution_constraint": "LOCAL_ONLY",
                "tools_executed": [],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

        is_offline_switch = msg_normalized in (
            "use offline mode", "switch to offline", "enable offline mode", "go offline",
            "offline mode", "set mode offline"
        )
        if is_offline_switch:
            from app.services.agent_brain import agent_brain, RuntimeMode
            agent_brain.set_mode(RuntimeMode.OFFLINE)
            total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
            return {
                "response": "Switched to OFFLINE mode. Network access, cloud models, and web-dependent tools are completely blocked.",
                "provider": "narad-core",
                "model": "offline-core",
                "execution_mode": "local",
                "execution": "local",
                "endpoint": "local://offline-core",
                "network_required": False,
                "latency_ms": total_latency_ms,
                "latency": total_latency_ms,
                "status": "success",
                "fallback_used": False,
                "fallback": False,
                "fallback_path": None,
                "fallback_reason": None,
                "route_reason": "OFFLINE_MODE_ENABLED",
                "why_this_choice": "User requested OFFLINE operational mode.",
                "execution_constraint": "OFFLINE",
                "tools_executed": [],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

        # Check Active Mode Blockage (LOCAL_ONLY / OFFLINE)
        from app.services.agent_brain import agent_brain, RuntimeMode
        current_op_mode = agent_brain.get_mode()

        if current_op_mode == RuntimeMode.LOCAL_ONLY and requested_provider and requested_provider not in ("ollama", "local"):
            total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
            return {
                "response": "LOCAL_ONLY_BLOCKED: Cloud provider inference is blocked because NARAD is in LOCAL_ONLY mode.",
                "provider": "ollama",
                "model": "qwen3.5:0.8b",
                "execution_mode": "local",
                "execution": "local",
                "endpoint": "local://ollama",
                "network_required": False,
                "latency_ms": total_latency_ms,
                "latency": total_latency_ms,
                "status": "blocked",
                "fallback_used": False,
                "fallback": False,
                "fallback_path": None,
                "fallback_reason": None,
                "route_reason": "LOCAL_ONLY_BLOCKED",
                "why_this_choice": "Strict LOCAL_ONLY mode prohibits remote cloud requests.",
                "tools_executed": [],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

        if current_op_mode == RuntimeMode.OFFLINE and requested_provider and requested_provider not in ("ollama", "local"):
            total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
            return {
                "response": "OFFLINE_BLOCKED: Cloud provider inference is blocked because NARAD is in OFFLINE mode.",
                "provider": "narad-core",
                "model": "offline-core",
                "execution_mode": "local",
                "execution": "local",
                "endpoint": "local://offline-core",
                "network_required": False,
                "latency_ms": total_latency_ms,
                "latency": total_latency_ms,
                "status": "blocked",
                "fallback_used": False,
                "fallback": False,
                "fallback_path": None,
                "fallback_reason": None,
                "route_reason": "OFFLINE_BLOCKED",
                "why_this_choice": "Strict OFFLINE mode prohibits network access.",
                "tools_executed": [],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

        # =====================================================================
        # NARAD V6 Autonomous Task Engine — Conversational Directives & Controls
        # =====================================================================
        msg_l = clean_message.lower()

        # 1. Natural Task Control: Pause
        if msg_l in ("pause", "pause task", "pause the task"):
            from app.services.task_engine import autonomous_task_engine, TaskStatus
            active = autonomous_task_engine.get_active_task()
            if active and active.status in (TaskStatus.EXECUTING, TaskStatus.WAITING_FOR_PERMISSION, TaskStatus.PLANNING):
                autonomous_task_engine.pause_task(active.task_id)
                total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
                return {
                    "response": f"Task '{active.objective}' has been paused. Say 'resume' or 'continue' whenever you wish to proceed.",
                    "provider": "task-engine",
                    "model": "autonomous-agent-v6",
                    "execution_mode": "local",
                    "execution": "local",
                    "endpoint": "local://autonomous-agent-v6",
                    "latency_ms": total_latency_ms,
                    "latency": total_latency_ms,
                    "status": "success",
                    "fallback_used": False,
                    "fallback": False,
                    "fallback_path": None,
                    "fallback_reason": None,
                    "route_reason": "task_control_pause",
                    "why_this_choice": "Executed on-device via Task Engine control policy (pause).",
                    "task_id": active.task_id,
                }

        # 2. Natural Task Control: Resume
        if msg_l in ("resume", "continue", "keep going", "proceed"):
            from app.services.task_engine import autonomous_task_engine, TaskStatus
            active = autonomous_task_engine.get_active_task()
            if active and active.status == TaskStatus.PAUSED:
                autonomous_task_engine.resume_task(active.task_id)
                total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
                return {
                    "response": f"Resumed execution of task '{active.objective}'.",
                    "provider": "task-engine",
                    "model": "autonomous-agent-v6",
                    "execution_mode": "local",
                    "execution": "local",
                    "endpoint": "local://autonomous-agent-v6",
                    "latency_ms": total_latency_ms,
                    "latency": total_latency_ms,
                    "status": "success",
                    "fallback_used": False,
                    "fallback": False,
                    "fallback_path": None,
                    "fallback_reason": None,
                    "route_reason": "task_control_resume",
                    "why_this_choice": "Executed on-device via Task Engine control policy (resume).",
                    "task_id": active.task_id,
                }

        # 3. Natural Task Control: Cancel / Stop
        is_cancel_request = (
            msg_l in ("cancel", "cancel that", "actually, don't do that", "cancel task", "stop task") or
            any(p in msg_l for p in ("cancel an active task", "cancel active task", "cancel the active task", "stop the active task")) or
            (msg_l == "stop" and not is_voice)
        )
        if is_cancel_request:
            from app.services.task_engine import autonomous_task_engine, TaskStatus
            from app.services.agent_brain import agent_brain
            agent_brain.cancel_active_tasks(reason="User cancelled via chat directive")
            active = autonomous_task_engine.get_active_task()
            if active and active.status in (TaskStatus.EXECUTING, TaskStatus.PAUSED, TaskStatus.WAITING_FOR_PERMISSION, TaskStatus.PLANNING):
                autonomous_task_engine.cancel_task(active.task_id, reason="User cancelled via chat directive")
                total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
                return {
                    "response": f"TASK_CANCELLED: Task '{active.objective}' has been cancelled. System returned to safe state.",
                    "provider": "task-engine",
                    "model": "autonomous-agent-v6",
                    "execution_mode": "local",
                    "execution": "local",
                    "endpoint": "local://autonomous-agent-v6",
                    "latency_ms": total_latency_ms,
                    "latency": total_latency_ms,
                    "status": "TASK_CANCELLED",
                    "fallback_used": False,
                    "fallback": False,
                    "fallback_path": None,
                    "fallback_reason": None,
                    "route_reason": "TASK_CANCELLED",
                    "why_this_choice": "Executed on-device via Task Engine control policy (cancel).",
                    "task_id": active.task_id,
                }
            total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
            return {
                "response": "TASK_CANCELLED: Active task has been stopped and returned to safe idle state.",
                "provider": "task-engine",
                "model": "autonomous-agent-v6",
                "execution_mode": "local",
                "execution": "local",
                "endpoint": "local://autonomous-agent-v6",
                "latency_ms": total_latency_ms,
                "latency": total_latency_ms,
                "status": "TASK_CANCELLED",
                "fallback_used": False,
                "fallback": False,
                "fallback_path": None,
                "fallback_reason": None,
                "route_reason": "TASK_CANCELLED",
                "why_this_choice": "Executed on-device via Task Engine control policy (cancel).",
            }

        # 4. Natural Task Control: Skip step
        if msg_l in ("skip", "skip step", "skip that step", "skip that", "skip this"):
            from app.services.task_engine import autonomous_task_engine, TaskStatus
            active = autonomous_task_engine.get_active_task()
            if active and active.status in (TaskStatus.EXECUTING, TaskStatus.WAITING_FOR_PERMISSION):
                res = autonomous_task_engine.skip_step(active.task_id)
                total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
                return {
                    "response": f"Skipped step '{res.get('step_id')}'. Continuing with task.",
                    "provider": "task-engine",
                    "model": "autonomous-agent-v6",
                    "execution_mode": "local",
                    "execution": "local",
                    "endpoint": "local://autonomous-agent-v6",
                    "latency_ms": total_latency_ms,
                    "latency": total_latency_ms,
                    "status": "success",
                    "fallback_used": False,
                    "fallback": False,
                    "fallback_path": None,
                    "fallback_reason": None,
                    "route_reason": "task_control_skip",
                    "why_this_choice": "Executed on-device via Task Engine control policy (skip).",
                    "task_id": active.task_id,
                }

        # 5. Natural Task Control: Status enquiry
        if any(p == msg_l or msg_l.startswith(p) for p in ("what's happening?", "what is happening?", "what are you doing?", "task status", "why did you stop?")):
            from app.services.task_engine import autonomous_task_engine, TaskStatus
            active = autonomous_task_engine.get_active_task()
            if active:
                step_desc = ""
                if 0 <= active.current_step_index < len(active.steps):
                    curr = active.steps[active.current_step_index]
                    step_desc = f" Currently on step {active.current_step_index + 1}/{len(active.steps)}: '{curr.title}' ({curr.status})."
                waiting_desc = ""
                if active.status == TaskStatus.WAITING_FOR_PERMISSION and active.pending_confirmation:
                    waiting_desc = f" Awaiting approval for: {active.pending_confirmation.get('action_summary')}."

                total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
                return {
                    "response": f"Active task '{active.objective}' is {active.status.value}.{step_desc}{waiting_desc}",
                    "provider": "task-engine",
                    "model": "autonomous-agent-v6",
                    "execution_mode": "local",
                    "execution": "local",
                    "endpoint": "local://autonomous-agent-v6",
                    "latency_ms": total_latency_ms,
                    "latency": total_latency_ms,
                    "status": "success",
                    "fallback_used": False,
                    "fallback": False,
                    "fallback_path": None,
                    "fallback_reason": None,
                    "route_reason": "task_control_status",
                    "why_this_choice": "Executed on-device via Task Engine telemetry query.",
                    "task_id": active.task_id,
                    "task": active.to_dict(),
                }

        # 6. Natural Task Control: Confirmation decision
        if msg_l in ("allow", "allow once", "approve", "allow this task", "allow for this task", "deny") and not requested_provider:
            from app.services.task_engine import autonomous_task_engine, TaskStatus
            active = autonomous_task_engine.get_active_task()
            if active and active.status == TaskStatus.WAITING_FOR_PERMISSION and active.pending_confirmation:
                conf_id = active.pending_confirmation.get("confirmation_id")
                decision = "allow_task" if "for this task" in msg_l or "this task" in msg_l else ("deny" if "deny" in msg_l else "allow")
                res = autonomous_task_engine.handle_confirmation_decision(conf_id, decision, task_id=active.task_id)
                total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
                return {
                    "response": f"Permission decision '{decision}' recorded for action '{res.get('action_summary')}'. Resuming task execution.",
                    "provider": "task-engine",
                    "model": "autonomous-agent-v6",
                    "execution_mode": "local",
                    "execution": "local",
                    "endpoint": "local://autonomous-agent-v6",
                    "latency_ms": total_latency_ms,
                    "latency": total_latency_ms,
                    "status": "success",
                    "fallback_used": False,
                    "fallback": False,
                    "fallback_path": None,
                    "fallback_reason": None,
                    "route_reason": "permission_decision",
                    "why_this_choice": f"Executed on-device security policy decision: {decision}.",
                    "task_id": active.task_id,
                }

        # 7. Autonomous Multi-Step Objectives (V6 Engine)
        is_autonomous_objective = any(w in msg_l for w in (
            "prepare my development environment", "start my narad development environment",
            "prepare dev environment", "set up development environment", "launch my dev environment",
            "check why frontend build is failing", "investigate why frontend build is failing",
            "diagnose frontend build", "check my narad project and tell me what is wrong",
            "inspect my project and tell me what's wrong", "inspect my project and tell me what is wrong",
            "inspect my project", "inspect project",
            "diagnose my narad project", "prepare the project for a production build",
            "prepare project for production build", "run production build pipeline",
        ))
        if is_autonomous_objective and not requested_provider:
            from app.services.task_engine import autonomous_task_engine, TaskStatus
            task = await autonomous_task_engine.create_and_start_task(clean_message)

            # Wait for execution loop or permission pause (up to 45s for chat response)
            runner = autonomous_task_engine._running_tasks.get(task.task_id)
            if runner:
                while not runner.done() and task.status in (
                    TaskStatus.PLANNING, TaskStatus.EXECUTING, TaskStatus.OBSERVING,
                    TaskStatus.VERIFYING, TaskStatus.RECOVERING
                ):
                    await asyncio.sleep(0.3)

            total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
            summary_msg = task.summary or f"Task is in status '{task.status.value}'."
            if task.status == TaskStatus.WAITING_FOR_PERMISSION and task.pending_confirmation:
                conf = task.pending_confirmation
                summary_msg = (
                    f"Task paused awaiting your permission: {conf.get('action_summary')}. "
                    f"Please confirm in HUD or say 'allow', 'allow for this task', or 'deny'."
                )

            return {
                "response": summary_msg,
                "provider": "task-engine",
                "model": "autonomous-agent-v6",
                "execution_mode": "local",
                "execution": "local",
                "endpoint": "local://autonomous-agent-v6",
                "latency_ms": total_latency_ms,
                "latency": total_latency_ms,
                "status": "success" if task.status == TaskStatus.COMPLETED else task.status.value.lower(),
                "fallback_used": False,
                "fallback": False,
                "fallback_path": None,
                "fallback_reason": None,
                "route_reason": "autonomous_multi_step_task",
                "why_this_choice": "Executed on-device via Task Engine autonomous multi-step loop.",
                "tools_executed": [
                    {"tool": s.tool_name, "status": s.status}
                    for s in task.steps if s.status in ("completed", "executing", "failed")
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                "task_id": task.task_id,
                "task": task.to_dict(),
                "plan": [s.to_dict() for s in task.steps],
                "honest_report": task.honest_report,
            }

        # Direct Computer Control via Manthan Planner (V4/V5 Trinetra / V8.1 Computer Execution)
        is_direct_computer_cmd = (
            ("music" in msg_l and any(w in msg_l for w in ("play", "back in black", "song", "track"))) or
            (msg_l.startswith("open ") and any(app in msg_l for app in ("calculator", "music", "safari", "chrome", "firefox", "terminal", "finder", "vs code", "settings"))) or
            any(p in msg_l for p in ("take screenshot", "take a screenshot", "inspect screen", "look at my screen", "what's on my screen", "what is on my screen", "read screen", "check screen", "is there an error on screen", "is there an error on my screen")) or
            ("programiz" in msg_l) or
            ("armstrong" in msg_l and any(w in msg_l for w in ("run", "execute", "paste", "compiler", "enter", "open", "code"))) or
            ("compiler" in msg_l and any(w in msg_l for w in ("open", "run", "paste", "c compiler", "enter"))) or
            any(phrase in msg_l for phrase in (
                "open it, paste it and run it",
                "open it paste it and run it",
                "paste it and run it",
                "open it, paste it",
                "run it and enter 153",
                "run it and enter",
            ))
        )
        if is_direct_computer_cmd and not requested_provider:
            from app.services.manthan import manthan_planner
            agent_res = await manthan_planner.execute_task(clean_message)
            total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
            return {
                "response": agent_res.get("message", "Task completed."),
                "provider": "manthan",
                "model": "computer-agent-v8.1",
                "execution_mode": "local",
                "execution": "local",
                "endpoint": "local://computer-agent-v8.1",
                "latency_ms": total_latency_ms,
                "latency": total_latency_ms,
                "status": "success" if agent_res.get("success") else agent_res.get("status", "failed"),
                "fallback_used": False,
                "fallback": False,
                "fallback_path": None,
                "fallback_reason": None,
                "route_reason": "computer_control",
                "why_this_choice": "Executed on-device via macOS Computer Agent & Manthan Planner.",
                "tools_executed": [{"tool": r.get("tool"), "status": r.get("status", "completed")} for r in agent_res.get("results", []) if r.get("tool")],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                "task_id": agent_res.get("task_id"),
                "plan": agent_res.get("plan", []),
            }

        # 3. Retrieve relevant Smṛti persistent memories (grounding user profile and facts)
        from app.services.smriti import smriti_service
        from app.services.knowledge import knowledge_service
        from app.core.prompts import build_narad_system_prompt

        persistent_memories = None
        try:
            persistent_memories = smriti_service.get_relevant_memories_context(query=clean_message)
        except Exception as smriti_err:
            logger.warning(f"[Smriti] Memory retrieval bypassed safely: {smriti_err}")
            persistent_memories = None

        # 4. Retrieve relevant Knowledge Base context (document grounding)
        knowledge_context = None
        try:
            knowledge_context = knowledge_service.get_relevant_knowledge_context(query=clean_message, max_chunks=2)
        except Exception as kb_err:
            logger.warning(f"[KnowledgeBase] Knowledge retrieval bypassed safely: {kb_err}")
            knowledge_context = None

        session_context = None
        conversation_summary = None
        if session_id:
            try:
                session_context = smriti_service.get_session_memory_context(session_id)
            except Exception as smriti_err:
                logger.warning(f"[Smriti] Could not load session summary for session {session_id}: {smriti_err}")
            try:
                conversation_summary = smriti_service.get_conversation_summary_context(session_id)
            except Exception as smriti_err:
                logger.warning(f"[Smriti] Could not load conversation summary for session {session_id}: {smriti_err}")

        # 5. Task / Intent Analysis & Model Routing (Phase 4)
        # Pipeline: USER REQUEST -> EXECUTION CONSTRAINT -> NARAD CORE -> RELEVANT SMṚTI -> RELEVANT KNOWLEDGE -> TASK / INTENT ANALYSIS -> MODEL ROUTER -> RESPONSE / ACTION
        from app.core.provider_truth import (
            detect_execution_constraint,
            is_local_provider,
            EXECUTION_LOCAL_ONLY,
            EXECUTION_CLOUD_ONLY,
        )
        execution_constraint = detect_execution_constraint(clean_message)
        if current_op_mode in (RuntimeMode.LOCAL_ONLY, RuntimeMode.OFFLINE):
            execution_constraint = EXECUTION_LOCAL_ONLY

        route = model_router.resolve_route(
            requested_provider=requested_provider,
            requested_model=requested_model,
            message=clean_message,
            is_voice=is_voice,
            execution_constraint=execution_constraint,
        )

        def _build_full_messages(prov_id: str, mdl_name: str) -> List[Dict[str, Any]]:
            sys_prompt = build_narad_system_prompt(
                provider_id=prov_id,
                model_name=mdl_name,
                session_id=session_id,
                session_context=session_context,
                persistent_memories=persistent_memories,
                knowledge_context=knowledge_context,
                conversation_summary=conversation_summary
            )
            full = [{"role": "system", "content": sys_prompt}]
            full.extend([m for m in messages if m.get("role") != "system"])
            return full

        from app.services.connectivity import connectivity_service
        from app.core.provider_truth import (
            validate_execution_mode,
            get_provider_endpoint,
            generate_why_this_choice,
        )
        is_offline = not connectivity_service.is_online()

        # Rule 6: Offline mode safeguard — never call cloud provider when offline
        if is_offline and route.execution_mode == "cloud":
            total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
            return {
                "response": (
                    f"⚠️ **LOCAL/OFFLINE Mode**: Cloud provider '{route.provider_id}' cannot be called while offline. "
                    "Only Ollama and verified local providers are permitted."
                ),
                "provider": route.provider_id,
                "model": route.model_name,
                "execution_mode": "cloud",
                "execution": "cloud",
                "endpoint": route.endpoint,
                "latency_ms": total_latency_ms,
                "latency": total_latency_ms,
                "status": "offline_rejected",
                "fallback_used": False,
                "fallback": False,
                "fallback_path": None,
                "fallback_reason": None,
                "route_reason": "LOCAL/OFFLINE",
                "why_this_choice": route.why_this_choice,
                "execution_constraint": route.execution_constraint,
                "tools_executed": [],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

        # LOCAL_ONLY constraint: if router returned is_configured=False, no local provider was found
        if execution_constraint == EXECUTION_LOCAL_ONLY and not route.is_configured:
            total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
            return {
                "response": (
                    "⚠️ **LOCAL_ONLY Mode**: No local provider (Ollama/HuggingFace) is currently available. "
                    "Cloud providers are forbidden by your local-only directive. "
                    "Please ensure Ollama is running on localhost:11434."
                ),
                "provider": route.provider_id,
                "model": route.model_name,
                "execution_mode": "local",
                "execution": "local",
                "endpoint": route.endpoint,
                "latency_ms": total_latency_ms,
                "latency": total_latency_ms,
                "status": "local_provider_unavailable",
                "fallback_used": False,
                "fallback": False,
                "fallback_path": None,
                "fallback_reason": None,
                "route_reason": "LOCAL_ONLY",
                "why_this_choice": route.why_this_choice,
                "execution_constraint": "LOCAL_ONLY",
                "tools_executed": [],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }

        # =====================================================================
        # FINAL SAFETY ASSERTION: If LOCAL_ONLY, verify selected provider is local
        # This prevents any routing bug from accidentally calling a cloud API.
        # =====================================================================
        if execution_constraint == EXECUTION_LOCAL_ONLY:
            if not is_local_provider(route.provider_id):
                logger.error(
                    f"[SafetyAbort] LOCAL_ONLY constraint violated: router selected '{route.provider_id}' "
                    f"which is NOT a verified local provider. Aborting to prevent cloud invocation."
                )
                total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)
                return {
                    "response": (
                        f"⚠️ **Safety Abort**: LOCAL_ONLY constraint violated. "
                        f"Router selected '{route.provider_id}' which is not a local provider. "
                        f"Aborting request to prevent cloud invocation."
                    ),
                    "provider": route.provider_id,
                    "model": route.model_name,
                    "execution_mode": route.execution_mode,
                    "execution": route.execution_mode,
                    "endpoint": route.endpoint,
                    "latency_ms": total_latency_ms,
                    "latency": total_latency_ms,
                    "status": "safety_abort",
                    "fallback_used": False,
                    "fallback": False,
                    "fallback_path": None,
                    "fallback_reason": None,
                    "route_reason": "LOCAL_ONLY_SAFETY_ABORT",
                    "why_this_choice": "Safety assertion prevented cloud invocation under LOCAL_ONLY constraint.",
                    "execution_constraint": "LOCAL_ONLY",
                    "tools_executed": [],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0}
                }

        # 5. Dispatch request to Primary Provider
        # Determine tool availability (Enforce CHAT_ONLY autonomy & suppress tool schemas for greetings)
        from app.services.action_policy import action_policy, AutonomyMode

        is_chat_only = (action_policy.autonomy_mode == AutonomyMode.LEVEL_0_CHAT_ONLY)
        msg_clean_lower = clean_message.lower().strip()
        is_greeting_or_chit_chat = any(
            msg_clean_lower.startswith(g) or msg_clean_lower == g
            for g in (
                "hello", "hi", "hey", "how are you", "good morning", "good evening",
                "good afternoon", "greetings", "thanks", "thank you", "who are you",
                "what are you", "introduce yourself"
            )
        ) and not any(
            t in msg_clean_lower for t in (
                "time is it", "what time", "what date", "calculate", "search", "remember",
                "open", "play", "screen", "file", "build", "run"
            )
        )
        passed_tools = [] if (is_chat_only or is_greeting_or_chit_chat) else None

        full_messages = _build_full_messages(route.provider_id, route.model_name)
        logger.info(
            f"NARAD Core dispatching to primary provider '{route.provider_id}' "
            f"[model: {route.model_name}, task: {route.task_category}, mode: {route.execution_mode}, tools: {len(passed_tools) if passed_tools is not None else 'all'}]"
        )

        provider_result = None
        primary_failed = False
        primary_status = "unknown"
        primary_error_msg = ""
        is_transient = False

        try:
            provider_result = await route.provider.generate_response(
                messages=full_messages,
                model=route.model_name,
                tools=passed_tools
            )
            primary_status = provider_result.get("status", "success")
            if primary_status != "success":
                primary_failed = True
                primary_error_msg = provider_result.get("error") or provider_result.get("content", "")
                err_lower = str(primary_error_msg).lower()
                is_400 = "400" in str(primary_error_msg) or "bad request" in err_lower or primary_status == "client_error"
                if is_400:
                    is_transient = False
                    primary_status = "client_error"
                else:
                    is_transient = provider_result.get("is_transient", True)
        except Exception as e:
            primary_failed = True
            primary_error_msg = str(e)
            err_lower = primary_error_msg.lower()
            is_400 = "400" in primary_error_msg or "bad request" in err_lower
            is_transient = not is_400
            primary_status = "client_error" if is_400 else "server_error"
            logger.error(f"Primary provider '{route.provider_id}' exception: {e}", exc_info=True)

        # 6. Intelligent Failover Logic (Phase 5)
        # CRITICAL RULE: Do NOT failover on 400 client/schema errors (these are bugs that must be surfaced).
        # Failover ONLY on transient errors: 429 rate limit, timeout, network failure, or 5xx server errors.
        fallback_occurred = False
        fallback_path = None
        fallback_reason = None
        executed_provider_id = route.provider_id
        executed_model_name = route.model_name

        if primary_failed:
            if not is_transient or primary_status == "client_error":
                logger.warning(
                    f"NARAD Core: Primary provider '{route.provider_id}' returned non-transient error "
                    f"[{primary_status}]. Preserving error without failover to expose integration bug."
                )
            elif route.failover_candidates:
                logger.warning(
                    f"NARAD Core: Primary provider '{route.provider_id}' encountered transient error "
                    f"[{primary_status}]. Initiating failover across candidates: {route.failover_candidates}..."
                )

                for candidate in route.failover_candidates:
                    cand_pid = candidate.get("provider")
                    cand_model = candidate.get("model")
                    cand_prov = provider_manager.get_provider(cand_pid)

                    # In offline mode, skip any cloud provider!
                    if is_offline and validate_execution_mode(cand_pid) != "local":
                        if cand_prov:
                            cand_prov.record_failover_skip()
                        continue

                    # LOCAL_ONLY constraint: skip any non-local provider in failover
                    if execution_constraint == EXECUTION_LOCAL_ONLY and not is_local_provider(cand_pid):
                        logger.info(f"[Failover Engine] Skipping cloud candidate '{cand_pid}' due to LOCAL_ONLY constraint.")
                        if cand_prov:
                            cand_prov.record_failover_skip()
                        continue

                    # V6.1: Never retry auth-error providers (permanent failure)
                    if not cand_prov or not cand_prov.is_configured() or cand_prov.has_auth_error():
                        if cand_prov:
                            cand_prov.record_failover_skip()
                        continue

                    # Skip providers still in cooldown
                    if cand_prov.is_in_cooldown():
                        cand_prov.record_failover_skip()
                        continue

                    logger.info(f"[Failover Engine] Attempting failover: '{route.provider_id}' → '{cand_pid}' [{cand_model}]")
                    fallback_messages = _build_full_messages(cand_pid, cand_model)

                    try:
                        cand_result = await cand_prov.generate_response(
                            messages=fallback_messages,
                            model=cand_model,
                            tools=passed_tools
                        )
                        if cand_result.get("status") == "success":
                            provider_result = cand_result
                            fallback_occurred = True
                            fallback_path = f"{route.provider_id.upper()} → {cand_pid.upper()}"
                            fallback_reason = primary_status
                            executed_provider_id = cand_pid
                            executed_model_name = cand_model
                            primary_failed = False
                            logger.info(f"[Failover Engine] Failover to '{cand_pid}' SUCCEEDED!")
                            break
                        else:
                            logger.warning(f"[Failover Engine] Candidate '{cand_pid}' failed with {cand_result.get('status')}. Continuing chain...")
                    except Exception as cand_err:
                        logger.warning(f"[Failover Engine] Candidate '{cand_pid}' raised exception: {cand_err}. Continuing chain...")

        total_latency_ms = int((time.perf_counter() - overall_start_time) * 1000)

        # Telemetry logging: Task -> Provider -> Model -> Reason -> Latency -> Failover
        telemetry_str = (
            f"Task: {route.task_category} -> Provider: {executed_provider_id} -> "
            f"Model: {executed_model_name} -> Reason: {route.routing_reason} -> "
            f"Latency: {total_latency_ms}ms -> Failover: {fallback_occurred}"
        )
        logger.info(f"[Routing Telemetry] {telemetry_str}")

        # 7. Assemble Final Self-Awareness Telemetry Response (Phase 10 & Provider Truth)
        executed_mode = validate_execution_mode(executed_provider_id)
        executed_endpoint = get_provider_endpoint(executed_provider_id)
        verified_why = generate_why_this_choice(
            provider_id=executed_provider_id,
            model_name=executed_model_name,
            task_category=route.task_category,
            execution_mode=executed_mode,
            route_reason=route.routing_reason,
            latency_ms=total_latency_ms,
            fallback_used=fallback_occurred,
            is_offline=is_offline
        )

        if provider_result and not primary_failed:
            # Smṛti 3.0: Non-blocking background observation and durable fact extraction
            try:
                from app.services.smriti import smriti_service
                smriti_service.observe_and_extract(clean_message, session_id=session_id)
            except Exception as sm_obs_err:
                logger.debug(f"[Smriti] Background observation notice: {sm_obs_err}")

            return {
                "response": provider_result.get("content", ""),
                "provider": executed_provider_id,
                "model": executed_model_name,
                "execution_mode": executed_mode,
                "execution": executed_mode,
                "endpoint": executed_endpoint,
                "network_required": (executed_mode.lower() != "local"),
                "latency_ms": total_latency_ms,
                "latency": total_latency_ms,
                "status": "success",
                "fallback_used": fallback_occurred,
                "fallback": fallback_occurred,
                "fallback_path": fallback_path,
                "fallback_reason": fallback_reason,
                "route_reason": route.task_category,
                "why_this_choice": verified_why,
                "execution_constraint": route.execution_constraint,
                "telemetry": telemetry_str,
                "tools_executed": provider_result.get("tools_executed", []),
                "usage": provider_result.get("usage", {})
            }
        else:
            if is_offline:
                err_content = (
                    f"⚠️ **LOCAL/OFFLINE Mode**: Local inference via '{route.provider_id}' failed: {primary_error_msg}\n\n"
                    "No cloud failover was attempted because NARAD is operating in verified offline mode."
                )
                final_status = "offline_failed"
            elif not route.is_configured:
                err_content = (
                    "⚠️ **All configured AI providers are currently unavailable.**\n\n"
                    "No LLM provider keys (Groq, NVIDIA NIM, Google Gemini, OpenRouter) are active in `backend/.env`.\n"
                    "Please configure at least one provider API key to activate conversational intelligence."
                )
                final_status = "service_unavailable"
            else:
                err_content = (
                    f"⚠️ **All configured AI providers are currently unavailable.**\n\n"
                    f"Communication failure with provider '{route.provider_id}': {primary_error_msg}\n\n"
                    "All attempted failover candidates were exhausted. Please verify provider connectivity and API keys in `backend/.env`."
                )
                final_status = "service_unavailable" if primary_status != "client_error" else primary_status

            return {
                "response": err_content,
                "provider": route.provider_id,
                "model": route.model_name,
                "execution_mode": route.execution_mode,
                "execution": route.execution_mode,
                "endpoint": route.endpoint,
                "network_required": (route.execution_mode.lower() != "local"),
                "latency_ms": total_latency_ms,
                "latency": total_latency_ms,
                "status": final_status,
                "fallback_used": False,
                "fallback": False,
                "fallback_path": None,
                "fallback_reason": None,
                "route_reason": route.task_category,
                "why_this_choice": verified_why,
                "execution_constraint": route.execution_constraint,
                "tools_executed": [],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }


# Global singleton NARAD Core service instance
narad_core = NaradCore()

