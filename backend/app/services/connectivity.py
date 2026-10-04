"""
Connectivity Subsystem for NARAD Phase 2:
Detects internet availability, manages operating mode transitions:
- NORMAL: Cloud + Local providers available
- DEGRADED: Internet up but some cloud providers are in cooldown or unavailable
- LOCAL: Internet unreachable, operating in local-only mode (Ollama + Local Tools + Smṛti)
"""

import time
import socket
import logging
from typing import Dict, Any

logger = logging.getLogger("narad.connectivity")


class ConnectivityService:
    def __init__(self, probe_host: str = "1.1.1.1", probe_port: int = 53, timeout: float = 0.6):
        self.probe_host = probe_host
        self.probe_port = probe_port
        self.timeout = timeout
        self._cached_online: bool = True
        self._last_probe_time: float = 0.0
        self._cache_duration: float = 5.0  # seconds

    def is_online(self, force_refresh: bool = False) -> bool:
        """
        Check if internet is reachable via fast non-blocking socket probe.
        Caches result for 5 seconds to avoid network thrashing.
        Respects OFFLINE_MODE setting and AgentBrain RuntimeMode.OFFLINE.
        """
        from app.core.config import settings
        if getattr(settings, "OFFLINE_MODE", False):
            return False

        try:
            from app.services.agent_brain import agent_brain, RuntimeMode
            if agent_brain.get_mode() == RuntimeMode.OFFLINE:
                return False
        except Exception:
            pass

        now = time.time()
        if not force_refresh and (now - self._last_probe_time) < self._cache_duration:
            return self._cached_online

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.probe_host, self.probe_port))
            sock.close()
            self._cached_online = True
        except Exception:
            # Fallback probe to Google DNS
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                sock.connect(("8.8.8.8", 53))
                sock.close()
                self._cached_online = True
            except Exception:
                self._cached_online = False

        self._last_probe_time = now
        return self._cached_online

    def get_operating_mode(self) -> str:
        """
        Calculates current operating mode:
        - NORMAL: Cloud internet reachable and primary cloud provider healthy
        - DEGRADED: Internet reachable but one or more cloud providers down/in cooldown
        - LOCAL: Internet unreachable; strictly local on-device operation
        """
        if not self.is_online():
            return "LOCAL"

        try:
            from app.providers.manager import provider_manager
            configured = provider_manager.get_configured_providers()
            if not configured:
                return "LOCAL"

            cloud_providers = [p for p in configured if p.provider_id not in ("ollama", "huggingface", "mock-narad")]
            if not cloud_providers:
                return "LOCAL"

            any_in_cooldown = any(p.is_in_cooldown() for p in cloud_providers)
            all_in_cooldown = all(p.is_in_cooldown() for p in cloud_providers)

            if all_in_cooldown:
                return "LOCAL"
            elif any_in_cooldown:
                return "DEGRADED"
            return "NORMAL"
        except Exception:
            return "NORMAL"

    def get_status(self) -> Dict[str, Any]:
        """Returns structured connectivity and operating mode telemetry."""
        online = self.is_online()
        mode = self.get_operating_mode()
        return {
            "online": online,
            "operating_mode": mode,
            "probe_host": self.probe_host,
            "last_checked": self._last_probe_time
        }


# Singleton connectivity service
connectivity_service = ConnectivityService()
