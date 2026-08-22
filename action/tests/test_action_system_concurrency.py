"""
Vivy AI — Action System: Concurrency Tests
===========================================
Tests race conditions, overlapping intents, and threading safety
in the SmartManager.
"""

import unittest
import threading
import time
from action.smart_manager import get_smart_manager
from action.intent_model import IntentModel, RiskLevel


class TestActionSystemConcurrency(unittest.TestCase):
    
    def setUp(self):
        self.sm = get_smart_manager()
        # Enable action system for test
        self.sm._enabled = True
        
    def test_concurrent_intent_routing(self):
        """Test multiple intents arriving at the same time."""
        results = []
        
        def route_intent(query):
            res = self.sm.try_route(query)
            results.append(res)
            
        threads = []
        queries = [
            "play some music",
            "open the calculator",
            "search amazon for laptops",
            "pause the video"
        ]
        
        for q in queries:
            t = threading.Thread(target=route_intent, args=(q,))
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        # Verify all threads completed without deadlock and returned something
        self.assertEqual(len(results), len(queries))
        handled_count = sum(1 for r in results if r.get("handled"))
        # At least one should be handled, likely all 4 if capabilities are loaded
        self.assertGreaterEqual(handled_count, 1)

    def test_risk_evaluation_thread_safety(self):
        """Test the centralized risk policy under concurrent load."""
        from action.risk_policy import evaluate_risk
        
        intents = [
            IntentModel("shopping", "purchase", "laptop"),
            IntentModel("file", "open", "doc.txt"),
            IntentModel("file", "delete", "doc.txt"),
            IntentModel("app", "close", "notepad"),
        ]
        
        results = {}
        lock = threading.Lock()
        
        def eval_intent(intent):
            r = evaluate_risk(intent)
            with lock:
                results[intent.action] = r
                
        threads = []
        for i in intents:
            t = threading.Thread(target=eval_intent, args=(i,))
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        self.assertEqual(results["purchase"], RiskLevel.HIGH_RISK.value)
        self.assertEqual(results["open"], RiskLevel.LOW_RISK.value)
        self.assertEqual(results["delete"], RiskLevel.HIGH_RISK.value)
        self.assertEqual(results["close"], RiskLevel.MEDIUM_RISK.value)

if __name__ == "__main__":
    unittest.main()
