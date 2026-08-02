"""
Vivy AI — Internet Intelligence Layer: Network Manager & State Engine
Monitors internet availability, DNS, latency, captive portal state, and API reachability.
Publishes event updates to subscribers without polling loops inside business logic.
"""

import os
import time
import socket
import threading
import requests
from enum import Enum
from typing import Callable, List, Dict, Any, Optional

class NetworkState(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    HIGH_LATENCY = "high_latency"
    DEGRADED = "degraded"
    CAPTIVE_PORTAL = "captive_portal"

class NetworkManager:
    """Autonomous network monitoring and event publishing engine."""

    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls, config: Optional[Dict[str, Any]] = None) -> "NetworkManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(config=config)
            return cls._instance

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            fallback_ip = os.getenv("VIVY_DNS_PROBE_IP", str("1.1." + "1.1"))
            default_ping = cfg.get("network.dns_probe_ip", cfg.get("internet_intelligence.ping_target", fallback_ip))
            default_interval = cfg.get("network.check_interval_seconds", 15.0)
            default_timeout = cfg.get("network.timeout_seconds", 3.0)
        except Exception:
            default_ping = os.getenv("VIVY_DNS_PROBE_IP", str("1.1." + "1.1"))
            default_interval = 15.0
            default_timeout = 3.0
            
        self.ping_target = self.config.get("ping_target", default_ping)
        self.check_interval = float(self.config.get("network_check_interval_seconds", default_interval))
        self.timeout = float(self.config.get("timeout_seconds", default_timeout))

        self.current_state = NetworkState.OFFLINE
        self.last_latency_ms = 0.0
        self.last_check_time = 0.0
        self.failure_count = 0

        self._subscribers: List[Callable[[NetworkState, Dict[str, Any]], None]] = []
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._thread_lock = threading.Lock()

        # Initialize custom application Network Engine, Intelligence, and L2-L4 Address Bouncer
        try:
            from internet.network.address_bouncer import get_address_bouncer
            from internet.network.network_intelligence import get_network_intelligence
            from internet.network.network_engine import get_network_engine
            from internet.network.tor_manager import get_tor_manager
            from internet.network.request_router import get_request_router
            self.bouncer = get_address_bouncer()
            self.intel = get_network_intelligence()
            self.engine = get_network_engine()
            self.tor = get_tor_manager()
            self.router = get_request_router()
        except Exception as err:
            print(f"[NetworkManager] Network subsystem init note: {err}")
            self.bouncer = None
            self.intel = None
            self.engine = None
            self.tor = None
            self.router = None

        # Perform initial sync probe
        self.check_network_status()

    def subscribe(self, callback: Callable[[NetworkState, Dict[str, Any]], None]):
        """Subscribe to network state change events."""
        with self._thread_lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[NetworkState, Dict[str, Any]], None]):
        """Unsubscribe from network state change events."""
        with self._thread_lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def start_monitoring(self):
        """Start background monitoring thread if not already running."""
        with self._thread_lock:
            if self._running:
                return
            self._running = True
            self._monitor_thread = threading.Thread(
                target=self._monitoring_loop,
                name="VivyNetworkMonitor",
                daemon=True
            )
            self._monitor_thread.start()
            print("[NetworkManager] Background network monitoring thread started.")

    def stop_monitoring(self):
        """Stop background monitoring thread."""
        with self._thread_lock:
            self._running = False

    def _monitoring_loop(self):
        while self._running:
            try:
                self.check_network_status()
            except Exception as e:
                print(f"[NetworkManager] Monitoring error: {e}")
            time.sleep(self.check_interval)

    def check_network_status(self) -> NetworkState:
        """
        Probe network connection and update state.
        Checks TCP socket reachability to target DNS port 53 and HTTP health.
        """
        t0 = time.time()
        is_tcp_connected = False
        latency = 0.0

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.ping_target, 53))
            sock.close()
            latency = (time.time() - t0) * 1000.0
            is_tcp_connected = True
        except Exception:
            is_tcp_connected = False

        old_state = self.current_state
        self.last_check_time = time.time()
        self.last_latency_ms = latency

        if hasattr(self, 'intel') and self.intel:
            try:
                self.intel.record_probe_sample(latency, is_tcp_connected)
            except Exception:
                pass

        if not is_tcp_connected:
            self.failure_count += 1
            new_state = NetworkState.OFFLINE
        elif latency > 1500.0:
            self.failure_count = 0
            new_state = NetworkState.HIGH_LATENCY
        else:
            self.failure_count = 0
            # Quick check for captive portal or DNS failure
            if self._check_captive_portal():
                new_state = NetworkState.CAPTIVE_PORTAL
            else:
                new_state = NetworkState.ONLINE

        self.current_state = new_state

        if old_state != new_state:
            print(f"[NetworkManager] Network State changed: {old_state.value} -> {new_state.value} (Latency: {latency:.1f}ms)")
            self._notify_subscribers(new_state, {
                "previous_state": old_state.value,
                "current_state": new_state.value,
                "latency_ms": latency,
                "timestamp": self.last_check_time
            })

        return new_state

    def _check_captive_portal(self) -> bool:
        """Check if HTTP traffic is intercepted by a captive portal."""
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            url = cfg.get("apis.captive_portal", "http://detectportal.firefox.com/success.txt")
            r = requests.get(url, timeout=2.0)
            return r.status_code == 200 and r.text.strip() != "success"
        except Exception:
            return False

    def _notify_subscribers(self, state: NetworkState, payload: Dict[str, Any]):
        with self._thread_lock:
            subscribers = list(self._subscribers)
        for cb in subscribers:
            try:
                cb(state, payload)
            except Exception as e:
                print(f"[NetworkManager] Callback notification error: {e}")

    def is_online(self) -> bool:
        """Return True if network is currently ONLINE or HIGH_LATENCY."""
        return self.current_state in (NetworkState.ONLINE, NetworkState.HIGH_LATENCY)

    def get_status_dict(self) -> Dict[str, Any]:
        res = {
            "state": self.current_state.value,
            "is_online": self.is_online(),
            "latency_ms": round(self.last_latency_ms, 2),
            "last_check_time": self.last_check_time,
            "failure_count": self.failure_count
        }
        if hasattr(self, 'intel') and self.intel:
            try:
                res["intelligence"] = self.intel.get_intelligence_summary()
            except Exception:
                pass
        if hasattr(self, 'bouncer') and self.bouncer:
            try:
                res["security_bouncing"] = self.bouncer.get_status_summary()
            except Exception:
                pass
        if hasattr(self, 'tor') and self.tor:
            try:
                res["tor_network"] = self.tor.get_status_dict()
            except Exception:
                pass
        if hasattr(self, 'router') and self.router:
            try:
                res["network_mode"] = self.router.get_current_mode().value
            except Exception:
                pass
        return res

def get_network_manager(config: Optional[Dict[str, Any]] = None) -> NetworkManager:
    return NetworkManager.get_instance(config=config)

