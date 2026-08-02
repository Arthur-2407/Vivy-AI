"""
Vivy AI — Network Security & Multi-Layer Defense Fusion Engine
==============================================================
Unites embedded Tor encryption with Vivy's 45-Second L2-L4 Address Bouncing:
  - When traffic routes via Private Mode or Onion circuits, simultaneously triggers Layer 2 MAC regeneration, Layer 3 IP/TTL hopping, and Layer 4 ephemeral port rotation.
  - Generates unified defense reports for developer diagnostic dashboards and AGI Blackboard reasoning.
"""

import threading
from typing import Dict, Any

from internet.network.address_bouncer import get_address_bouncer
from internet.network.tor_identity import get_tor_identity

class NetworkSecurity:
    """Thread-safe multi-layer security defense coordinator."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "NetworkSecurity":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._lock = threading.RLock()
        self.bouncer = get_address_bouncer()
        self.tor_identity = get_tor_identity()
        self.active_defense_level = "HIGH_ANONYMITY_DEFENSE"

    def enforce_session_defense(self, url_or_domain: str, is_tor_active: bool) -> Dict[str, Any]:
        """Executes combined L2-L4 Address Bouncing and Tor circuit inspection."""
        with self._lock:
            bounce_state = self.bouncer.trigger_bounce_cycle(reason=f"security_enforcement ({url_or_domain})")
            tor_state = self.tor_identity.get_identity_summary() if is_tor_active else {"active_circuit": "DIRECT_HTTPS_NO_TOR"}

            return {
                "target": url_or_domain,
                "defense_level": "TOR_ONION + 45S_L2_L4_BOUNCING" if is_tor_active else "45S_L2_L4_BOUNCING_ONLY",
                "l2_src_mac": bounce_state["l2_src_mac"],
                "l4_src_port": bounce_state["l4_src_port"],
                "tor_circuit": tor_state["active_circuit"],
                "apparent_ip": tor_state.get("apparent_origin_ip", bounce_state.get("l3_src_ip")),
                "tool_chain": bounce_state["tool_pipeline"]
            }

    def get_security_summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "defense_level": self.active_defense_level,
                "address_bouncer_interval": f"{self.bouncer.interval} seconds",
                "tool_hierarchy": "FRRouting -> GNS3 -> Scapy -> Raw Sockets -> iptables",
                "tor_encryption": "READY_AND_INTEGRATED"
            }

_global_sec = None
def get_network_security() -> NetworkSecurity:
    global _global_sec
    if _global_sec is None:
        _global_sec = NetworkSecurity.get_instance()
    return _global_sec
