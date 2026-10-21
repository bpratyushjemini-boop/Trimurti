"""
NARAD Phase 2.5 / Phase 3.5 — Local Node Registry & Command Relay Service.
Manages registered execution nodes (Mac laptops), authenticated heartbeats,
secure token rotation & revocation, and safe command relay execution queues.
"""

import asyncio
import hashlib
import json
import logging
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple, Set

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import LocalNodeRecord, NodeActionRecord

logger = logging.getLogger("narad.node_registry")

# Strict Allowlist of permitted local operations
ALLOWED_NODE_ACTIONS: Set[str] = {
    "node_status",
    "diagnostics",
    "get_system_state",
    "open_application",
    "take_screenshot",
}


def hash_token(token: str) -> str:
    """Generate SHA-256 hash of authentication token."""
    if not token:
        return ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LocalNodeRegistry:
    """
    Coordinates registered execution nodes (e.g. user's Mac laptop).
    Maintains heartbeat timestamps, capabilities, and availability.
    Implements secure token exchange, revocation, and safe command relay.
    """

    def __init__(self):
        self._cached_nodes: Dict[str, Dict[str, Any]] = {}
        self._token_hashes: Dict[str, str] = {}  # token_hash -> node_id
        self._actions: Dict[str, Dict[str, Any]] = {}  # action_id -> dict
        self._action_events: Dict[str, threading.Event] = {}  # action_id -> threading.Event

    @property
    def heartbeat_timeout(self) -> float:
        return float(getattr(settings, "NARAD_NODE_TIMEOUT_SECONDS", 120.0))

    def register_or_heartbeat(
        self,
        node_id: str,
        node_name: str = "Local Mac Laptop",
        status: str = "ONLINE",
        capabilities: Optional[Dict[str, Any]] = None,
        runtime: Optional[Dict[str, Any]] = None,
        model_availability: Optional[List[str]] = None,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Record heartbeat / registration from a local node.
        Persists to database so it survives cloud restarts.
        Rejects requests if node is revoked.
        """
        # Check if node is revoked
        cached = self.get_node(node_id)
        if cached and cached.get("revoked"):
            logger.warning(f"[NodeRegistry] Rejecting heartbeat from revoked node '{node_id}'")
            return {
                "node_id": node_id,
                "node_name": node_name,
                "status": "REVOKED",
                "revoked": True,
                "error": "NODE_REVOKED",
            }

        now = datetime.now(timezone.utc)
        caps = capabilities if capabilities is not None else {
            "computer_control": True,
            "screen_capture": True,
            "apple_music": True,
            "local_ai": True,
            "ollama": True,
            "local_voice": True,
        }
        runt = runtime if runtime is not None else {"os": "macOS", "arch": "arm64"}
        models = model_availability if model_availability is not None else ["qwen3.5:0.8b"]

        t_hash = hash_token(token) if token else (cached.get("token_hash") if cached else None)
        if t_hash:
            self._token_hashes[t_hash] = node_id

        node_payload = {
            "node_id": node_id,
            "node_name": node_name,
            "status": status,
            "capabilities": caps,
            "runtime": runt,
            "model_availability": models,
            "token_hash": t_hash,
            "revoked": False,
            "revoked_at": None,
            "last_seen": now.isoformat(),
            "last_seen_epoch": now.timestamp(),
        }

        # Update in-memory cache
        self._cached_nodes[node_id] = node_payload

        # Persist to database
        try:
            with SessionLocal() as db:
                rec = db.query(LocalNodeRecord).filter(LocalNodeRecord.node_id == node_id).first()
                if rec:
                    if rec.revoked:
                        logger.warning(f"[NodeRegistry] DB reports node '{node_id}' is revoked.")
                        self._cached_nodes[node_id]["revoked"] = True
                        self._cached_nodes[node_id]["status"] = "REVOKED"
                        return self._cached_nodes[node_id]
                    rec.node_name = node_name
                    rec.status = status
                    rec.capabilities_json = json.dumps(caps)
                    rec.runtime_json = json.dumps(runt)
                    rec.models_json = json.dumps(models)
                    if t_hash:
                        rec.token_hash = t_hash
                    rec.last_seen = now
                else:
                    rec = LocalNodeRecord(
                        node_id=node_id,
                        node_name=node_name,
                        status=status,
                        capabilities_json=json.dumps(caps),
                        runtime_json=json.dumps(runt),
                        models_json=json.dumps(models),
                        token_hash=t_hash,
                        revoked=False,
                        last_seen=now,
                        created_at=now,
                    )
                    db.add(rec)
                db.commit()
        except Exception as e:
            logger.debug(f"[NodeRegistry] DB persist notice: {e}")

        logger.info(f"[NodeRegistry] Heartbeat acknowledged for node '{node_id}' ({node_name}) [status={status}]")
        return node_payload

    def get_active_node(self) -> Optional[Dict[str, Any]]:
        """
        Returns the primary active local node if seen within heartbeat_timeout.
        Ignores revoked nodes and nodes marked OFFLINE.
        """
        now_ts = datetime.now(timezone.utc).timestamp()
        timeout = self.heartbeat_timeout

        # Check memory first
        for nid, node in self._cached_nodes.items():
            if node.get("revoked"):
                continue
            epoch = node.get("last_seen_epoch", 0)
            if now_ts - epoch < timeout and node.get("status") == "ONLINE":
                return node

        # Fallback to database check
        try:
            with SessionLocal() as db:
                recs = db.query(LocalNodeRecord).filter(
                    LocalNodeRecord.status == "ONLINE",
                    LocalNodeRecord.revoked == False
                ).all()
                for r in recs:
                    d = r.to_dict()
                    dt = r.last_seen
                    if dt:
                        dt_epoch = dt.replace(tzinfo=timezone.utc).timestamp() if dt.tzinfo is None else dt.timestamp()
                        if now_ts - dt_epoch < timeout:
                            d["last_seen_epoch"] = dt_epoch
                            if r.token_hash:
                                self._token_hashes[r.token_hash] = r.node_id
                            self._cached_nodes[r.node_id] = d
                            return d
        except Exception as e:
            logger.debug(f"[NodeRegistry] DB query notice: {e}")

        return None

    def is_local_node_connected(self) -> bool:
        """True if any local node has sent a heartbeat recently."""
        return self.get_active_node() is not None

    def is_node_online(self, node_id: str) -> bool:
        """Check if specific node is online and not timed out."""
        node = self.get_node(node_id)
        if not node or node.get("revoked"):
            return False
        if node.get("status") != "ONLINE":
            return False
        now_ts = datetime.now(timezone.utc).timestamp()
        epoch = node.get("last_seen_epoch", 0)
        return (now_ts - epoch) < self.heartbeat_timeout

    def list_nodes(self) -> List[Dict[str, Any]]:
        """List all known nodes from database or cache."""
        nodes = []
        try:
            with SessionLocal() as db:
                recs = db.query(LocalNodeRecord).order_by(LocalNodeRecord.last_seen.desc()).all()
                nodes = [r.to_dict() for r in recs]
        except Exception as e:
            logger.debug(f"[NodeRegistry] List nodes notice: {e}")

        if not nodes:
            nodes = list(self._cached_nodes.values())
        return nodes

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve single node by ID."""
        if node_id in self._cached_nodes:
            return self._cached_nodes[node_id]

        try:
            with SessionLocal() as db:
                rec = db.query(LocalNodeRecord).filter(LocalNodeRecord.node_id == node_id).first()
                if rec:
                    d = rec.to_dict()
                    d["token_hash"] = rec.token_hash
                    dt = rec.last_seen
                    if dt:
                        d["last_seen_epoch"] = dt.replace(tzinfo=timezone.utc).timestamp() if dt.tzinfo is None else dt.timestamp()
                    if rec.token_hash:
                        self._token_hashes[rec.token_hash] = rec.node_id
                    self._cached_nodes[node_id] = d
                    return d
        except Exception as e:
            logger.debug(f"[NodeRegistry] Get node notice: {e}")
        return None

    def verify_token(self, token: str) -> bool:
        """
        Verify if a token is valid across global settings, cached hashes, or DB.
        Rejects revoked node tokens.
        """
        if not token or not token.strip():
            return False

        clean_token = token.strip()
        # 1. Global node token check
        global_node_token = getattr(settings, "NARAD_NODE_TOKEN", "")
        if global_node_token and clean_token == global_node_token:
            return True

        # 2. Hash lookup in memory
        t_hash = hash_token(clean_token)
        node_id = self._token_hashes.get(t_hash)
        if node_id:
            node = self.get_node(node_id)
            if node and not node.get("revoked"):
                return True
            return False

        # 3. Hash lookup in DB
        try:
            with SessionLocal() as db:
                rec = db.query(LocalNodeRecord).filter(
                    LocalNodeRecord.token_hash == t_hash,
                    LocalNodeRecord.revoked == False
                ).first()
                if rec:
                    self._token_hashes[t_hash] = rec.node_id
                    return True
        except Exception as e:
            logger.debug(f"[NodeRegistry] Token DB lookup notice: {e}")

        return False

    def verify_node_authorization(self, node_id: str, token: str) -> bool:
        """
        Verify if caller with token is authorized to act as/for node_id.
        Admins with NARAD_API_KEY are authorized for all nodes.
        In local development (no server API key, no node token, and no node token hash set),
        access is permitted.
        """
        api_key = getattr(settings, "NARAD_API_KEY", "")
        global_node_token = getattr(settings, "NARAD_NODE_TOKEN", "")

        node = self.get_node(node_id)
        if not node or node.get("revoked"):
            return False

        node_token_hash = node.get("token_hash")
        # If no auth is configured on server and no token was registered for this node, allow
        if not api_key and not global_node_token and not node_token_hash:
            return True

        if not token:
            return False

        clean_token = token.strip()
        if api_key and clean_token == api_key:
            return True

        if global_node_token and clean_token == global_node_token:
            return True

        t_hash = hash_token(clean_token)
        if node_token_hash and node_token_hash == t_hash:
            return True

        return False


    def revoke_node(self, node_id: str) -> bool:
        """
        Revoke node credentials and mark as revoked.
        Immediately stops accepting heartbeats or commands.
        """
        now = datetime.now(timezone.utc)
        node = self.get_node(node_id)
        if not node:
            return False

        node["revoked"] = True
        node["revoked_at"] = now.isoformat()
        node["status"] = "REVOKED"
        self._cached_nodes[node_id] = node

        # Remove from hash map
        t_hash = node.get("token_hash")
        if t_hash and t_hash in self._token_hashes:
            del self._token_hashes[t_hash]

        try:
            with SessionLocal() as db:
                rec = db.query(LocalNodeRecord).filter(LocalNodeRecord.node_id == node_id).first()
                if rec:
                    rec.revoked = True
                    rec.revoked_at = now
                    rec.status = "REVOKED"
                    db.commit()
        except Exception as e:
            logger.error(f"[NodeRegistry] Failed to persist revocation for {node_id}: {e}")

        logger.warning(f"[NodeRegistry] Node '{node_id}' has been REVOKED.")
        return True

    def rotate_node_token(self, node_id: str) -> str:
        """
        Generate and persist a new random token for node_id.
        Restores node from revoked status.
        Returns the plaintext token to be securely transmitted to caller.
        """
        raw_token = f"node_{secrets.token_urlsafe(32)}"
        t_hash = hash_token(raw_token)
        now = datetime.now(timezone.utc)

        node = self.get_node(node_id) or {
            "node_id": node_id,
            "node_name": "Local Mac Laptop",
            "capabilities": {},
            "runtime": {},
            "model_availability": [],
            "created_at": now.isoformat(),
        }

        # Clear old token hash
        old_hash = node.get("token_hash")
        if old_hash and old_hash in self._token_hashes:
            del self._token_hashes[old_hash]

        node["token_hash"] = t_hash
        node["revoked"] = False
        node["revoked_at"] = None
        node["status"] = "ONLINE"
        node["last_seen"] = now.isoformat()
        node["last_seen_epoch"] = now.timestamp()
        self._cached_nodes[node_id] = node
        self._token_hashes[t_hash] = node_id

        try:
            with SessionLocal() as db:
                rec = db.query(LocalNodeRecord).filter(LocalNodeRecord.node_id == node_id).first()
                if rec:
                    rec.token_hash = t_hash
                    rec.revoked = False
                    rec.revoked_at = None
                    rec.status = "ONLINE"
                    rec.last_seen = now
                else:
                    rec = LocalNodeRecord(
                        node_id=node_id,
                        node_name=node.get("node_name", "Local Node"),
                        status="ONLINE",
                        token_hash=t_hash,
                        revoked=False,
                        last_seen=now,
                        created_at=now,
                    )
                    db.add(rec)
                db.commit()
        except Exception as e:
            logger.error(f"[NodeRegistry] Failed to persist token rotation for {node_id}: {e}")

        logger.info(f"[NodeRegistry] Token rotated successfully for node '{node_id}'")
        return raw_token

    # =========================================================================
    # SAFE COMMAND RELAY (Task Queue & Dispatch)
    # =========================================================================

    def enqueue_action(
        self,
        node_id: str,
        action_type: str,
        payload: Optional[Dict[str, Any]] = None,
        confirmed: bool = False,
        request_id: Optional[str] = None,
        timeout_seconds: int = 30,
    ) -> Dict[str, Any]:
        """
        Enqueue an approved local action for dispatch to a connected Mac node.
        Validates against ALLOWED_NODE_ACTIONS and enforces action policy.
        """
        clean_type = action_type.strip().lower()
        if clean_type not in ALLOWED_NODE_ACTIONS:
            raise ValueError(
                f"Action '{action_type}' is prohibited on secure node bridge. "
                f"Allowed operations: {sorted(ALLOWED_NODE_ACTIONS)}"
            )

        node = self.get_node(node_id)
        if not node:
            raise ValueError(f"Node '{node_id}' not found.")
        if node.get("revoked"):
            raise ValueError(f"Node '{node_id}' is revoked.")
        if not self.is_node_online(node_id):
            raise ValueError(f"Node '{node_id}' is currently offline.")

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=max(5, timeout_seconds))
        action_id = f"act_{uuid.uuid4().hex[:12]}"
        req_id = request_id or f"req_{uuid.uuid4().hex[:12]}"
        args = payload or {}

        # Classify permission requirement
        if clean_type == "take_screenshot":
            perm_level = 2
            req_confirm = True
            if not confirmed:
                raise ValueError("Operation 'take_screenshot' requires explicit user confirmation (confirmed=true).")
        elif clean_type == "open_application":
            perm_level = 1
            req_confirm = False
        else:
            perm_level = 0
            req_confirm = False

        action_data = {
            "action_id": action_id,
            "node_id": node_id,
            "action_type": clean_type,
            "payload": args,
            "status": "PENDING",
            "permission_level": perm_level,
            "requires_confirmation": req_confirm,
            "confirmed": confirmed,
            "result": None,
            "error": None,
            "request_id": req_id,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "completed_at": None,
        }

        self._actions[action_id] = action_data
        self._action_events[action_id] = threading.Event()

        # Persist to database
        try:
            with SessionLocal() as db:
                rec = NodeActionRecord(
                    action_id=action_id,
                    node_id=node_id,
                    action_type=clean_type,
                    payload_json=json.dumps(args),
                    status="PENDING",
                    permission_level=perm_level,
                    requires_confirmation=req_confirm,
                    confirmed=confirmed,
                    request_id=req_id,
                    created_at=now,
                    expires_at=expires_at,
                )
                db.add(rec)
                db.commit()
        except Exception as e:
            logger.debug(f"[NodeRegistry] Action DB persist notice: {e}")

        logger.info(f"[NodeRegistry] Enqueued action '{action_id}' ({clean_type}) for node '{node_id}'")
        return action_data

    def get_pending_actions(self, node_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve and dispatch unexpired pending actions for node_id.
        Marks returned actions as DISPATCHED.
        """
        node = self.get_node(node_id)
        if not node or node.get("revoked"):
            return []

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        pending = []

        for act_id, act in list(self._actions.items()):
            if act["node_id"] == node_id and act["status"] == "PENDING":
                # Check expiration
                if act.get("expires_at") and act["expires_at"] < now_iso:
                    act["status"] = "TIMEOUT"
                    act["error"] = "Action expired before dispatch."
                    continue
                act["status"] = "DISPATCHED"
                pending.append(act)

        # Check DB for any pending actions not in memory
        try:
            with SessionLocal() as db:
                recs = db.query(NodeActionRecord).filter(
                    NodeActionRecord.node_id == node_id,
                    NodeActionRecord.status == "PENDING",
                    NodeActionRecord.expires_at > now
                ).all()
                for r in recs:
                    if r.action_id not in self._actions:
                        d = r.to_dict()
                        d["status"] = "DISPATCHED"
                        self._actions[r.action_id] = d
                        self._action_events[r.action_id] = threading.Event()
                        pending.append(d)
                    r.status = "DISPATCHED"
                db.commit()
        except Exception as e:
            logger.debug(f"[NodeRegistry] DB pending action query notice: {e}")

        return pending

    def submit_action_result(
        self,
        node_id: str,
        action_id: str,
        success: bool,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Record the execution result returned by the Mac node agent.
        Enforces idempotency: terminal states (COMPLETED, FAILED, TIMEOUT, CANCELLED)
        are not overwritten.
        """
        act = self.get_action(action_id)
        if not act:
            raise ValueError(f"Action '{action_id}' not found.")
        if act["node_id"] != node_id:
            raise ValueError(f"Action '{action_id}' does not belong to node '{node_id}'.")

        # Idempotency check: Already terminal
        if act["status"] in ("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"):
            logger.info(f"[NodeRegistry] Action '{action_id}' is already terminal ({act['status']}). Idempotent return.")
            return act

        now = datetime.now(timezone.utc)
        status = "COMPLETED" if success else "FAILED"
        act["status"] = status
        act["result"] = result
        act["error"] = error
        act["completed_at"] = now.isoformat()
        self._actions[action_id] = act

        # Persist to DB
        try:
            with SessionLocal() as db:
                rec = db.query(NodeActionRecord).filter(NodeActionRecord.action_id == action_id).first()
                if rec:
                    rec.status = status
                    rec.result_json = json.dumps(result) if result is not None else None
                    rec.error = error
                    rec.completed_at = now
                    db.commit()
        except Exception as e:
            logger.debug(f"[NodeRegistry] Action result DB update notice: {e}")

        # Signal any waiting thread/async caller
        evt = self._action_events.get(action_id)
        if evt:
            evt.set()

        logger.info(f"[NodeRegistry] Action '{action_id}' finalized with status={status}")
        return act

    def cancel_action(self, node_id: str, action_id: str, reason: str = "Cancelled by user") -> Dict[str, Any]:
        """Cancel a pending or dispatched action."""
        act = self.get_action(action_id)
        if not act:
            raise ValueError(f"Action '{action_id}' not found.")
        if act["node_id"] != node_id:
            raise ValueError(f"Action '{action_id}' does not belong to node '{node_id}'.")

        if act["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            return act

        now = datetime.now(timezone.utc)
        act["status"] = "CANCELLED"
        act["error"] = reason
        act["completed_at"] = now.isoformat()
        self._actions[action_id] = act

        try:
            with SessionLocal() as db:
                rec = db.query(NodeActionRecord).filter(NodeActionRecord.action_id == action_id).first()
                if rec:
                    rec.status = "CANCELLED"
                    rec.error = reason
                    rec.completed_at = now
                    db.commit()
        except Exception as e:
            logger.debug(f"[NodeRegistry] Action cancel DB notice: {e}")

        evt = self._action_events.get(action_id)
        if evt:
            evt.set()

        return act

    def get_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve action by ID from memory or database."""
        if action_id in self._actions:
            return self._actions[action_id]

        try:
            with SessionLocal() as db:
                rec = db.query(NodeActionRecord).filter(NodeActionRecord.action_id == action_id).first()
                if rec:
                    d = rec.to_dict()
                    self._actions[action_id] = d
                    return d
        except Exception as e:
            logger.debug(f"[NodeRegistry] Get action notice: {e}")
        return None

    def dispatch_and_wait_sync(
        self,
        node_id: str,
        action_type: str,
        payload: Optional[Dict[str, Any]] = None,
        confirmed: bool = False,
        timeout_seconds: int = 30,
    ) -> Dict[str, Any]:
        """
        Synchronously dispatch an action to a node and wait up to timeout_seconds.
        Used by MacComputerAdapter when running in cloud mode.
        """
        try:
            action = self.enqueue_action(
                node_id=node_id,
                action_type=action_type,
                payload=payload,
                confirmed=confirmed,
                timeout_seconds=timeout_seconds,
            )
        except Exception as e:
            return {"success": False, "error": str(e)}

        act_id = action["action_id"]
        evt = self._action_events.get(act_id)
        if not evt:
            return {"success": False, "error": "Internal event tracking failure"}

        signaled = evt.wait(timeout=float(timeout_seconds))
        if not signaled:
            # Mark timeout
            self.submit_action_result(
                node_id=node_id,
                action_id=act_id,
                success=False,
                error=f"Operation '{action_type}' timed out waiting for Mac node response after {timeout_seconds}s.",
            )
            act_final = self.get_action(act_id) or action
            act_final["status"] = "TIMEOUT"
            return {
                "success": False,
                "error": f"Mac unavailable: Timed out waiting for Mac node response after {timeout_seconds}s.",
                "message": f"Action {act_id} timed out after {timeout_seconds}s.",
            }

        act_final = self.get_action(act_id) or action
        if act_final.get("status") == "COMPLETED":
            res = act_final.get("result") or {"success": True}
            if isinstance(res, dict) and "success" not in res:
                res["success"] = True
            return res

        return {
            "success": False,
            "error": f"Mac unavailable: {act_final.get('error', 'Execution failed on remote Mac node.')}",
            "status": act_final.get("status"),
        }


    async def dispatch_and_wait(
        self,
        node_id: str,
        action_type: str,
        payload: Optional[Dict[str, Any]] = None,
        confirmed: bool = False,
        timeout_seconds: int = 30,
    ) -> Dict[str, Any]:
        """Asynchronous wrapper around dispatch_and_wait_sync."""
        return await asyncio.to_thread(
            self.dispatch_and_wait_sync,
            node_id=node_id,
            action_type=action_type,
            payload=payload,
            confirmed=confirmed,
            timeout_seconds=timeout_seconds,
        )


# Global singleton instance
node_registry = LocalNodeRegistry()
