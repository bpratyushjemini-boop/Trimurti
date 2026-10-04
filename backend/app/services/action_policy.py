"""NARAD V4 - Action Policy and Permission System.

Enforces 5-tier permission levels, strict filesystem sandboxing, and command allowlisting:
- LEVEL 0 (SAFE): Read-only, status, safe queries, app launch, public URLs. No confirmation.
- LEVEL 1 (LOW RISK): Safe application focus, view changes.
- LEVEL 2 (CONFIRM): Create/modify/move files, run development commands. Requires confirmation.
- LEVEL 3 (HIGH RISK): Deleting files, closing applications. Requires explicit confirmation.
- LEVEL 4 (BLOCKED): Credential theft, SSH keys, .env, sudo, destructive shell, security bypass.
"""

from enum import IntEnum
import os
import re
import shlex
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid
import logging

logger = logging.getLogger("narad.action_policy")


class PermissionLevel(IntEnum):
    LEVEL_0_SAFE = 0
    LEVEL_1_LOW = 1
    LEVEL_2_CONFIRM = 2
    LEVEL_3_HIGH = 3
    LEVEL_4_BLOCKED = 4

    SAFE_READ = 0
    LOW_RISK = 1
    CONFIRM = 2
    HIGH_RISK = 3
    BLOCKED = 4


from enum import Enum

class CommandSafetyCategory(str, Enum):
    SAFE_READ = "SAFE_READ"
    SAFE_DIAGNOSTIC = "SAFE_DIAGNOSTIC"
    MUTATING = "MUTATING"
    HIGH_RISK = "HIGH_RISK"
    BLOCKED = "BLOCKED"


class AutonomyMode(str, Enum):
    LEVEL_0_CHAT_ONLY = "CHAT_ONLY"
    LEVEL_1_SUGGEST = "SUGGEST"
    LEVEL_2_SUPERVISED = "SUPERVISED"
    LEVEL_3_TASK_AUTONOMY = "TASK_AUTONOMY"


class PolicyCheckResult:
    def __init__(
        self,
        allowed: bool,
        level: int,
        requires_confirmation: bool = False,
        confirmation_id: Optional[str] = None,
        blocked: bool = False,
        reason: str = "",
        action_summary: str = "",
    ):
        self.allowed = allowed
        self.level = level
        self.requires_confirmation = requires_confirmation
        self.confirmation_id = confirmation_id
        self.blocked = blocked
        self.reason = reason
        self.action_summary = action_summary

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "level": self.level,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_id": self.confirmation_id,
            "blocked": self.blocked,
            "reason": self.reason,
            "action_summary": self.action_summary,
        }


class ActionPolicy:
    """Evaluates computer and tool action requests against security constraints."""

    # Explicit allowed development commands (prefix match)
    ALLOWED_DEV_COMMANDS = [
        "git status",
        "git diff",
        "git log",
        "git branch",
        "git remote",
        "git rev-parse",
        "git --version",
        "git -v",
        "pwd",
        "ls",
        "find",
        "which",
        "python --version",
        "python -V",
        "python3 --version",
        "python3 -V",
        "node --version",
        "node -v",
        "npm --version",
        "npm -v",
        "pytest",
        "python -m unittest",
        "python3 -m unittest",
        "npm run build",
        "npm test",
        "npm install",
        "npm run dev",
    ]

    # Dangerous shell tokens that are strictly blocked
    DANGEROUS_SHELL_TOKENS = [
        "sudo",
        "rm ",
        "rmdir",
        "mkfs",
        "dd ",
        "chmod",
        "chown",
        "kill",
        "pkill",
        "curl",
        "wget",
        "nc ",
        "netcat",
        "bash",
        "sh ",
        "zsh",
        "eval",
        "exec",
        ">",
        "<",
        "|",
        ";",
        "&&",
        "||",
        "`",
        "$",
    ]

    # Blocked sensitive path substrings
    FORBIDDEN_PATH_SUBSTRINGS = [
        "/.ssh",
        "/.aws",
        "/.gnupg",
        "/.config/gcloud",
        "/.bashrc",
        "/.zshrc",
        "/.zprofile",
        "/.env",
        "/etc/",
        "/var/",
        "/System/",
        "/Library/",
        "/usr/",
        "/bin/",
        "/sbin/",
        "id_rsa",
        "id_ed25519",
        "credentials",
        "secret",
    ]

    def __init__(self, workspace_root: Optional[str] = None, sandbox_dir: Optional[str] = None):
        # Determine environment mode (CLOUD vs LOCAL/SELF_HOSTED)
        try:
            from app.core.config import settings
            is_cloud = (
                getattr(settings, "is_cloud", False)
                or os.getenv("ENVIRONMENT", "").upper() == "CLOUD"
                or os.getenv("APP_ENV", "").upper() == "CLOUD"
                or getattr(settings, "NARAD_RUNTIME_MODE", "").lower() == "cloud"
            )
        except Exception:
            is_cloud = (
                os.getenv("ENVIRONMENT", "").upper() == "CLOUD"
                or os.getenv("APP_ENV", "").upper() == "CLOUD"
                or os.getenv("NARAD_RUNTIME_MODE", "").lower() == "cloud"
            )

        if is_cloud:
            # CLOUD mode: Default to a writable runtime directory (/tmp/narad)
            cloud_sandbox = os.path.realpath(sandbox_dir or os.getenv("NARAD_SANDBOX_DIR", "/tmp/narad"))
            self.sandbox_dir = cloud_sandbox
            self.workspace_root = os.path.realpath(workspace_root or os.getenv("NARAD_WORKSPACE_ROOT", self.sandbox_dir))
        else:
            # LOCAL / SELF_HOSTED mode: Preserve existing workspace & data/sandbox behavior
            current_file = os.path.abspath(__file__)
            # action_policy.py -> services -> app -> backend
            detected_backend = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
            detected_workspace = os.path.dirname(detected_backend)

            if os.path.basename(detected_backend) == "backend":
                default_workspace = detected_workspace
                default_backend = detected_backend
            else:
                default_workspace = detected_backend
                default_backend = detected_backend

            self.workspace_root = os.path.realpath(workspace_root or default_workspace)
            default_sandbox = os.path.join(default_backend, "data", "sandbox")
            self.sandbox_dir = os.path.realpath(sandbox_dir or default_sandbox)

        # Ensure sandbox directory exists, falling back safely to /tmp/narad if permissions prevent creation
        try:
            os.makedirs(self.sandbox_dir, exist_ok=True)
        except (PermissionError, OSError) as exc:
            logger.warning(
                f"[ActionPolicy] Permission denied creating sandbox at '{self.sandbox_dir}' ({exc}). "
                f"Falling back to temporary directory '/tmp/narad'."
            )
            self.sandbox_dir = os.path.realpath("/tmp/narad")
            os.makedirs(self.sandbox_dir, exist_ok=True)

        # Pending user confirmations: confirmation_id -> dict
        self._pending_confirmations: Dict[str, Dict[str, Any]] = {}

        # V6 Autonomy Mode (Phase 32 & 33)
        self.autonomy_mode: AutonomyMode = AutonomyMode.LEVEL_2_SUPERVISED

        # V6 Task-Scoped Batch Permissions: task_id -> set of allowed permission tuples (Phase 9 / Bug 4 & 6)
        self._task_scope_permissions: Dict[str, set] = {}

    @staticmethod
    def classify_development_command(command: str) -> Tuple[CommandSafetyCategory, PermissionLevel, str]:
        """Classify a development shell command into a safety category and permission level (BUG 1 & 2).

        Returns:
            (CommandSafetyCategory, PermissionLevel, rationale)
        """
        if not command or not command.strip():
            return CommandSafetyCategory.BLOCKED, PermissionLevel.LEVEL_4_BLOCKED, "Command cannot be empty."

        cleaned_cmd = command.strip()

        # 1. Dangerous shell tokens and metacharacters (defense in depth, prevent command chaining)
        for token in ActionPolicy.DANGEROUS_SHELL_TOKENS:
            if token in cleaned_cmd:
                return (
                    CommandSafetyCategory.BLOCKED,
                    PermissionLevel.LEVEL_4_BLOCKED,
                    f"Command contains prohibited token or metacharacter: '{token}'.",
                )

        # 2. Check for sensitive filesystem path leaks
        lower_cmd = cleaned_cmd.lower()
        for forbidden in ActionPolicy.FORBIDDEN_PATH_SUBSTRINGS:
            if forbidden.lower() in lower_cmd:
                return (
                    CommandSafetyCategory.BLOCKED,
                    PermissionLevel.LEVEL_4_BLOCKED,
                    f"Access to sensitive path pattern '{forbidden}' is strictly blocked.",
                )

        # 3. Parse tokens safely without shell execution
        try:
            tokens = shlex.split(cleaned_cmd)
        except Exception as e:
            return (
                CommandSafetyCategory.BLOCKED,
                PermissionLevel.LEVEL_4_BLOCKED,
                f"Failed to safely parse command syntax: {e}",
            )

        if not tokens:
            return CommandSafetyCategory.BLOCKED, PermissionLevel.LEVEL_4_BLOCKED, "Empty command tokens."

        prog = tokens[0].lower()
        sub = tokens[1].lower() if len(tokens) > 1 else ""

        # Version queries across runtime tools (SAFE_READ / Level 0)
        if prog in ("python", "python3", "node", "npm", "git") and sub in ("--version", "-v", "-V", "version"):
            return CommandSafetyCategory.SAFE_READ, PermissionLevel.LEVEL_0_SAFE, f"Read-only version query for '{prog}'."

        # Git operations (BUG 1: git status, branch, log, diff, remote, rev-parse are read-only)
        if prog == "git":
            if not sub:
                return CommandSafetyCategory.SAFE_READ, PermissionLevel.LEVEL_0_SAFE, "Read-only git command."

            if sub == "status":
                return CommandSafetyCategory.SAFE_READ, PermissionLevel.LEVEL_0_SAFE, "Read-only git status diagnostic."

            if sub == "diff":
                return CommandSafetyCategory.SAFE_READ, PermissionLevel.LEVEL_0_SAFE, "Read-only git diff diagnostic."

            if sub == "log":
                return CommandSafetyCategory.SAFE_READ, PermissionLevel.LEVEL_0_SAFE, "Read-only git log diagnostic."

            if sub == "branch":
                mutating_branch_flags = {"-d", "-D", "-m", "-M", "--delete", "--move"}
                if any(f in tokens for f in mutating_branch_flags):
                    return CommandSafetyCategory.MUTATING, PermissionLevel.LEVEL_2_CONFIRM, "Mutating git branch operation."
                return CommandSafetyCategory.SAFE_READ, PermissionLevel.LEVEL_0_SAFE, "Read-only git branch diagnostic."

            if sub == "remote":
                if any(act in tokens for act in ("add", "remove", "rm", "set-url", "rename")):
                    return CommandSafetyCategory.MUTATING, PermissionLevel.LEVEL_2_CONFIRM, "Mutating git remote operation."
                return CommandSafetyCategory.SAFE_READ, PermissionLevel.LEVEL_0_SAFE, "Read-only git remote diagnostic."

            if sub == "rev-parse":
                return CommandSafetyCategory.SAFE_READ, PermissionLevel.LEVEL_0_SAFE, "Read-only git rev-parse diagnostic."

            if sub in ("show", "describe"):
                return CommandSafetyCategory.SAFE_READ, PermissionLevel.LEVEL_0_SAFE, f"Read-only git {sub} diagnostic."

            # Explicit mutating git subcommands
            if sub in ("push", "pull", "fetch", "commit", "checkout", "switch", "merge", "rebase", "stash", "reset", "clean", "init", "clone", "add", "mv", "rm", "tag"):
                return CommandSafetyCategory.MUTATING, PermissionLevel.LEVEL_2_CONFIRM, f"Mutating git operation '{sub}'."

            return CommandSafetyCategory.MUTATING, PermissionLevel.LEVEL_2_CONFIRM, f"Git command '{cleaned_cmd}' requires confirmation."

        # System read-only commands
        if prog == "pwd":
            return CommandSafetyCategory.SAFE_READ, PermissionLevel.LEVEL_0_SAFE, "Read-only pwd command."

        if prog in ("ls", "dir"):
            return CommandSafetyCategory.SAFE_READ, PermissionLevel.LEVEL_0_SAFE, "Read-only directory listing."

        if prog == "which":
            return CommandSafetyCategory.SAFE_READ, PermissionLevel.LEVEL_0_SAFE, "Read-only binary path lookup."

        if prog == "find":
            if any(flag in tokens for flag in ("-delete", "-exec", "-execdir")):
                return CommandSafetyCategory.BLOCKED, PermissionLevel.LEVEL_4_BLOCKED, "Destructive find command flag is prohibited."
            return CommandSafetyCategory.SAFE_READ, PermissionLevel.LEVEL_0_SAFE, "Read-only filesystem search."

        # Safe diagnostics (build compilers and unit tests)
        if prog == "npm" and len(tokens) >= 3 and tokens[1] == "run" and tokens[2] == "build":
            return CommandSafetyCategory.SAFE_DIAGNOSTIC, PermissionLevel.LEVEL_0_SAFE, "Frontend build compilation diagnostic."

        if (prog == "npm" and sub == "test") or prog == "pytest":
            return CommandSafetyCategory.SAFE_DIAGNOSTIC, PermissionLevel.LEVEL_0_SAFE, f"Diagnostic test runner '{prog}'."

        if prog in ("python", "python3") and len(tokens) >= 3 and tokens[1:3] == ["-m", "unittest"]:
            return CommandSafetyCategory.SAFE_DIAGNOSTIC, PermissionLevel.LEVEL_0_SAFE, "Python unittest diagnostic."

        # Mutating package managers and process launchers
        if prog == "npm" and sub in ("install", "i", "add", "update", "ci"):
            return CommandSafetyCategory.MUTATING, PermissionLevel.LEVEL_2_CONFIRM, "Package installation modifies node_modules."

        if prog == "npm" and (sub == "start" or (len(tokens) >= 3 and tokens[1] == "run" and tokens[2] in ("dev", "start"))):
            return CommandSafetyCategory.MUTATING, PermissionLevel.LEVEL_2_CONFIRM, "Command starts long-running development server."

        if (prog == "pip" and sub == "install") or (prog in ("python", "python3") and len(tokens) >= 4 and tokens[1:4] == ["-m", "pip", "install"]):
            return CommandSafetyCategory.MUTATING, PermissionLevel.LEVEL_2_CONFIRM, "Mutating python package installation."

        if prog in ("touch", "mkdir"):
            return CommandSafetyCategory.MUTATING, PermissionLevel.LEVEL_2_CONFIRM, f"Filesystem command '{prog}' modifies directory contents."

        # Explicitly blocked commands
        if prog in ("sudo", "rm", "rmdir", "kill", "pkill", "dd", "mkfs", "chmod", "chown", "curl", "wget"):
            return CommandSafetyCategory.BLOCKED, PermissionLevel.LEVEL_4_BLOCKED, f"Command '{prog}' is strictly prohibited."

        # Unclassified commands default to Level 2
        return CommandSafetyCategory.MUTATING, PermissionLevel.LEVEL_2_CONFIRM, f"Development command '{cleaned_cmd}' requires confirmation."

    def get_allowed_roots(self) -> List[str]:
        """Return allowed canonical filesystem root paths."""
        return [self.workspace_root, self.sandbox_dir]

    def validate_path_sandbox(self, target_path: str) -> Tuple[bool, str, str]:
        """Validate if a path is safe and inside the allowed sandbox roots.

        Returns (is_safe, canonical_path, error_message).
        """
        if not target_path or not target_path.strip():
            return False, "", "Path cannot be empty."

        cleaned = os.path.expanduser(target_path.strip())

        # Resolve canonical absolute path
        canonical = os.path.realpath(os.path.abspath(cleaned))

        # Check forbidden substrings (credentials, keys, sensitive system paths)
        canonical_lower = canonical.lower()
        for forbidden in self.FORBIDDEN_PATH_SUBSTRINGS:
            if forbidden.lower() in canonical_lower:
                return False, canonical, f"Access to sensitive path pattern '{forbidden}' is strictly blocked."

        # Check that canonical path starts with one of the allowed roots
        is_inside_allowed = any(
            canonical == root or canonical.startswith(root + os.sep)
            for root in self.get_allowed_roots()
        )

        if not is_inside_allowed:
            return (
                False,
                canonical,
                f"Path '{target_path}' is outside the authorized workspace and sandbox directories.",
            )

        return True, canonical, ""

    def validate_command(self, cmd: str) -> Tuple[bool, str]:
        """Validate a development command against safety rules and blocked tokens."""
        if not cmd or not cmd.strip():
            return False, "Command cannot be empty."

        category, level, reason = self.classify_development_command(cmd)
        if category == CommandSafetyCategory.BLOCKED or level == PermissionLevel.LEVEL_4_BLOCKED:
            return False, reason

        return True, ""

    def get_permission_level(self, tool_name: str, tool_args: Optional[Dict[str, Any]] = None) -> int:
        """Helper to get integer permission level for a tool."""
        level, _, _ = self.classify_action(tool_name, tool_args or {})
        return level

    def classify_action(self, tool_name: str, tool_args: Dict[str, Any]) -> Tuple[int, str, str]:
        """Classify tool action into risk level 0-4, returning (level, action_summary, reason)."""
        tool_name = tool_name.strip().lower()

        # Safe Read-Only tools (Level 0)
        if tool_name in (
            "get_current_time",
            "get_current_date",
            "calculator",
            "retrieve_memory",
            "list_memories",
            "web_search",
            "search_knowledge",
            "get_active_application",
            "get_system_state",
            "inspect_screen",
            "take_screenshot",
            "observe_screen",
            "understand_screen",
            "detect_screen_change",
            "open_url",
            "open_application",
            "browser_navigate",
            "browser_observe_output",
        ):
            return PermissionLevel.LEVEL_0_SAFE, f"Execute {tool_name}", "Safe read-only or application interaction."

        # Apple Music Control: play/pause/status is Level 0
        if tool_name == "control_apple_music":
            action = str(tool_args.get("action", "play")).lower()
            track = tool_args.get("track", "")
            summary = f"Apple Music {action} '{track}'" if track else f"Apple Music {action}"
            return PermissionLevel.LEVEL_0_SAFE, summary, "Safe media playback control."

        # Sandboxed Filesystem: Read and List (Level 0 if in sandbox, Level 4 if outside)
        if tool_name in ("read_file", "list_directory"):
            path = tool_args.get("path") or tool_args.get("file_path") or tool_args.get("directory_path", "")
            is_safe, canonical, err = self.validate_path_sandbox(str(path))
            if not is_safe:
                return PermissionLevel.LEVEL_4_BLOCKED, f"{tool_name} on {path}", err
            return PermissionLevel.LEVEL_0_SAFE, f"{tool_name} at {os.path.basename(canonical)}", "Read within allowed sandbox."

        # Level 1: Low Risk (e.g., focus application, browser code/compiler interaction)
        if tool_name in ("focus_application", "browser_paste_code", "browser_run_code", "browser_enter_input", "browser_compiler_workflow"):
            summary = f"Browser interaction: {tool_name}"
            if tool_name == "focus_application":
                app = tool_args.get("application", "")
                summary = f"Focus {app}"
            elif tool_name == "browser_paste_code":
                summary = "Paste code into web editor"
            elif tool_name == "browser_run_code":
                summary = "Execute code in web compiler"
            elif tool_name == "browser_enter_input":
                summary = f"Enter stdin input '{tool_args.get('input_text', '')}'"
            elif tool_name == "browser_compiler_workflow":
                summary = "Execute verified online compiler workflow"
            return PermissionLevel.LEVEL_1_LOW, summary, "Safe browser application interaction."

        # Level 2: Confirm required (create file, create folder, move file, run dev command)
        if tool_name in ("create_file", "create_folder", "move_file"):
            target = tool_args.get("path") or tool_args.get("file_path") or tool_args.get("destination", "")
            is_safe, canonical, err = self.validate_path_sandbox(str(target))
            if not is_safe:
                return PermissionLevel.LEVEL_4_BLOCKED, f"{tool_name} {target}", err

            if tool_name == "move_file":
                src = tool_args.get("source", "")
                is_safe_src, _, err_src = self.validate_path_sandbox(str(src))
                if not is_safe_src:
                    return PermissionLevel.LEVEL_4_BLOCKED, f"move_file from {src}", err_src
                summary = f"Move file '{os.path.basename(src)}' to '{os.path.basename(canonical)}'"
            elif tool_name == "create_file":
                summary = f"Create file '{os.path.basename(canonical)}'"
            else:
                summary = f"Create directory '{os.path.basename(canonical)}'"

            return PermissionLevel.LEVEL_2_CONFIRM, summary, "Modifies filesystem contents within workspace."

        if tool_name == "run_development_command":
            cmd = str(tool_args.get("command", "")).strip()
            cat, lvl, reason = self.classify_development_command(cmd)
            if cat == CommandSafetyCategory.BLOCKED or lvl == PermissionLevel.LEVEL_4_BLOCKED:
                return PermissionLevel.LEVEL_4_BLOCKED, f"Run command: {cmd}", reason
            return lvl, f"Run development command '{cmd}'", reason

        # Level 3: High Risk (delete file, close application)
        if tool_name == "delete_file":
            path = tool_args.get("path") or tool_args.get("file_path", "")
            is_safe, canonical, err = self.validate_path_sandbox(str(path))
            if not is_safe:
                return PermissionLevel.LEVEL_4_BLOCKED, f"Delete file {path}", err
            return PermissionLevel.LEVEL_3_HIGH, f"Delete file '{os.path.basename(canonical)}'", "Destructive file removal."

        if tool_name == "close_application":
            app = tool_args.get("application", "")
            return PermissionLevel.LEVEL_3_HIGH, f"Quit application '{app}'", "Terminates running application."

        if tool_name in ("save_memory", "delete_memory"):
            # Existing memory tools
            return PermissionLevel.LEVEL_0_SAFE, f"Manage memory ({tool_name})", "Safe memory store."

        # Check if the tool is dynamically registered in kriya_dispatcher (e.g., test tools)
        from app.services.kriya import kriya_dispatcher
        registered = kriya_dispatcher.get_tool(tool_name)
        if registered is not None:
            lvl = getattr(registered, "permission_level", 0)
            return lvl, f"Execute {tool_name}", "Registered tool execution."

        # Unknown or unspecified tools are blocked by default
        return (
            PermissionLevel.LEVEL_4_BLOCKED,
            f"Unknown tool: {tool_name}",
            f"Tool '{tool_name}' is not recognized or authorized.",
        )

    def is_authorized_for_task(self, task_id: str, tool_name: str, tool_args: Dict[str, Any]) -> bool:
        """Check if action is explicitly authorized for active task (BUG 4 & 6)."""
        if not task_id or task_id not in self._task_scope_permissions:
            return False

        perms = self._task_scope_permissions[task_id]

        if tool_name == "run_development_command":
            cmd = str(tool_args.get("command", "")).strip()
            cat, _, _ = self.classify_development_command(cmd)
            # Never authorize blocked or high-risk
            if cat in (CommandSafetyCategory.BLOCKED, CommandSafetyCategory.HIGH_RISK):
                return False
            # Check exact command match
            if ("cmd", cmd) in perms:
                return True
            # Check safe diagnostic category match
            if cat == CommandSafetyCategory.SAFE_DIAGNOSTIC and ("category", "SAFE_DIAGNOSTIC") in perms:
                return True
            return False

        if tool_name in ("create_file", "create_folder", "move_file"):
            if ("tool", tool_name) in perms:
                return True
            return False

        # Destructive tools (delete_file, close_application) cannot be auto-authorized
        return False

    def _log_evaluation(
        self,
        action_summary: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        level: int,
        result: PolicyCheckResult,
    ):
        """Structured development logging (BUG 13 - no secrets logged)."""
        if tool_name == "run_development_command":
            cat_enum, _, _ = self.classify_development_command(tool_args.get("command", ""))
            cat_str = cat_enum.value
        else:
            if level == PermissionLevel.LEVEL_0_SAFE:
                cat_str = "SAFE_READ"
            elif level == PermissionLevel.LEVEL_1_LOW:
                cat_str = "LOW_RISK"
            elif level == PermissionLevel.LEVEL_2_CONFIRM:
                cat_str = "MUTATING"
            elif level == PermissionLevel.LEVEL_3_HIGH:
                cat_str = "HIGH_RISK"
            else:
                cat_str = "BLOCKED"

        policy_str = f"LEVEL {int(level)}"
        conf_str = "REQUIRED" if result.requires_confirmation else "NOT_REQUIRED"
        exec_str = "APPROVED" if result.allowed else ("BLOCKED" if result.blocked else "PENDING_CONFIRMATION")

        logger.info(
            f"\n[ActionPolicy Evaluation]\n"
            f"ACTION:\n  {action_summary}\n"
            f"CLASSIFICATION:\n  {cat_str}\n"
            f"POLICY:\n  {policy_str}\n"
            f"CONFIRMATION:\n  {conf_str}\n"
            f"EXECUTION:\n  {exec_str}\n"
        )

    def evaluate_request(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        confirmation_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> PolicyCheckResult:
        """Evaluate an action request against permissions, autonomy mode, and user confirmations."""
        level, action_summary, reason = self.classify_action(tool_name, tool_args)

        # Autonomy Mode Level 0: Chat only - all computer actions are blocked
        if self.autonomy_mode == AutonomyMode.LEVEL_0_CHAT_ONLY:
            res = PolicyCheckResult(
                allowed=False,
                level=level,
                blocked=True,
                reason="Computer actions are disabled in CHAT_ONLY autonomy mode.",
                action_summary=action_summary,
            )
            self._log_evaluation(action_summary, tool_name, tool_args, level, res)
            return res

        # Autonomy Mode Level 1: Suggest only - propose actions but do not execute
        if self.autonomy_mode == AutonomyMode.LEVEL_1_SUGGEST:
            res = PolicyCheckResult(
                allowed=False,
                level=level,
                blocked=True,
                reason="Execution is disabled in SUGGEST autonomy mode. Only action proposals are permitted.",
                action_summary=action_summary,
            )
            self._log_evaluation(action_summary, tool_name, tool_args, level, res)
            return res

        # Level 4 is strictly blocked under ALL modes and cannot be overridden
        if level == PermissionLevel.LEVEL_4_BLOCKED:
            res = PolicyCheckResult(
                allowed=False,
                level=level,
                blocked=True,
                reason=reason,
                action_summary=action_summary,
            )
            self._log_evaluation(action_summary, tool_name, tool_args, level, res)
            return res

        # Level 0 and Level 1 are safe and allowed immediately
        if level in (PermissionLevel.LEVEL_0_SAFE, PermissionLevel.LEVEL_1_LOW):
            res = PolicyCheckResult(
                allowed=True,
                level=level,
                requires_confirmation=False,
                reason=reason,
                action_summary=action_summary,
            )
            self._log_evaluation(action_summary, tool_name, tool_args, level, res)
            return res

        # Check Task-Scoped Batch Permissions (BUG 4 & 6: "ALLOW FOR THIS TASK")
        if task_id and self.is_authorized_for_task(task_id, tool_name, tool_args):
            res = PolicyCheckResult(
                allowed=True,
                level=level,
                requires_confirmation=False,
                reason=f"Action pre-authorized for task '{task_id}'.",
                action_summary=action_summary,
            )
            self._log_evaluation(action_summary, tool_name, tool_args, level, res)
            return res

        # Level 3 Task Autonomy Mode: safe modifying actions planned as part of an approved task can execute
        # Note: High risk Level 3 actions (delete_file, close_application) remain gated! (BUG 7)
        if self.autonomy_mode == AutonomyMode.LEVEL_3_TASK_AUTONOMY and level == PermissionLevel.LEVEL_2_CONFIRM:
            res = PolicyCheckResult(
                allowed=True,
                level=level,
                requires_confirmation=False,
                reason="Auto-authorized under TASK_AUTONOMY mode.",
                action_summary=action_summary,
            )
            self._log_evaluation(action_summary, tool_name, tool_args, level, res)
            return res

        # Level 2 and Level 3 require confirmation
        if confirmation_id:
            # Check if this confirmation was already approved
            pending = self._pending_confirmations.get(confirmation_id)
            if pending and pending.get("status") in ("allowed", "approved"):
                # Exact matching (BUG 6): verify tool_name AND tool_args match
                tool_matches = (pending.get("tool_name") == tool_name)
                pending_args = pending.get("tool_args", {})
                args_match = (pending_args == tool_args)
                if tool_name == "run_development_command":
                    args_match = (str(pending_args.get("command", "")).strip() == str(tool_args.get("command", "")).strip())

                if tool_matches and args_match:
                    # Single-use: Mark confirmation as consumed (BUG 3 & BUG 12)
                    pending["status"] = "consumed"
                    pending["consumed_at"] = time.time()
                    res = PolicyCheckResult(
                        allowed=True,
                        level=level,
                        requires_confirmation=False,
                        confirmation_id=confirmation_id,
                        reason="Action confirmed by user.",
                        action_summary=action_summary,
                    )
                    self._log_evaluation(action_summary, tool_name, tool_args, level, res)
                    return res
                else:
                    logger.warning(f"[ActionPolicy] Confirmation mismatch: {pending.get('tool_name')} vs {tool_name}")
            elif pending and pending.get("status") == "denied":
                res = PolicyCheckResult(
                    allowed=False,
                    level=level,
                    requires_confirmation=False,
                    confirmation_id=confirmation_id,
                    reason="Action denied by user.",
                    action_summary=action_summary,
                )
                self._log_evaluation(action_summary, tool_name, tool_args, level, res)
                return res

        # Generate new confirmation request
        new_id = f"conf_{uuid.uuid4().hex[:8]}"
        self._pending_confirmations[new_id] = {
            "confirmation_id": new_id,
            "task_id": task_id,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "level": int(level),
            "description": action_summary,
            "reason": reason,
            "status": "pending",
            "created_at": time.time(),
        }

        res = PolicyCheckResult(
            allowed=False,
            level=level,
            requires_confirmation=True,
            confirmation_id=new_id,
            reason=f"Action requires user confirmation ({action_summary}).",
            action_summary=action_summary,
        )
        self._log_evaluation(action_summary, tool_name, tool_args, level, res)
        return res

    def decide_confirmation(self, confirmation_id: str, decision: str) -> Dict[str, Any]:
        """Record user decision ('allow', 'allow_task', or 'deny') for a pending confirmation."""
        decision = decision.lower().strip()
        if decision not in ("allow", "allow_task", "deny"):
            return {"success": False, "error": f"Invalid decision: '{decision}'. Must be 'allow', 'allow_task', or 'deny'."}

        pending = self._pending_confirmations.get(confirmation_id)
        if not pending:
            return {"success": False, "error": f"Confirmation request '{confirmation_id}' not found."}

        is_allowed = decision in ("allow", "allow_task")
        pending["status"] = "allowed" if is_allowed else "denied"
        pending["decision_type"] = decision
        pending["decided_at"] = time.time()

        # Batch authorization for active task (BUG 4 & BUG 6)
        if decision == "allow_task":
            task_id = pending.get("task_id")
            if task_id:
                if task_id not in self._task_scope_permissions:
                    self._task_scope_permissions[task_id] = set()
                tool = pending.get("tool_name")
                args = pending.get("tool_args", {})
                if tool == "run_development_command":
                    cmd = str(args.get("command", "")).strip()
                    cat, _, _ = self.classify_development_command(cmd)
                    self._task_scope_permissions[task_id].add(("cmd", cmd))
                    if cat == CommandSafetyCategory.SAFE_DIAGNOSTIC:
                        self._task_scope_permissions[task_id].add(("category", "SAFE_DIAGNOSTIC"))
                elif tool in ("create_file", "create_folder", "move_file"):
                    self._task_scope_permissions[task_id].add(("tool", tool))
                logger.info(f"[ActionPolicy Task Auth] Stored task-scoped permission for {task_id}: {tool}")

        return {
            "success": True,
            "confirmation_id": confirmation_id,
            "decision": decision,
            "decision_type": decision,
            "status": "approved" if is_allowed else "denied",
            "action_summary": pending.get("description", ""),
            "tool_name": pending.get("tool_name", ""),
            "task_id": pending.get("task_id"),
        }

    def clear_task_permissions(self, task_id: str):
        """Purge temporary task-scoped authorizations when a task ends."""
        if task_id in self._task_scope_permissions:
            del self._task_scope_permissions[task_id]
            logger.info(f"[ActionPolicy Batch] Cleared task-scoped permissions for {task_id}")

    def get_autonomy_mode(self) -> str:
        """Return the active autonomy mode."""
        return self.autonomy_mode.value

    def set_autonomy_mode(self, mode: str) -> Dict[str, Any]:
        """Update active autonomy mode with strict validation (Level 4 rejected)."""
        clean_mode = mode.upper().strip()
        valid_modes = {
            "CHAT_ONLY": AutonomyMode.LEVEL_0_CHAT_ONLY,
            "SUGGEST": AutonomyMode.LEVEL_1_SUGGEST,
            "SUPERVISED": AutonomyMode.LEVEL_2_SUPERVISED,
            "TASK_AUTONOMY": AutonomyMode.LEVEL_3_TASK_AUTONOMY,
        }
        if clean_mode not in valid_modes:
            return {
                "success": False,
                "error": f"Invalid autonomy mode '{mode}'. Allowed modes: {list(valid_modes.keys())}. Level 4 unrestricted autonomy is prohibited.",
            }
        self.autonomy_mode = valid_modes[clean_mode]
        logger.info(f"[ActionPolicy Autonomy] Switched autonomy mode to: {self.autonomy_mode.value}")
        return {"success": True, "autonomy_mode": self.autonomy_mode.value}

    def get_pending_confirmation(self, confirmation_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve confirmation details."""
        return self._pending_confirmations.get(confirmation_id)

    def list_pending_confirmations(self) -> List[Dict[str, Any]]:
        """List all pending confirmation requests."""
        return [
            item for item in self._pending_confirmations.values()
            if item["status"] == "pending"
        ]


# Global singleton action policy
action_policy = ActionPolicy()
classify_development_command = ActionPolicy.classify_development_command
