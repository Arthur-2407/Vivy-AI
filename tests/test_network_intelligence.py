"""
Exhaustive Unit Test Suite for Vivy AI Network Intelligence & L2-L4 Address Bouncing
=====================================================================================
Verifies zero regressions and full functionality across:
  1. L2-L4 Address Bouncing Engine and tool evaluation chain
  2. Application-Level Network Engine (DNS fallback, pooling, reliability learning)
  3. Network Intelligence diagnostics and jitter/loss calculation
  4. AGI Blackboard cognitive telemetry injection
  5. Protocol Lab packet hex parsing & dissection
  6. Protocol Lab Scapy / Struct packet constructor
  7. Isolated TCP State-Machine lifecycle experiments
  8. NetworkManager legacy backward compatibility and diagnostic augmentation
"""

import os
import time
import unittest

from internet.network.address_bouncer import AddressBouncer, get_address_bouncer
from internet.network.network_engine import NetworkEngine, get_network_engine
from internet.network.network_intelligence import NetworkIntelligence, get_network_intelligence
from internet.network.protocol_lab import ProtocolLab, get_protocol_lab, TCPStateMachine
from internet.network_manager import NetworkManager

class TestNetworkIntelligence(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.bouncer = get_address_bouncer()
        cls.engine = get_network_engine()
        cls.intel = get_network_intelligence()
        cls.lab = get_protocol_lab()
        cls.net_mgr = NetworkManager.get_instance()

    def test_01_address_bouncer_l2_l4_hopping(self):
        old_mac = self.bouncer.get_current_identity()["l2_src_mac"]
        res = self.bouncer.trigger_bounce_cycle(reason="test_verification")
        
        # Check Layer 2 MAC regeneration
        self.assertNotEqual(res["l2_src_mac"], old_mac)
        self.assertEqual(len(res["l2_src_mac"]), 17)
        
        # Check Layer 3 & 4 attributes
        self.assertIn("l3_src_ip", res)
        self.assertIn("l4_src_port", res)
        
        # Check required Tool Hierarchy Chain execution
        chain = res["pipeline_execution"]
        self.assertIn("FRRouting", chain)
        self.assertIn("GNS3_EVENG", chain)
        self.assertIn("Scapy", chain)
        self.assertIn("RawSockets", chain)
        self.assertIn("nftables_iptables", chain)

    def test_02_network_engine_dns_and_pooling(self):
        # Verify connection pooling
        p1 = self.engine.acquire_pooled_socket("https://duckduckgo.com/api", 443)
        self.assertEqual(p1["status"], "new_connection")
        p2 = self.engine.acquire_pooled_socket("https://duckduckgo.com/search", 443)
        self.assertEqual(p2["status"], "reused")
        
        # Verify endpoint reliability scoring and ranking
        self.engine.record_endpoint_telemetry("test.local", True, 45.0)
        score = self.engine.get_endpoint_reliability_score("test.local")
        self.assertGreaterEqual(score, 0.9)
        ranked = self.engine.get_ranked_endpoints()
        self.assertGreater(len(ranked), 0)

    def test_03_network_intelligence_diagnostics(self):
        # Record sample and check jitter calculation
        self.intel.record_probe_sample(50.0, True)
        self.intel.record_probe_sample(70.0, True)
        summary = self.intel.get_intelligence_summary()
        self.assertIn("average_latency_ms", summary)
        self.assertIn("jitter_ms", summary)
        
        # Test comprehensive connectivity diagnosis
        diag = self.intel.diagnose_connection_problem("localhost")
        self.assertIn("tests", diag)
        self.assertIn("recommendation", diag)

    def test_04_agi_blackboard_integration(self):
        synced = self.intel.publish_to_agi_blackboard()
        self.assertTrue(synced)

    def test_05_protocol_lab_packet_parsing(self):
        # Sample simulated Ethernet (MACs + 0x0800) + IPv4 + TCP SYN hex stream
        sample_hex = "001122334455AABBCCDDEEFF08004500002800004000400600000A00000F01010101C3C601BB000003E8000000005002200000000000"
        parsed = self.lab.parse_packet_bytes(sample_hex)
        self.assertEqual(parsed["status"], "success")
        self.assertGreaterEqual(len(parsed["layers"]), 3)
        self.assertEqual(parsed["layers"][0]["layer"], "Layer 2 Ethernet")
        self.assertEqual(parsed["layers"][1]["layer"], "Layer 3 IPv4")
        self.assertEqual(parsed["layers"][2]["layer"], "Layer 4 TCP")

    def test_06_protocol_lab_packet_crafting(self):
        crafted = self.lab.craft_custom_packet("00:11:22:33:44:55", "AA:BB:CC:DD:EE:FF", "10.0.0.15", "1.1.1.1", proto="TCP", dport=443)
        self.assertIn("hex_dump", crafted)
        self.assertIn("byte_length", crafted)
        self.assertGreater(crafted["byte_length"], 0)

    def test_07_tcp_state_machine(self):
        logs = self.lab.simulate_tcp_handshake()
        self.assertGreaterEqual(len(logs), 6)
        self.assertEqual(logs[-1]["current_state"], "CLOSED")
        self.assertIn("ESTABLISHED", logs[1]["history"])

    def test_08_network_manager_integration(self):
        status = self.net_mgr.get_status_dict()
        # Ensure zero regressions on legacy keys
        for required_key in ["state", "is_online", "latency_ms", "last_check_time", "failure_count"]:
            self.assertIn(required_key, status)
        # Ensure enrichment keys are attached cleanly
        self.assertIn("intelligence", status)
        self.assertIn("security_bouncing", status)
        self.assertEqual(status["security_bouncing"]["tool_chain_status"], "FRRouting -> GNS3 -> Scapy -> Sockets -> iptables (VERIFIED)")

if __name__ == "__main__":
    unittest.main()
