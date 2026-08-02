"""
Vivy AI — Session Isolation, Memory Architecture & Knowledge Router Test Suite
"""
import os
import sys
import json
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from session_manager import SessionManager, UserSession, get_session_manager
from memory_orchestrator import ModularMemoryOrchestrator, get_memory_orchestrator
from knowledge_router import KnowledgeRouter, NetworkState, get_knowledge_router

class TestSessionIsolationAndMemory(unittest.TestCase):

    def test_01_session_isolation_starts_empty(self):
        """Verify that starting a new session creates an empty visible history."""
        sm = SessionManager()
        sess1 = sm.start_new_session()
        self.assertIsNotNone(sess1.session_id)
        self.assertEqual(sess1.display_history, [])
        self.assertEqual(sess1.session_messages, [])

        sess1.add_user_message("Hello Vivy!")
        sess1.add_assistant_reply("Hello! How are you?", emotion="happy")
        self.assertEqual(len(sess1.display_history), 2)

        # Start second session — must be isolated and start empty
        sess2 = sm.start_new_session()
        self.assertNotEqual(sess1.session_id, sess2.session_id)
        self.assertEqual(sess2.display_history, [])
        self.assertEqual(sess2.session_messages, [])

    def test_02_memory_persistence(self):
        """Verify persistent long-term memory data is preserved and loadable."""
        mo = ModularMemoryOrchestrator()
        data = mo.get_memory_data()
        self.assertIn("long_term_facts", data)
        self.assertIn("relationship", data)
        self.assertIn("emotion_vector", data)
        self.assertIn("likes", data)
        self.assertIn("dislikes", data)

    def test_03_intent_driven_memory_retrieval(self):
        """Verify memory retrieval triggers on recall questions without exposing internal schemas."""
        mo = ModularMemoryOrchestrator()
        
        # Test recall detection
        self.assertTrue(mo.should_retrieve_memory("Do you remember my name?"))
        self.assertTrue(mo.should_retrieve_memory("What were we discussing last time?"))
        self.assertFalse(mo.should_retrieve_memory("Pass me the salt."))

        # Test natural formatting (no json/dict brackets in retrieved summary)
        mo._memory_data["name"] = "Satyajeet"
        summary = mo.retrieve_relevant_memories("What is my name?")
        self.assertIn("Satyajeet", summary)
        self.assertNotIn("{", summary)
        self.assertNotIn("}", summary)

    def test_04_knowledge_router_capability(self):
        """Verify KnowledgeRouter returns network state and non-blocking query routing."""
        kr = KnowledgeRouter()
        state = kr.get_state()
        self.assertIn(state, [NetworkState.ONLINE, NetworkState.OFFLINE, NetworkState.DEGRADED])

        dummy_search = lambda q: f"Results for {q}"
        res = kr.route_knowledge_query("test query", dummy_search)
        self.assertIsNotNone(res)

if __name__ == "__main__":
    unittest.main()
