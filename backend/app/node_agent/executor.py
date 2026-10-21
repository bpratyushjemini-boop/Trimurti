"""
NARAD Phase 3.5 — Safe Local Node Action Executor.
Enforces strict sandboxing and permission validation on local macOS operations.
Explicitly prohibits arbitrary shell execution, unrestricted AppleScript,
arbitrary file access, and silent background recording.
"""

import os
import platform
import re
import subprocess
import time
import datetime
from typing import Any, Dict, Optional, Set
import logging

logger = logging.getLogger("narad.node_agent.executor")

# Allowlisted applications for safe launching on macOS
ALLOWED_APPLICATIONS: Dict[str, str] = {
    "music": "Music",
    "apple music": "Music",
    "safari": "Safari",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
    "calculator": "Calculator",
    "finder": "Finder",
    "terminal": "Terminal",
    "preview": "Preview",
    "textedit": "TextEdit",
    "notes": "Notes",
    "calendar": "Calendar",
    "system settings": "System Settings",
    "settings": "System Settings",
}

# Strictly forbidden command tokens to prevent any injection
FORBIDDEN_TOKENS: Set[str] = {
    "sudo", "rm ", "rmdir", "mkfs", "dd ", "chmod", "chown", "kill",
    "pkill", "curl", "wget", "nc ", "netcat", "bash", "sh ", "zsh",
    "eval", "exec", ";", "&&", "||", "`", "$", "|", ">", "<",
}


def sanitize_input_string(value: str) -> str:
    """Strip quotes, backslashes, and control characters to prevent shell injection."""
    if not value or not isinstance(value, str):
        return ""
    cleaned = value.replace("\\", "").replace('"', "").replace("'", "").replace("\n", " ").replace("\r", " ")
    return cleaned.strip()


class SafeNodeExecutor:
    """
    Executes approved, sandboxed commands on the local Mac node.
    Enforces strict allowlists and permission constraints.
    """

    def __init__(self, screenshots_dir: Optional[str] = None):
        self.os_name = platform.system()
        self.arch = platform.machine()
        # Default screenshots directory in user's home or temp
        home = os.path.expanduser("~")
        default_dir = os.path.join(home, ".narad", "screenshots")
        self.screenshots_dir = screenshots_dir or default_dir
        try:
            os.makedirs(self.screenshots_dir, exist_ok=True)
        except Exception:
            self.screenshots_dir = os.path.join(os.path.expanduser("~"), "Downloads")

    def execute(self, action_type: str, payload: Dict[str, Any], confirmed: bool = False) -> Dict[str, Any]:
        """
        Execute a received command relay action safely.
        Returns execution result dictionary or raises ValueError.
        """
        clean_action = (action_type or "").strip().lower()

        if clean_action == "node_status":
            return self.get_node_status()

        elif clean_action in ("diagnostics", "get_system_state"):
            return self.get_diagnostics()

        elif clean_action == "open_application":
            app_name = payload.get("application", "")
            path = payload.get("path")
            return self.open_application(app_name, path=path)

        elif clean_action == "take_screenshot":
            # Screen capture requires explicit confirmation
            filename = payload.get("filename")
            is_confirmed = confirmed or bool(payload.get("confirmed", False))
            return self.take_screenshot(filename=filename, confirmed=is_confirmed)

        else:
            logger.warning(f"[SafeNodeExecutor] Prohibited action rejected: '{clean_action}'")
            return {
                "success": False,
                "error": "ACTION_PROHIBITED",
                "message": f"Action '{clean_action}' is not permitted on this secure node. Arbitrary commands are blocked.",
            }

    def get_node_status(self) -> Dict[str, Any]:
        """Report genuine macOS node status and platform facts."""
        active_app = self._get_active_application()
        return {
            "success": True,
            "platform": self.os_name,
            "machine": self.arch,
            "release": platform.release(),
            "mac_ver": platform.mac_ver()[0] if self.os_name == "Darwin" else "N/A",
            "active_application": active_app,
            "node_type": "Apple Silicon Node" if self.arch == "arm64" else "Intel Mac Node",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    def get_diagnostics(self) -> Dict[str, Any]:
        """Retrieve approved non-sensitive diagnostic info."""
        active_app = self._get_active_application()
        screencapture_available = (
            self.os_name == "Darwin" and os.path.exists("/usr/sbin/screencapture")
        )
        return {
            "success": True,
            "platform": self.os_name,
            "machine": self.arch,
            "release": platform.release(),
            "active_application": active_app,
            "screencapture_available": screencapture_available,
            "screenshots_dir": self.screenshots_dir,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    def open_application(self, app_name: str, path: Optional[str] = None) -> Dict[str, Any]:
        """
        Open an explicitly requested application from the allowlist.
        Does not execute shell scripts or arbitrary binaries.
        """
        if not app_name or not app_name.strip():
            return {"success": False, "error": "Application name cannot be empty."}

        # Check for forbidden injection tokens
        for token in FORBIDDEN_TOKENS:
            if token in app_name.lower():
                return {
                    "success": False,
                    "error": "PROHIBITED_TOKEN",
                    "message": f"Application name contains prohibited token '{token}'.",
                }

        cleaned = app_name.strip().lower()
        resolved_app = ALLOWED_APPLICATIONS.get(cleaned)
        if not resolved_app:
            return {
                "success": False,
                "error": "APPLICATION_NOT_ALLOWLISTED",
                "message": (
                    f"Application '{app_name}' is not in the allowed application registry. "
                    f"Allowed applications: {sorted(set(ALLOWED_APPLICATIONS.values()))}"
                ),
            }

        if self.os_name != "Darwin":
            return {"success": False, "error": "open_application requires macOS (Darwin)."}

        sanitized_app = sanitize_input_string(resolved_app)
        cmd = ["/usr/bin/open", "-a", sanitized_app]

        if path and path.strip():
            # Validate path doesn't contain forbidden shell tokens
            for token in FORBIDDEN_TOKENS:
                if token in path:
                    return {
                        "success": False,
                        "error": "PROHIBITED_TOKEN",
                        "message": f"Path contains prohibited token '{token}'.",
                    }
            target_path = os.path.expanduser(path.strip())
            cmd.append(target_path)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=8,
                shell=False,  # Strictly shell=False to prevent shell injection
            )
            if proc.returncode == 0:
                time.sleep(0.2)
                return {
                    "success": True,
                    "application": resolved_app,
                    "path": path,
                    "message": f"Successfully launched {resolved_app}.",
                }
            else:
                return {
                    "success": False,
                    "application": resolved_app,
                    "error": proc.stderr.strip() or f"Process returned code {proc.returncode}",
                }
        except Exception as e:
            return {"success": False, "application": resolved_app, "error": str(e)}

    def take_screenshot(self, filename: Optional[str] = None, confirmed: bool = False) -> Dict[str, Any]:
        """
        Capture the screen only with explicit user confirmation.
        Silent recording without confirmation is strictly rejected.
        """
        if not confirmed:
            return {
                "success": False,
                "error": "CONFIRMATION_REQUIRED",
                "message": "Screen capture requires explicit user confirmation. Silent recording is prohibited.",
            }

        if self.os_name != "Darwin":
            return {"success": False, "error": "Screen capture requires macOS (Darwin)."}

        screencapture_bin = "/usr/sbin/screencapture"
        if not os.path.exists(screencapture_bin):
            return {"success": False, "error": f"{screencapture_bin} utility not found on this system."}

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = f"narad_screen_{timestamp}.png" if not filename else filename
        if not safe_name.endswith(".png"):
            safe_name += ".png"
        safe_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", os.path.basename(safe_name))
        file_path = os.path.join(self.screenshots_dir, safe_name)

        try:
            # -x: disable capture sound
            proc = subprocess.run(
                [screencapture_bin, "-x", file_path],
                capture_output=True,
                text=True,
                timeout=10,
                shell=False,
            )
            if proc.returncode == 0 and os.path.exists(file_path):
                size = os.path.getsize(file_path)
                return {
                    "success": True,
                    "file_path": file_path,
                    "filename": safe_name,
                    "size_bytes": size,
                    "message": f"Captured screenshot to {safe_name} ({size} bytes).",
                }
            else:
                return {
                    "success": False,
                    "error": proc.stderr.strip() or f"screencapture exited with code {proc.returncode}",
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_active_application(self) -> str:
        """Query frontmost macOS application safely via osascript with shell=False."""
        if self.os_name != "Darwin":
            return "N/A"
        script = 'tell application "System Events" to get name of first application process whose frontmost is true'
        try:
            proc = subprocess.run(
                ["/usr/bin/osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=4,
                shell=False,
            )
            if proc.returncode == 0:
                return proc.stdout.strip() or "Unknown"
        except Exception:
            pass
        return "Unknown"
