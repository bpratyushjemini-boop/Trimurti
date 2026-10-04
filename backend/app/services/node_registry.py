"""
NARAD Phase 2.5 / Phase 3 — Local Node Registry Service.
Architectural boundary for future self-hosted laptop migration.
Enables a remote or local Mac laptop to check in, declare capabilities,
and report hardware/model availability to the Cloud NARAD instance.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.database import SessionLocal
from app.db.models import LocalNodeRecord

logger = logging.getLogger("narad.node_registry")

HEARTBEAT_TIMEOUT_SECONDS = 120.0


class LocalNodeRegistry:
    """
    Coordinates registered execution nodes (e.g. user's Mac laptop).
    Maintains heartbeat timestamps, capabilities, and availability.
    """

    def __init__(self):
        self._cached_nodes: Dict[str, Dict[str, Any]] = {}

    def register_or_heartbeat(
        self,
        node_id: str,
        node_name: str = "Local Mac Laptop",
        status: str = "ONLINE",
        capabilities: Optional[Dict[str, Any]] = None,
        runtime: Optional[Dict[str, Any]] = None,
        model_availability: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Record heartbeat / registration from a local node.
        Persists to database so it survives cloud restarts.
        """
        now = datetime.now(timezone.utc)
        caps = capabilities or {
            "computer_control": True,
            "screen_capture": True,
            "apple_music": True,
            "local_ai": True,
            "ollama": True,
            "local_voice": True,
        }
        runt = runtime or {"os": "macOS", "arch": "arm64"}
        models = model_availability or ["qwen3.5:0.8b"]

        node_payload = {
            "node_id": node_id,
            "node_name": node_name,
            "status": status,
            "capabilities": caps,
            "runtime": runt,
            "model_availability": models,
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
                    rec.node_name = node_name
                    rec.status = status
                    rec.capabilities_json = json.dumps(caps)
                    rec.runtime_json = json.dumps(runt)
                    rec.models_json = json.dumps(models)
                    rec.last_seen = now
                else:
                    rec = LocalNodeRecord(
                        node_id=node_id,
                        node_name=node_name,
                        status=status,
                        capabilities_json=json.dumps(caps),
                        runtime_json=json.dumps(runt),
                        models_json=json.dumps(models),
                        last_seen=now,
                        created_at=now,
                    )
                    db.add(rec)
                db.commit()
        except Exception as e:
            logger.debug(f"[NodeRegistry] DB persist notice: {e}")

        logger.info(f"[NodeRegistry] Heartbeat acknowledged for node '{node_id}' ({node_name})")
        return node_payload

    def get_active_node(self) -> Optional[Dict[str, Any]]:
        """
        Returns the primary active local node if seen within HEARTBEAT_TIMEOUT_SECONDS.
        """
        now_ts = datetime.now(timezone.utc).timestamp()

        # Check memory first
        for nid, node in self._cached_nodes.items():
            epoch = node.get("last_seen_epoch", 0)
            if now_ts - epoch < HEARTBEAT_TIMEOUT_SECONDS and node.get("status") == "ONLINE":
                return node

        # Fallback to database check
        try:
            with SessionLocal() as db:
                recs = db.query(LocalNodeRecord).filter(LocalNodeRecord.status == "ONLINE").all()
                for r in recs:
                    d = r.to_dict()
                    dt = r.last_seen
                    if dt:
                        dt_epoch = dt.replace(tzinfo=timezone.utc).timestamp() if dt.tzinfo is None else dt.timestamp()
                        if now_ts - dt_epoch < HEARTBEAT_TIMEOUT_SECONDS:
                            d["last_seen_epoch"] = dt_epoch
                            self._cached_nodes[r.node_id] = d
                            return d
        except Exception as e:
            logger.debug(f"[NodeRegistry] DB query notice: {e}")

        return None

    def is_local_node_connected(self) -> bool:
        """True if any local node has sent a heartbeat recently."""
        return self.get_active_node() is not None

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
                    self._cached_nodes[node_id] = d
                    return d
        except Exception as e:
            logger.debug(f"[NodeRegistry] Get node notice: {e}")
        return None


node_registry = LocalNodeRegistry()
