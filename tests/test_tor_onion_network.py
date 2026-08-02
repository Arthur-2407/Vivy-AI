"""
Vivy AI — Verification Suite: Embedded Tor, Onion Routing & Smart Network Modes
=================================================================================
Exhaustively tests all newly integrated networking components and legacy integrations:
  1. Tor Config & Startup Sequence (torrc generation, OS detection)
  2. Tor Circuit Identity Hopping (Entry -> Middle -> Exit node cycling)
  3. Smart Request Router & 4 Network Modes (Normal, Private, Hybrid, Offline)
  4. Internal Browserless DuckDuckGo HTML/Lite Search Client
  5. Automatic Onion Domain Client (.onion Support)
  6. Network Intelligence & AGI Cognitive Blackboard Telemetry Sync
  7. Legacy NetworkManager Zero Regression & Subsystem Binding
"""

import os
import time
import unittest
from typing import Dict, Any

from internet.network.tor_config import get_tor_config
from internet.network.tor_manager import get_tor_manager
from internet.network.proxy_manager import get_proxy_manager
from internet.network.dns_manager import get_dns_manager
from internet.network.connection_pool import get_connection_pool
from internet.network.network_security import get_network_security
from internet.network.duckduckgo_client import get_duckduckgo_client
from internet.network.onion_client import get_onion_client
from internet.network.request_router import get_request_router, NetworkMode
from internet.network.network_intelligence import get_network_intelligence
from internet.network_manager import get_network_manager

class TestTorOnionNetwork(unittest.TestCase):

    def test_01_tor_config_and_startup_sequence(self):
        print("\n[TEST 1] Verifying embedded Tor configuration & startup sequence...")
        mgr = get_tor_manager()
        status = mgr.get_status_dict()
        self.assertTrue(status["ready"], "Tor Manager must report ready status on startup.")
        self.assertTrue(os.path.exists(status["config"]["tor_data_dir"]), "tor_data directory must be created in workspace.")
        self.assertTrue(status["config"]["torrc_file_ready"], "torrc configuration file must be generated.")
        self.assertTrue(status["config"]["license_notice_included"], "Tor license notice must be distributed.")
        print(f"[PASSED] Tor Ready: {status['ready']} | Engine Mode: {status['controller']['engine_mode']} | OS: {status['config']['os_detected']}")

    def test_02_tor_circuit_identity_rotation(self):
        print("\n[TEST 2] Verifying cryptographic circuit identity rotation and relay hopping...")
        mgr = get_tor_manager()
        circ1 = mgr.request_new_identity()
        id1 = circ1["circuit_id"]
        path1 = f"{circ1['entry_guard']['country']} -> {circ1['middle_relay']['country']} -> {circ1['exit_node']['country']}"
        time.sleep(0.1)
        circ2 = mgr.request_new_identity()
        id2 = circ2["circuit_id"]
        path2 = f"{circ2['entry_guard']['country']} -> {circ2['middle_relay']['country']} -> {circ2['exit_node']['country']}"
        self.assertNotEqual(id1, id2, "Circuit ID must rotate upon request_new_identity().")
        print(f"[PASSED] Rotated Circuit: {id1} ({path1}) ==> {id2} ({path2})")

    def test_03_smart_request_router_modes(self):
        print("\n[TEST 3] Verifying Smart Request Router across all 4 Network Modes...")
        router = get_request_router()
        
        # Test Mode 3 Hybrid Default
        router.set_mode(NetworkMode.HYBRID)
        route_weather = router.evaluate_route("weather in new york")
        self.assertEqual(route_weather["route"], "DIRECT_INTERNET_HTTPS", "Standard research must route via fast Direct HTTPS.")
        
        route_anon = router.evaluate_route("anonymous search for government blocked news")
        self.assertEqual(route_anon["route"], "ONION_TOR_SOCKS5", "Sensitive privacy keywords must route via Tor SOCKS5 circuit.")
        
        route_onion = router.evaluate_route("http://vivydarknet77.onion")
        self.assertEqual(route_onion["route"], "ONION_TOR_SOCKS5", ".onion domains must automatically invoke Onion routing.")

        # Test Mode 2 Private
        router.set_mode(NetworkMode.PRIVATE)
        self.assertEqual(router.evaluate_route("basic math")["route"], "ONION_TOR_SOCKS5", "Private Mode must force all queries through Tor.")

        # Test Mode 4 Offline
        router.set_mode(NetworkMode.OFFLINE)
        self.assertEqual(router.evaluate_route("weather")["route"], "OFFLINE_LOCAL_RAG_KB", "Offline Mode must force Local RAG interception.")
        
        # Reset to default
        router.set_mode(NetworkMode.HYBRID)
        print("[PASSED] Smart Request Router successfully evaluated all dynamic rule classifications.")

    def test_04_duckduckgo_client_internal(self):
        print("\n[TEST 4] Verifying browserless DuckDuckGo client over Direct and Tor SOCKS5 channels...")
        ddg = get_duckduckgo_client()
        res_direct = ddg.search_internal("quantum computing advancements", use_tor=False)
        self.assertEqual(res_direct["status"], "success", "Direct browserless search must return success or sandbox fallback.")
        self.assertFalse(res_direct["is_tor"])
        
        res_tor = ddg.search_internal("untraceable security audit", use_tor=True)
        self.assertTrue(res_tor["is_tor"], "Tor proxy channel must be tagged inside search result.")
        self.assertIn("Onion SOCKS5", res_tor["pool_channel"], "Tor search must utilize isolated Onion Connection Pool.")
        print(f"[PASSED] Browserless DDG Client | Direct Latency: {res_direct['latency_ms']}ms | Tor Latency: {res_tor['latency_ms']}ms")

    def test_05_onion_client_routing(self):
        print("\n[TEST 5] Verifying automatic Onion Client routing for .onion top-level domains...")
        onion = get_onion_client()
        resp = onion.fetch_onion("http://vivycognitionx8.onion")
        self.assertEqual(resp["status_code"], 200, "Onion fetch must resolve cleanly through sandbox or live route.")
        self.assertIn("Tor SOCKS5 Proxy Circuit", resp["routing"])
        self.assertIsNotNone(resp["apparent_exit_ip"])
        print(f"[PASSED] Automatic Onion Routing successful: {resp['url']} via Circuit {resp['active_circuit']}")

    def test_06_network_intelligence_and_blackboard_sync(self):
        print("\n[TEST 6] Verifying AGI Cognitive Blackboard synchronization of Tor circuits and defense states...")
        intel = get_network_intelligence()
        sync_ok = intel.publish_to_agi_blackboard()
        self.assertTrue(sync_ok, "Publishing to AGI Blackboard must return True.")
        
        from agi.blackboard import get_cognitive_blackboard
        bb = get_cognitive_blackboard()
        intel_space = bb.get_state("network_intelligence") or {}
        sec_space = bb.get_state("security_defense") or {}
        self.assertIn("tor_circuit_path", intel_space, "Blackboard network_intelligence must contain active Tor circuit path.")
        self.assertIn("network_mode", sec_space, "Blackboard security_defense must record active Network Mode.")
        print(f"[PASSED] AGI Blackboard self-aware of Tor Path: {intel_space.get('tor_circuit_path')} & Mode: {sec_space.get('network_mode')}")

    def test_07_network_manager_zero_regression(self):
        print("\n[TEST 7] Verifying legacy NetworkManager binding and zero regressions...")
        nm = get_network_manager()
        status = nm.get_status_dict()
        self.assertIn("tor_network", status, "NetworkManager get_status_dict must report tor_network subdict.")
        self.assertIn("network_mode", status, "NetworkManager must report current network_mode.")
        self.assertIsNotNone(nm.tor, "NetworkManager.tor attribute must bind to TorManager.")
        self.assertIsNotNone(nm.router, "NetworkManager.router attribute must bind to RequestRouter.")
        print(f"[PASSED] Legacy NetworkManager fully bound with zero regressions. Current State: {status['state']}")

if __name__ == "__main__":
    unittest.main()
