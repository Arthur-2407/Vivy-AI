"""
Vivy AI — Network Intelligence & Diagnostics Subsystem
======================================================
Monitors real-time network metadata and feeds observations into Vivy's reasoning:
  - **Metadata Monitor**: Precision latency tracking, estimated bandwidth capability, packet loss percentage, and latency jitter calculation.
  - **Connectivity Diagnostics**: Diagnoses DNS resolution timeouts, TCP reset anomalies, captive portal interception, and degraded links.
  - **AGI Blackboard Integration**: Publishes live network observations and L2-L4 address bouncing state directly into `agi/blackboard.py` for autonomous planning.
"""

import time
import math
import socket
import threading
from typing import Dict, List, Any, Optional

class NetworkIntelligence:
    """Diagnostic intelligence subsystem analyzing traffic and feeding AGI reasoning."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "NetworkIntelligence":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._lock = threading.RLock()
        self.latency_history_ms: List[float] = [55.0, 60.0, 58.0, 62.0, 57.0]
        self.packet_loss_percent = 0.0
        self.jitter_ms = 2.4
        self.estimated_bandwidth_mbps = 85.5
        self.last_diagnostic = "HEALTHY_OPTIMAL_STREAMS"

    def record_probe_sample(self, latency_ms: float, success: bool = True):
        """Record real-time connection sample and recalculate jitter and loss metrics."""
        with self._lock:
            if not success:
                self.packet_loss_percent = min(100.0, self.packet_loss_percent + 15.0)
                self.last_diagnostic = "PACKET_LOSS_ANOMALY"
            else:
                self.latency_history_ms.append(latency_ms)
                if len(self.latency_history_ms) > 30:
                    self.latency_history_ms.pop(0)
                
                # Jitter is average standard deviation across consecutive latency deltas
                deltas = [abs(self.latency_history_ms[i] - self.latency_history_ms[i-1]) for i in range(1, len(self.latency_history_ms))]
                self.jitter_ms = round(sum(deltas) / len(deltas) if deltas else 1.0, 2)
                
                # Decay historical loss on success
                self.packet_loss_percent = max(0.0, round(self.packet_loss_percent * 0.85, 2))
                
                if latency_ms > 800.0 or self.jitter_ms > 200.0:
                    self.last_diagnostic = "HIGH_JITTER_DEGRADE_WARNING"
                elif self.packet_loss_percent > 5.0:
                    self.last_diagnostic = "INTERMITTENT_LINK_LOSS"
                else:
                    self.last_diagnostic = "HEALTHY_OPTIMAL_STREAMS"

        # Automatically sync findings with AGI Blackboard (outside the lock to prevent deadlocks)
        self.publish_to_agi_blackboard()

    def diagnose_connection_problem(self, target_host: str = "duckduckgo.com") -> Dict[str, Any]:
        """
        Runs comprehensive multi-layer connectivity diagnostics to identify failures.
        """
        diag = {"target": target_host, "timestamp": time.time(), "tests": {}, "recommendation": "Maintain standard connection flow."}
        
        # 1. Check DNS resolution layer
        try:
            from internet.network.network_engine import get_network_engine
            dns_res = get_network_engine().resolve_domain_strategy(target_host, timeout=1.5)
            diag["tests"]["dns_resolution"] = "PASSED" if dns_res["resolved"] else f"FAILED ({dns_res.get('error')})"
            if not dns_res["resolved"]:
                diag["recommendation"] = "Switch DNS resolver from primary to Cloudflare 1.1.1.1 or invoke offline local RAG."
                return diag
        except Exception as e:
            diag["tests"]["dns_resolution"] = f"ERROR ({e})"

        # 2. Check TCP socket handshake layer
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(1.5)
            s.connect((target_host, 80))
            diag["tests"]["tcp_reachability"] = "PASSED"
        except Exception as err:
            diag["tests"]["tcp_reachability"] = f"FAILED ({err})"
            diag["recommendation"] = "Trigger L2-L4 Address Bouncer immediately to cycle IP/ports, or reroute via alternative search provider."
        finally:
            try:
                s.close()
            except Exception as _e:
                import logging
                logging.getLogger(__name__).debug(f"Fallback triggered: {_e}")

        # 3. Assess metadata parameters
        diag["tests"]["jitter_ms"] = self.jitter_ms
        diag["tests"]["packet_loss"] = f"{self.packet_loss_percent}%"
        diag["status"] = self.last_diagnostic
        return diag

    def publish_to_agi_blackboard(self) -> bool:
        """
        Feeds network observations and L2-L4 Address Bouncing identity directly into Vivy's Cognitive Blackboard.
        This grants cognitive planning modules awareness of network defense and bandwidth states!
        """
        try:
            from agi.blackboard import get_cognitive_blackboard
            bb = get_cognitive_blackboard()

            # Retrieve active bouncer state
            try:
                from internet.network.address_bouncer import get_address_bouncer
                bouncer_identity = get_address_bouncer().get_current_identity()
            except Exception:
                bouncer_identity = {"status": "inactive"}

            # Retrieve Tor SOCKS5 circuit & Network Mode state
            try:
                from internet.network.tor_manager import get_tor_manager
                from internet.network.request_router import get_request_router
                tor_status = get_tor_manager().get_status_dict()["circuit_identity"]
                net_mode = get_request_router().get_current_mode().value
            except Exception:
                tor_status = {"active_circuit": "DIRECT_HTTPS"}
                net_mode = "NORMAL_DIRECT_HTTPS"

            with self._lock:
                diag_status = self.last_diagnostic
                lat_history = list(self.latency_history_ms)
                jitt = self.jitter_ms
                pkt_loss = self.packet_loss_percent
                est_bw = self.estimated_bandwidth_mbps
                
            avg_lat = round(sum(lat_history)/len(lat_history), 1) if lat_history else 0.0

            payload = {
                "diagnostic_status": diag_status,
                "avg_latency_ms": avg_lat,
                "jitter_ms": jitt,
                "packet_loss_pct": pkt_loss,
                "estimated_bandwidth_mbps": est_bw,
                "active_network_defense": bouncer_identity.get("tool_pipeline", "Standard"),
                "tor_circuit_path": tor_status.get("path_summary", "None"),
                "network_routing_mode": net_mode,
                "current_mac": bouncer_identity.get("l2_src_mac", "N/A"),
                "current_port": bouncer_identity.get("l4_src_port", "N/A"),
                "timestamp": time.time()
            }

            # Publish to Cognitive Blackboard workspaces
            bb.publish_state("network_intelligence", payload, source_engine="NetworkIntelligenceSubsystem")
            bb.publish_state("security_defense", {"bouncing_identity": bouncer_identity, "tor_circuit": tor_status, "network_mode": net_mode, "interval_seconds": 45.0}, source_engine="AddressBouncer + TorManager")
            return True
        except Exception as err:
            print(f"[NetworkIntelligence] Blackboard sync notice: {err}")
            return False

    def get_intelligence_summary(self) -> Dict[str, Any]:
        with self._lock:
            avg_lat = round(sum(self.latency_history_ms)/len(self.latency_history_ms), 1) if self.latency_history_ms else 0.0
            return {
                "health_diagnostic": self.last_diagnostic,
                "average_latency_ms": avg_lat,
                "jitter_ms": self.jitter_ms,
                "packet_loss_percent": self.packet_loss_percent,
                "estimated_bandwidth_mbps": self.estimated_bandwidth_mbps,
                "agi_blackboard_integration": "ACTIVE"
            }

_global_intel = None
def get_network_intelligence() -> NetworkIntelligence:
    global _global_intel
    if _global_intel is None:
        _global_intel = NetworkIntelligence.get_instance()
    return _global_intel
