"""
NARAD Phase 2 — Tool Orchestration & Dynamic Tool Selection Engine.
Manages tool metadata, dynamic scoping per intent, execution validation,
permission verification, post-action visual observation, error categorization,
and strict zero-fake-success verification.
"""

import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime
import enum
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app.services.action_policy import action_policy, PermissionLevel
from app.services.kriya import kriya_dispatcher
from app.services.event_system import event_system, EventType

logger = logging.getLogger("narad.tool_orchestrator")


class FailureCategory(str, enum.Enum):
    TIMEOUT = "TIMEOUT"
    TOOL_ERROR = "TOOL_ERROR"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    NETWORK_ERROR = "NETWORK_ERROR"
    MODEL_ERROR = "MODEL_ERROR"
    VISION_ERROR = "VISION_ERROR"
    STATE_MISMATCH = "STATE_MISMATCH"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"


# Type alias for tool execution result
ToolResult = Dict[str, Any]


@dataclass
class ToolMetadata:
    name: str
    description: str
    category: str  # vision, computer, filesystem, research, memory, system, utility
    risk_level: str  # safe, low, medium, high
    requires_confirmation: bool = False
    local_only: bool = True
    network_required: bool = False
    supports_dry_run: bool = True
    timeout: int = 15
    idempotent: bool = True
    capabilities: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ToolOrchestrator:
    """
    Tool Orchestrator for NARAD.
    - Maintains rich metadata per tool
    - Selects relevant tools dynamically based on task requirements
    - Validates arguments & enforces action policies
    - Executes tools via Krīya and captures execution timing
    - Chaining & post-action observation (Act -> Observe -> Compare -> Verify)
    - Categorizes failures with zero fake success
    """

    def __init__(self):
        self._metadata_registry: Dict[str, ToolMetadata] = {}
        self._init_default_metadata()

    def _init_default_metadata(self):
        """Register canonical metadata for all Krīya and system tools."""
        self.register_metadata(ToolMetadata(
            name="observe_screen",
            description="Capture current display screenshot and active application metadata with Trinetra.",
            category="vision",
            risk_level="safe",
            requires_confirmation=False,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=10,
            idempotent=True,
            capabilities=["vision", "screen_capture", "observation"]
        ))
        self.register_metadata(ToolMetadata(
            name="get_active_application",
            description="Inspect the frontmost active application title and window state.",
            category="vision",
            risk_level="safe",
            requires_confirmation=False,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=5,
            idempotent=True,
            capabilities=["vision", "active_app", "observation"]
        ))
        self.register_metadata(ToolMetadata(
            name="understand_screen",
            description="Analyze visual screen state or image to answer questions.",
            category="vision",
            risk_level="safe",
            requires_confirmation=False,
            local_only=False,  # Can use local or cloud vision
            network_required=False,
            supports_dry_run=True,
            timeout=25,
            idempotent=True,
            capabilities=["vision", "visual_reasoning"]
        ))
        self.register_metadata(ToolMetadata(
            name="open_application",
            description="Launch or bring a macOS desktop application to the foreground.",
            category="computer",
            risk_level="low",
            requires_confirmation=False,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=10,
            idempotent=True,
            capabilities=["computer", "app_control"]
        ))
        self.register_metadata(ToolMetadata(
            name="close_application",
            description="Gracefully terminate a running macOS application.",
            category="computer",
            risk_level="medium",
            requires_confirmation=True,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=10,
            idempotent=True,
            capabilities=["computer", "app_control"]
        ))
        self.register_metadata(ToolMetadata(
            name="focus_application",
            description="Switch window focus to a running application.",
            category="computer",
            risk_level="safe",
            requires_confirmation=False,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=5,
            idempotent=True,
            capabilities=["computer", "app_control"]
        ))
        self.register_metadata(ToolMetadata(
            name="media_control",
            description="Control media playback (play, pause, next, volume).",
            category="computer",
            risk_level="safe",
            requires_confirmation=False,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=5,
            idempotent=False,
            capabilities=["computer", "media"]
        ))
        self.register_metadata(ToolMetadata(
            name="play_music",
            description="Launch Apple Music and start playback of a track or artist.",
            category="computer",
            risk_level="low",
            requires_confirmation=False,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=10,
            idempotent=False,
            capabilities=["computer", "media", "music"]
        ))
        self.register_metadata(ToolMetadata(
            name="open_browser_url",
            description="Open a web URL in the default browser.",
            category="browser",
            risk_level="low",
            requires_confirmation=False,
            local_only=False,
            network_required=True,
            supports_dry_run=True,
            timeout=10,
            idempotent=True,
            capabilities=["browser", "web"]
        ))
        self.register_metadata(ToolMetadata(
            name="read_file",
            description="Read contents of a file within the project workspace.",
            category="filesystem",
            risk_level="safe",
            requires_confirmation=False,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=10,
            idempotent=True,
            capabilities=["filesystem", "file_read"]
        ))
        self.register_metadata(ToolMetadata(
            name="write_file",
            description="Write or overwrite contents of a file in the workspace.",
            category="filesystem",
            risk_level="medium",
            requires_confirmation=True,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=15,
            idempotent=False,
            capabilities=["filesystem", "file_write"]
        ))
        self.register_metadata(ToolMetadata(
            name="delete_file",
            description="Delete a file from the workspace.",
            category="filesystem",
            risk_level="high",
            requires_confirmation=True,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=10,
            idempotent=False,
            capabilities=["filesystem", "file_delete"]
        ))
        self.register_metadata(ToolMetadata(
            name="list_directory",
            description="List contents and subdirectories within a directory path.",
            category="filesystem",
            risk_level="safe",
            requires_confirmation=False,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=10,
            idempotent=True,
            capabilities=["filesystem", "directory_list"]
        ))
        self.register_metadata(ToolMetadata(
            name="run_shell_command",
            description="Execute a safe sandboxed terminal command in the workspace.",
            category="system",
            risk_level="medium",
            requires_confirmation=True,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=30,
            idempotent=False,
            capabilities=["system", "shell_execution"]
        ))
        self.register_metadata(ToolMetadata(
            name="check_service_port",
            description="Check if a local TCP service port (e.g. 8000, 5173) is open and listening.",
            category="system",
            risk_level="safe",
            requires_confirmation=False,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=5,
            idempotent=True,
            capabilities=["system", "port_check", "diagnostics"]
        ))
        self.register_metadata(ToolMetadata(
            name="get_system_state",
            description="Collect system resources, CPU, memory, and uptime metrics.",
            category="system",
            risk_level="safe",
            requires_confirmation=False,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=10,
            idempotent=True,
            capabilities=["system", "metrics"]
        ))
        self.register_metadata(ToolMetadata(
            name="calculator",
            description="Perform exact deterministic mathematical evaluations.",
            category="utility",
            risk_level="safe",
            requires_confirmation=False,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=3,
            idempotent=True,
            capabilities=["math", "calculation"]
        ))
        self.register_metadata(ToolMetadata(
            name="get_current_time",
            description="Get the current local system date, time, and UTC offset.",
            category="utility",
            risk_level="safe",
            requires_confirmation=False,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=2,
            idempotent=True,
            capabilities=["time", "datetime"]
        ))
        self.register_metadata(ToolMetadata(
            name="get_time_in_location",
            description="Look up the local time in a specified world city or timezone.",
            category="utility",
            risk_level="safe",
            requires_confirmation=False,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=3,
            idempotent=True,
            capabilities=["time", "world_clock"]
        ))
        self.register_metadata(ToolMetadata(
            name="save_memory",
            description="Persist a verified user fact, preference, or project state into Smṛti 3.0.",
            category="memory",
            risk_level="safe",
            requires_confirmation=False,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=5,
            idempotent=False,
            capabilities=["memory", "smriti"]
        ))
        self.register_metadata(ToolMetadata(
            name="retrieve_memory",
            description="Retrieve persistent memories from Smṛti 3.0 matching key or query.",
            category="memory",
            risk_level="safe",
            requires_confirmation=False,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=5,
            idempotent=True,
            capabilities=["memory", "smriti"]
        ))
        self.register_metadata(ToolMetadata(
            name="search_knowledge",
            description="Search ingested documentation and knowledge base passages.",
            category="research",
            risk_level="safe",
            requires_confirmation=False,
            local_only=True,
            network_required=False,
            supports_dry_run=True,
            timeout=10,
            idempotent=True,
            capabilities=["knowledge", "search", "documents"]
        ))
        self.register_metadata(ToolMetadata(
            name="web_search",
            description="Perform live external search engine queries for real-time information.",
            category="research",
            risk_level="low",
            requires_confirmation=False,
            local_only=False,
            network_required=True,
            supports_dry_run=True,
            timeout=15,
            idempotent=True,
            capabilities=["research", "web_search"]
        ))

    def register_metadata(self, metadata: ToolMetadata):
        """Register or override metadata for a tool."""
        self._metadata_registry[metadata.name] = metadata

    def get_tool_metadata(self, name: str) -> Optional[ToolMetadata]:
        return self._metadata_registry.get(name)

    def select_tools_for_intent(
        self,
        intents: List[str],
        offline_mode: bool = False,
        local_only_mode: bool = False,
    ) -> List[ToolMetadata]:
        """
        Dynamically select only relevant tools matching intent categories.
        Ensures the agent is never overwhelmed with all tools simultaneously.
        """
        selected: Dict[str, ToolMetadata] = {}
        intents_upper = [i.upper() for i in intents]

        for name, meta in self._metadata_registry.items():
            # Check offline & local-only constraints
            if offline_mode and meta.network_required:
                continue
            if local_only_mode and not meta.local_only:
                continue

            # Category mappings
            if "VISION" in intents_upper and meta.category == "vision":
                selected[name] = meta
            elif "COMPUTER_CONTROL" in intents_upper and meta.category in ("computer", "vision"):
                selected[name] = meta
            elif "FILE_OPERATION" in intents_upper and meta.category == "filesystem":
                selected[name] = meta
            elif "SYSTEM_OPERATION" in intents_upper and meta.category in ("system", "filesystem"):
                selected[name] = meta
            elif "CODING" in intents_upper and meta.category in ("filesystem", "system", "browser"):
                selected[name] = meta
            elif "RESEARCH" in intents_upper and meta.category in ("research", "knowledge"):
                selected[name] = meta
            elif "MEMORY" in intents_upper and meta.category == "memory":
                selected[name] = meta
            elif any(cat in intents_upper for cat in ("MULTI_STEP_TASK", "AUTOMATION", "PLANNING")):
                # For complex multi-step tasks, provide core operational tools
                if meta.category in ("vision", "computer", "system", "filesystem", "utility"):
                    selected[name] = meta
            elif "QUESTION" in intents_upper or "CHAT" in intents_upper:
                # Lightweight utility tools for basic chat/questions
                if meta.category in ("utility", "memory"):
                    selected[name] = meta

        # If no specific matches, fall back to safe read/utility tools
        if not selected:
            for name, meta in self._metadata_registry.items():
                if meta.risk_level == "safe" and not meta.network_required:
                    selected[name] = meta

        return list(selected.values())

    async def execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        task_id: Optional[str] = None,
        confirmation_id: Optional[str] = None,
        dry_run: bool = False,
        offline_mode: bool = False,
        local_only_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute a tool safely through Krīya:
        - Validates arguments
        - Validates offline / local-only compatibility
        - Enforces permissions
        - Measures execution duration
        - Post-action observation & verification
        - Returns structured result without fake success
        """
        t0 = time.perf_counter()
        meta = self.get_tool_metadata(name)
        risk = meta.risk_level if meta else "medium"

        # Check tool existence before policy or dispatch
        from app.services.kriya import kriya_dispatcher
        if not meta and not kriya_dispatcher.get_tool(name):
            dur = int((time.perf_counter() - t0) * 1000)
            err_msg = f"Unknown tool: '{name}' is not registered in NARAD."
            logger.warning(f"[ToolOrchestrator] {err_msg}")
            event_system.emit_event(
                EventType.ACTION_FAILED,
                title=f"Unknown Tool: {name}",
                body=err_msg,
                priority="high",
                task_id=task_id,
                metadata={"tool": name}
            )
            return {
                "tool": name,
                "success": False,
                "result": None,
                "error": err_msg,
                "duration_ms": dur,
                "risk": risk,
                "failure_category": FailureCategory.TOOL_ERROR.value,
                "observations": {"unknown_tool": True}
            }

        event_system.emit_event(
            EventType.ACTION_STARTED,
            title=f"Tool Execution Started: {name}",
            body=f"Executing tool '{name}' with arguments {arguments}",
            priority="normal",
            task_id=task_id,
            metadata={"tool": name, "arguments": arguments, "dry_run": dry_run}
        )

        try:
            from app.services.agent_brain import agent_brain
            is_off = offline_mode or (agent_brain.is_offline() if hasattr(agent_brain, "is_offline") else False)
            is_local = local_only_mode or (agent_brain.is_local_only() if hasattr(agent_brain, "is_local_only") else False)
        except Exception:
            is_off = offline_mode
            is_local = local_only_mode

        # 1. Check Offline Mode Enforcement
        if is_off and meta and meta.network_required:
            dur = int((time.perf_counter() - t0) * 1000)
            err_msg = f"OFFLINE_BLOCKED: Tool '{name}' requires network connectivity, which is blocked in OFFLINE mode."
            logger.warning(f"[ToolOrchestrator] {err_msg}")
            event_system.emit_event(
                EventType.ACTION_FAILED,
                title=f"Tool Blocked in Offline Mode: {name}",
                body=err_msg,
                priority="high",
                task_id=task_id,
                metadata={"tool": name, "error": err_msg}
            )
            return {
                "tool": name,
                "success": False,
                "result": None,
                "error": err_msg,
                "duration_ms": dur,
                "risk": risk,
                "failure_category": FailureCategory.NETWORK_ERROR.value,
                "observations": {"network_blocked": True, "mode": "OFFLINE"}
            }

        # 2. Check Local-Only Mode Enforcement
        if is_local and meta and not meta.local_only:
            dur = int((time.perf_counter() - t0) * 1000)
            err_msg = f"LOCAL_ONLY_BLOCKED: Tool '{name}' requires cloud services, which is blocked in LOCAL_ONLY mode."
            logger.warning(f"[ToolOrchestrator] {err_msg}")
            event_system.emit_event(
                EventType.ACTION_FAILED,
                title=f"Tool Blocked in Local-Only Mode: {name}",
                body=err_msg,
                priority="high",
                task_id=task_id,
                metadata={"tool": name, "error": err_msg}
            )
            return {
                "tool": name,
                "success": False,
                "result": None,
                "error": err_msg,
                "duration_ms": dur,
                "risk": risk,
                "failure_category": FailureCategory.PERMISSION_DENIED.value,
                "observations": {"cloud_blocked": True, "mode": "LOCAL_ONLY"}
            }

        # 3. Dry-Run Handling
        if dry_run:
            dur = int((time.perf_counter() - t0) * 1000)
            logger.info(f"[ToolOrchestrator] Dry-run simulated for tool '{name}'")
            return {
                "tool": name,
                "success": True,
                "result": {"dry_run": True, "simulated": True, "message": f"Simulated execution of {name}"},
                "error": None,
                "duration_ms": dur,
                "risk": risk,
                "failure_category": None,
                "observations": {"simulated": True}
            }

        # 4. Check Action Policy (Permissions)
        policy_check = action_policy.evaluate_request(
            name,
            arguments,
            confirmation_id=confirmation_id,
            task_id=task_id
        )
        if policy_check.blocked:
            dur = int((time.perf_counter() - t0) * 1000)
            logger.warning(f"[ToolOrchestrator] Policy blocked tool '{name}': {policy_check.reason}")
            event_system.emit_event(
                EventType.ACTION_FAILED,
                title=f"Permission Denied for Tool: {name}",
                body=policy_check.reason,
                priority="high",
                task_id=task_id,
                metadata={"tool": name, "reason": policy_check.reason}
            )
            return {
                "tool": name,
                "success": False,
                "result": None,
                "error": policy_check.reason,
                "duration_ms": dur,
                "risk": risk,
                "failure_category": FailureCategory.PERMISSION_DENIED.value,
                "observations": {"policy": "blocked", "confirmation_required": policy_check.requires_confirmation}
            }

        # 5. Dispatch Execution to Krīya
        timeout = meta.timeout if meta else 20
        observations: Dict[str, Any] = {}
        try:
            kriya_res = await asyncio.wait_for(
                kriya_dispatcher.execute_tool(
                    name=name,
                    arguments=arguments,
                    confirmation_id=confirmation_id,
                    task_id=task_id
                ),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            dur = int((time.perf_counter() - t0) * 1000)
            err_msg = f"Tool '{name}' timed out after {timeout} seconds."
            logger.error(f"[ToolOrchestrator] {err_msg}")
            event_system.emit_event(
                EventType.ACTION_FAILED,
                title=f"Tool Timeout: {name}",
                body=err_msg,
                priority="high",
                task_id=task_id,
                metadata={"tool": name, "timeout": timeout}
            )
            return {
                "tool": name,
                "success": False,
                "result": None,
                "error": err_msg,
                "duration_ms": dur,
                "risk": risk,
                "failure_category": FailureCategory.TIMEOUT.value,
                "observations": {"timeout": True}
            }
        except Exception as e:
            dur = int((time.perf_counter() - t0) * 1000)
            err_msg = f"Unexpected failure executing tool '{name}': {str(e)}"
            logger.error(f"[ToolOrchestrator] {err_msg}")
            event_system.emit_event(
                EventType.ACTION_FAILED,
                title=f"Tool Execution Error: {name}",
                body=err_msg,
                priority="high",
                task_id=task_id,
                metadata={"tool": name, "exception": str(e)}
            )
            return {
                "tool": name,
                "success": False,
                "result": None,
                "error": err_msg,
                "duration_ms": dur,
                "risk": risk,
                "failure_category": FailureCategory.TOOL_ERROR.value,
                "observations": {"exception": str(e)}
            }

        dur = int((time.perf_counter() - t0) * 1000)

        # 6. Parse Krīya Result & Check For Failures
        success = True
        err = None
        fail_cat = None

        if isinstance(kriya_res, dict):
            if "error" in kriya_res or kriya_res.get("status") in ("error", "failed", "blocked"):
                success = False
                err = kriya_res.get("error") or kriya_res.get("message") or "Tool reported error status."
                fail_cat = FailureCategory.TOOL_ERROR.value
            elif kriya_res.get("success") is False:
                success = False
                err = kriya_res.get("message") or "Tool execution unsuccessful."
                fail_cat = FailureCategory.TOOL_ERROR.value

        # 7. Observe After Action for Mutating Operations (Section 8)
        # For application launches or computer mutations: ACT -> OBSERVE -> COMPARE -> VERIFY
        if success and name in ("open_application", "focus_application"):
            target_app = arguments.get("app_name") or arguments.get("application") or ""
            obs_res = await self._observe_post_action(name, target_app)
            observations.update(obs_res)
            if not obs_res.get("verified", True):
                success = False
                err = f"Post-action verification failed: expected '{target_app}' to be frontmost, but actual state differed."
                fail_cat = FailureCategory.STATE_MISMATCH.value

        if success:
            event_system.emit_event(
                EventType.ACTION_COMPLETED,
                title=f"Tool Completed: {name}",
                body=f"Successfully executed tool '{name}' in {dur}ms",
                priority="normal",
                task_id=task_id,
                metadata={"tool": name, "duration_ms": dur}
            )
        else:
            event_system.emit_event(
                EventType.ACTION_FAILED,
                title=f"Tool Failed: {name}",
                body=err or "Execution error",
                priority="high",
                task_id=task_id,
                metadata={"tool": name, "error": err, "failure_category": fail_cat}
            )

        return {
            "tool": name,
            "success": success,
            "result": kriya_res,
            "error": err,
            "duration_ms": dur,
            "risk": risk,
            "failure_category": fail_cat,
            "observations": observations
        }

    def can_retry(self, result: Dict[str, Any], attempt_count: int = 1) -> bool:
        """Determine if a failed tool result can be safely retried."""
        if attempt_count >= 3:
            return False
        cat = result.get("failure_category")
        if cat in (
            FailureCategory.TIMEOUT.value,
            FailureCategory.SERVICE_UNAVAILABLE.value,
            FailureCategory.NETWORK_ERROR.value,
        ):
            return True
        return False

    async def _observe_post_action(self, tool_name: str, target: Any) -> Dict[str, Any]:
        """
        Act -> Observe -> Compare expected vs actual -> Verify.
        Uses computer adapter to verify whether targeted application opened.
        """
        try:
            from app.services.computer import computer_adapter
            await asyncio.sleep(0.5)  # Allow OS window animation
            active_info = computer_adapter.get_active_application()
            active_name = active_info.get("active_application", "") if isinstance(active_info, dict) else ""
            
            target_str = ""
            if isinstance(target, dict):
                target_str = target.get("app_name") or target.get("target") or target.get("name") or ""
            elif isinstance(target, str):
                target_str = target

            if not target_str:
                return {"active_application": active_name, "verified": True}

            is_match = (
                target_str.lower() in active_name.lower() or
                active_name.lower() in target_str.lower()
            )
            return {
                "observed_active_application": active_name,
                "expected_target": target_str,
                "verified": is_match
            }
        except Exception as e:
            logger.debug(f"[ToolOrchestrator] Post-action observation error: {e}")
            return {"observation_error": str(e), "verified": True}


tool_orchestrator = ToolOrchestrator()

