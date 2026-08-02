"""
Vivy AI — Unified Tor Engine Startup & Lifecycle Manager
==========================================================
Coordinates the invisible background startup sequence on Vivy boot:
  Launch Vivy -> Load Memory -> Initialize Brain -> Initialize Tools ->
  Start Tor -> Verify Connection -> Ready!
"""

import threading
from typing import Dict, Any

from internet.network.tor_config import get_tor_config
from internet.network.tor_controller import get_tor_controller
from internet.network.tor_monitor import get_tor_monitor
from internet.network.tor_identity import get_tor_identity

class TorManager:
    """Unified Facade managing embedded Tor and Onion networking."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "TorManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._lock = threading.RLock()
        self.config = get_tor_config()
        self.controller = get_tor_controller()
        self.monitor = get_tor_monitor()
        self.identity = get_tor_identity()
        self.is_ready = False
        self._startup()

    def _startup(self):
        with self._lock:
            print("[TorManager] Starting automated Tor Engine initialization sequence...")
            # Start background health monitoring
            self.monitor.start_monitoring()
            # Verify connectivity
            healthy = self.monitor.check_circuit_health()
            if healthy:
                self.is_ready = True
                print("[TorManager] Tor Engine & Onion Circuit Ready! (Invisible Background Operation)")
            else:
                print("[TorManager] Notice: Tor initial probe offline, engaging background auto-retry.")

    def request_new_identity(self) -> Dict[str, Any]:
        """Expose circuit renewal method to planners and user commands."""
        with self._lock:
            return self.identity.request_new_identity(reason="manual_tor_manager_request")

    def shutdown(self):
        with self._lock:
            self.monitor.stop_monitoring()
            self.controller.stop_process()
            self.is_ready = False
            print("[TorManager] Tor Engine shut down cleanly.")

    def get_status_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "ready": self.is_ready,
                "config": self.config.get_config_summary(),
                "controller": self.controller.get_status(),
                "monitor": self.monitor.get_monitor_summary(),
                "circuit_identity": self.identity.get_identity_summary()
            }

_global_mgr = None
def get_tor_manager() -> TorManager:
    global _global_mgr
    if _global_mgr is None:
        _global_mgr = TorManager.get_instance()
    return _global_mgr
