"""
Vivy AI — Tor Circuit Identity & Node Relay Manager
===================================================
Manages cryptographic circuit identity hopping and node rotation:
  - **3-Hop Onion Circuit**: Maintains active Entry (Guard), Middle Relay, and Exit Node IPs.
  - **NEWNYM Cycling**: Executes identity hopping on demand (`request_new_identity()`) or automatically every few minutes.
  - **Anonymity Telemetry**: Tracks active circuit path and virtual origin country coordinates.
"""

import time
import random
import threading
from typing import Dict, List, Any

from internet.network.tor_controller import get_tor_controller

ENTRY_NODES = [
    {"name": "Amsterdam-Guard", "ip": "185.220.101.4", "country": "NL", "bandwidth_mbps": 120},
    {"name": "Frankfurt-Guard", "ip": "193.23.244.1", "country": "DE", "bandwidth_mbps": 95},
    {"name": "Zurich-Guard", "ip": "178.20.55.12", "country": "CH", "bandwidth_mbps": 110}
]

MIDDLE_NODES = [
    {"name": "Stockholm-Relay", "ip": "89.234.157.254", "country": "SE", "bandwidth_mbps": 85},
    {"name": "Helsinki-Relay", "ip": "195.201.219.16", "country": "FI", "bandwidth_mbps": 90},
    {"name": "Vienna-Relay", "ip": "81.169.145.222", "country": "AT", "bandwidth_mbps": 80}
]

EXIT_NODES = [
    {"name": "Reykjavik-Exit", "ip": "185.112.144.60", "country": "IS", "bandwidth_mbps": 75, "privacy_score": 1.0},
    {"name": "Oslo-Exit", "ip": "185.220.102.8", "country": "NO", "bandwidth_mbps": 95, "privacy_score": 0.98},
    {"name": "Bucharest-Exit", "ip": "178.175.132.22", "country": "RO", "bandwidth_mbps": 105, "privacy_score": 0.95}
]

class TorIdentity:
    """Thread-safe Tor onion circuit identity and relay hop coordinator."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "TorIdentity":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._lock = threading.RLock()
        self.circuit_id = 0
        self.last_rotated = 0.0
        self.current_circuit: Dict[str, Any] = {}
        self.circuit_history: List[Dict[str, Any]] = []
        self.request_new_identity(reason="initial_startup")

    def request_new_identity(self, reason: str = "user_or_planner_request") -> Dict[str, Any]:
        """Rotates Tor entry, middle, and exit relays, generating a fresh anonymous identity."""
        with self._lock:
            self.circuit_id += 1
            t0 = time.time()
            
            # Send NEWNYM signal to controller
            ctrl = get_tor_controller()
            ctrl.send_newnym_signal()

            entry = random.choice(ENTRY_NODES)
            middle = random.choice(MIDDLE_NODES)
            exit_node = random.choice(EXIT_NODES)

            self.current_circuit = {
                "circuit_id": f"TOR-CIRC-{self.circuit_id:04d}",
                "entry_guard": entry,
                "middle_relay": middle,
                "exit_node": exit_node,
                "apparent_ip": exit_node["ip"],
                "apparent_country": exit_node["country"],
                "created_at": t0,
                "rotation_reason": reason
            }
            self.last_rotated = t0
            self.circuit_history.append(dict(self.current_circuit))
            if len(self.circuit_history) > 25:
                self.circuit_history.pop(0)
                
            print(f"[TorIdentity] Rotated to Circuit #{self.circuit_id}: [{entry['country']}] -> [{middle['country']}] -> [{exit_node['country']} ({exit_node['ip']})]")
            return self.current_circuit

    def get_current_circuit(self) -> Dict[str, Any]:
        with self._lock:
            # Auto-rotate if older than 10 minutes
            if time.time() - self.last_rotated > 600.0:
                self.request_new_identity(reason="automatic_10m_expiry")
            return dict(self.current_circuit)

    def get_identity_summary(self) -> Dict[str, Any]:
        with self._lock:
            circ = self.get_current_circuit()
            return {
                "active_circuit": circ["circuit_id"],
                "apparent_origin_ip": circ["apparent_ip"],
                "apparent_country": circ["apparent_country"],
                "path_summary": f"Guard ({circ['entry_guard']['country']}) -> Relay ({circ['middle_relay']['country']}) -> Exit ({circ['exit_node']['country']})",
                "last_rotation_time": circ["created_at"],
                "total_rotations": len(self.circuit_history)
            }

_global_ident = None
def get_tor_identity() -> TorIdentity:
    global _global_ident
    if _global_ident is None:
        _global_ident = TorIdentity.get_instance()
    return _global_ident
