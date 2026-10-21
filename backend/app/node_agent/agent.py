"""
NARAD Phase 3.5 — Lightweight Mac Node Agent.
Outbound-only daemon connecting a local macOS host to the NARAD Cloud backend.
Handles:
- Authenticated registration & periodic heartbeats
- Genuine hardware capability reporting
- Safe command relay polling & execution
- Exponential backoff & resilient reconnection
- Graceful shutdown with OFFLINE status notification
"""

import json
import logging
import os
import platform
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from app.node_agent.executor import SafeNodeExecutor

logger = logging.getLogger("narad.node_agent")


class MacNodeAgent:
    """
    Dedicated lightweight macOS agent connecting outbound to NARAD Cloud.
    Requires no open inbound ports and no administrator privileges.
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        token: Optional[str] = None,
        heartbeat_interval: float = 30.0,
        poll_interval: float = 2.0,
        executor: Optional[SafeNodeExecutor] = None,
    ):
        raw_server = server_url or os.getenv("NARAD_SERVER_URL") or os.getenv("NARAD_CLOUD_URL") or "https://narad-gqtp.onrender.com"
        self.server_url = raw_server.rstrip("/")
        # Stable node ID based on machine hostname or custom ID
        clean_host = re_sanitize = "".join(c for c in platform.node() if c.isalnum() or c in ("-", "_"))
        self.node_id = node_id or os.getenv("NARAD_NODE_ID") or f"mac_{clean_host or 'laptop'}"
        self.node_name = node_name or os.getenv("NARAD_NODE_NAME") or f"{platform.node()} ({platform.machine()})"
        self.token = token or os.getenv("NARAD_NODE_TOKEN") or os.getenv("NARAD_API_KEY") or ""
        self.heartbeat_interval = heartbeat_interval
        self.poll_interval = poll_interval

        self.executor = executor or SafeNodeExecutor()
        self.running = False
        self._last_heartbeat_time = 0.0
        self.is_online = False
        self.last_confirmed_status: Optional[str] = None

        # Backoff tracking for network resilience
        self._consecutive_failures = 0
        self._max_backoff_seconds = 30.0

    # =========================================================================
    # HTTP REQUEST HELPER (Outbound HTTPS only)
    # =========================================================================

    def _send_request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """
        Send an outbound HTTPS/HTTP request with authentication headers.
        Never transmits credentials in URLs or query strings.
        """
        url = f"{self.server_url}{path}"
        headers = {
            "User-Agent": "NARAD-MacNodeAgent/3.5",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["X-Node-Token"] = self.token
            headers["Authorization"] = f"Bearer {self.token}"

        data_bytes = None
        if payload is not None:
            data_bytes = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_body = resp.read().decode("utf-8")
                if not resp_body:
                    return {"status_code": resp.status}
                try:
                    parsed = json.loads(resp_body)
                    if isinstance(parsed, dict):
                        parsed["status_code"] = resp.status
                    elif isinstance(parsed, list):
                        return {"status_code": resp.status, "items": parsed}
                    return parsed
                except json.JSONDecodeError:
                    return {"status_code": resp.status, "raw": resp_body}
        except urllib.error.HTTPError as http_err:
            body = http_err.read().decode("utf-8")
            logger.warning(f"[MacNodeAgent] HTTP error {http_err.code} on {method} {path}: {body}")
            try:
                err_dict = json.loads(body)
                err_dict["status_code"] = http_err.code
                return err_dict
            except Exception:
                return {"status_code": http_err.code, "error": str(http_err), "detail": body}
        except Exception as exc:
            logger.warning(f"[MacNodeAgent] Network failure on {method} {path}: {exc}")
            raise

    # =========================================================================
    # GENUINE CAPABILITY DETECTION
    # =========================================================================

    def detect_genuine_capabilities(self) -> Dict[str, Any]:
        """
        Inspect the local host to report genuine, truthful capabilities.
        Zero fake success — only enables what is genuinely available.
        """
        is_darwin = platform.system() == "Darwin"
        has_screencapture = is_darwin and os.path.exists("/usr/sbin/screencapture")

        # Check local Ollama availability
        has_ollama = False
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    has_ollama = True
        except Exception:
            has_ollama = False

        return {
            "computer_control": is_darwin,
            "screen_capture": has_screencapture,
            "apple_music": is_darwin,
            "local_ai": has_ollama,
            "ollama": has_ollama,
            "local_voice": is_darwin,
            "apple_silicon": platform.machine() == "arm64",
        }

    def detect_runtime_info(self) -> Dict[str, Any]:
        """Report genuine hardware and OS details."""
        return {
            "os": "macOS" if platform.system() == "Darwin" else platform.system(),
            "arch": platform.machine(),
            "release": platform.release(),
            "mac_ver": platform.mac_ver()[0] if platform.system() == "Darwin" else "N/A",
            "python": platform.python_version(),
            "hostname": platform.node(),
        }

    # =========================================================================
    # HEARTBEAT & REGISTRATION
    # =========================================================================

    def send_heartbeat(self, status: str = "ONLINE") -> Dict[str, Any]:
        """
        Transmit periodic heartbeat to NARAD Cloud.
        Registers genuine capabilities, architecture, and current status.
        Only treats the heartbeat as successful when the cloud returns 2xx
        and confirms the expected node identity and accepted status.
        Never reports ONLINE upon 404, 401, 403, 500, or unconfirmed identity.
        """
        payload = {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "status": status,
            "capabilities": self.detect_genuine_capabilities(),
            "runtime": self.detect_runtime_info(),
            "model_availability": ["qwen3.5:0.8b"] if self.detect_genuine_capabilities()["ollama"] else [],
        }

        resp = self._send_request("POST", "/api/v1/nodes/heartbeat", payload=payload)
        status_code = resp.get("status_code", 200)

        # Heartbeat is successful only when:
        # 1. HTTP status code is 2xx
        # 2. Response explicitly indicates success == True
        # 3. Cloud confirms expected node_id
        # 4. Cloud confirms accepted status
        http_ok = isinstance(status_code, int) and (200 <= status_code < 300)
        cloud_success = bool(resp.get("success", False))
        confirmed_node_id = resp.get("node_id")
        confirmed_status = resp.get("status")

        is_confirmed = (
            http_ok
            and cloud_success
            and (confirmed_node_id == self.node_id)
            and (confirmed_status == status)
        )

        if is_confirmed:
            self._last_heartbeat_time = time.time()
            self.is_online = (confirmed_status == "ONLINE")
            self.last_confirmed_status = confirmed_status
            logger.info(
                f"[MacNodeAgent] Heartbeat acknowledged by cloud: status={confirmed_status} (node_id={self.node_id})"
            )
            return resp

        # Heartbeat failed / rejected
        self.is_online = False
        error_detail = (
            resp.get("error", {}).get("message")
            if isinstance(resp.get("error"), dict)
            else resp.get("error") or resp.get("detail") or f"HTTP {status_code}"
        )
        logger.warning(
            f"[MacNodeAgent] Heartbeat NOT accepted by cloud: HTTP {status_code} "
            f"(node_id={self.node_id}, requested_status={status}, reason={error_detail})"
        )
        raise ConnectionError(
            f"Heartbeat rejected by cloud (HTTP {status_code}): {error_detail}"
        )

    # =========================================================================
    # ACTION POLLING & SAFE EXECUTION
    # =========================================================================

    def poll_and_execute_actions(self):
        """
        Poll pending commands from cloud queue and execute approved actions.
        Submits execution results back to cloud.
        Only polls when node is confirmed ONLINE.
        """
        if not self.is_online:
            logger.debug("[MacNodeAgent] Skipping action poll: node is not online.")
            return

        path = f"/api/v1/nodes/{urllib.parse.quote(self.node_id)}/actions/pending"
        resp = self._send_request("GET", path)

        if isinstance(resp, dict):
            status_code = resp.get("status_code", 200)
            if isinstance(status_code, int) and status_code >= 400:
                err_msg = (
                    resp.get("error", {}).get("message")
                    if isinstance(resp.get("error"), dict)
                    else resp.get("error") or resp.get("detail") or f"HTTP {status_code}"
                )
                logger.warning(
                    f"[MacNodeAgent] Polling pending actions rejected by cloud: HTTP {status_code} ({err_msg})"
                )
                raise ConnectionError(f"Action polling failed (HTTP {status_code}): {err_msg}")

        actions: List[Dict[str, Any]] = []
        if isinstance(resp, list):
            actions = resp
        elif isinstance(resp, dict) and "items" in resp:
            actions = resp["items"]

        if not actions:
            return

        for action in actions:
            act_id = action.get("action_id")
            act_type = action.get("action_type", "")
            payload = action.get("payload", {})
            confirmed = action.get("confirmed", False)

            logger.info(f"[MacNodeAgent] Processing action '{act_id}' ({act_type})")

            # Execute via safe sandboxed executor
            try:
                exec_result = self.executor.execute(
                    action_type=act_type,
                    payload=payload,
                    confirmed=confirmed,
                )
                success = bool(exec_result.get("success", False))
                error_msg = exec_result.get("error") if not success else None
            except Exception as e:
                logger.error(f"[MacNodeAgent] Execution failed on action {act_id}: {e}", exc_info=True)
                exec_result = {"success": False, "error": str(e)}
                success = False
                error_msg = str(e)

            # Submit result back to cloud
            res_path = f"/api/v1/nodes/{urllib.parse.quote(self.node_id)}/actions/{urllib.parse.quote(act_id)}/result"
            result_payload = {
                "success": success,
                "result": exec_result,
                "error": error_msg,
            }
            try:
                res_resp = self._send_request("POST", res_path, payload=result_payload)
                res_code = res_resp.get("status_code", 200) if isinstance(res_resp, dict) else 200
                if isinstance(res_code, int) and res_code >= 400:
                    logger.warning(
                        f"[MacNodeAgent] Failed to submit result for action '{act_id}': HTTP {res_code}"
                    )
                else:
                    logger.info(f"[MacNodeAgent] Submitted result for action '{act_id}' (success={success})")
            except Exception as post_err:
                logger.error(f"[MacNodeAgent] Failed to post result for action '{act_id}': {post_err}")

    # =========================================================================
    # MAIN RESILIENT RUN LOOP & GRACEFUL SHUTDOWN
    # =========================================================================

    def run(self):
        """
        Main execution loop.
        Sends heartbeats periodically, polls for actions, and handles reconnection
        with exponential backoff upon network interruption.
        """
        self.running = True
        logger.info(
            f"[MacNodeAgent] Starting NARAD Mac Node Agent\n"
            f"  Server: {self.server_url}\n"
            f"  Node ID: {self.node_id}\n"
            f"  Architecture: {platform.machine()} ({platform.system()})\n"
            f"  Heartbeat: {self.heartbeat_interval}s, Poll: {self.poll_interval}s"
        )

        # Setup OS signal handlers for graceful exit
        self._setup_signals()

        # Initial registration heartbeat
        try:
            self.send_heartbeat(status="ONLINE")
            self._consecutive_failures = 0
        except Exception as e:
            self._consecutive_failures += 1
            logger.warning(f"[MacNodeAgent] Initial heartbeat failed, will retry in loop: {e}")

        while self.running:
            now = time.time()
            try:
                # 1. Periodic heartbeat (or immediate retry if not currently online)
                if not self.is_online or (now - self._last_heartbeat_time >= self.heartbeat_interval):
                    self.send_heartbeat(status="ONLINE")

                # 2. Poll for pending actions only if confirmed online
                if self.is_online:
                    self.poll_and_execute_actions()

                # Reset failure counter upon successful iteration
                self._consecutive_failures = 0
                time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                logger.info("[MacNodeAgent] KeyboardInterrupt received. Shutting down...")
                break
            except Exception as loop_err:
                self._consecutive_failures += 1
                backoff = min(self._max_backoff_seconds, 2 ** min(self._consecutive_failures, 5))
                logger.warning(
                    f"[MacNodeAgent] Network/loop error: {loop_err}. "
                    f"Retrying in {backoff:.1f}s (failure count: {self._consecutive_failures})..."
                )
                time.sleep(backoff)

        self.shutdown()

    def shutdown(self):
        """
        Clean, graceful shutdown:
        Sends OFFLINE status to cloud backend immediately so Runtime Truth
        reflects node disconnection with zero lag.
        """
        self.running = False
        self.is_online = False
        logger.info(f"[MacNodeAgent] Sending OFFLINE notification for node '{self.node_id}'...")
        try:
            self.send_heartbeat(status="OFFLINE")
            logger.info("[MacNodeAgent] Successfully notified cloud of clean disconnect.")
        except Exception as exc:
            logger.warning(f"[MacNodeAgent] Could not deliver offline heartbeat: {exc}")

    def _setup_signals(self):
        """Register SIGINT and SIGTERM handlers for clean stop."""
        def _handle_exit(signum, frame):
            logger.info(f"[MacNodeAgent] Signal {signum} received. Stopping gracefully...")
            self.running = False

        try:
            signal.signal(signal.SIGINT, _handle_exit)
            signal.signal(signal.SIGTERM, _handle_exit)
        except Exception:
            pass
