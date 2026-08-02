"""
Vivy AI — Internet Intelligence Layer Unit Test Suite
Tests SearchProvider contract, DuckDuckGoProvider, NetworkManager, SearchCache,
SmartSearchPlanner, AutonomousKnowledgeUpdater, and InternetManager facade.
"""

import os
import sys
import time
import unittest
from typing import List

# Ensure BASE_DIR is in path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from internet import (
    SearchProvider,
    SearchResult,
    DuckDuckGoProvider,
    NetworkManager,
    NetworkState,
    SearchCache,
    SmartSearchPlanner,
    AutonomousKnowledgeUpdater,
    InternetManager,
    get_internet_manager
)

class DummyProvider(SearchProvider):
    def name(self) -> str:
        return "dummy"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 5, **kwargs) -> List[SearchResult]:
        return [
            SearchResult(
                title=f"Result for {query}",
                snippet=f"Snippet for {query}",
                url="https://example.com",
                source="dummy",
                confidence=1.0
            )
        ]

class TestInternetIntelligence(unittest.TestCase):

    def setUp(self):
        self.temp_cache_file = os.path.join(BASE_DIR, "shared", "test_search_cache.json")
        if os.path.exists(self.temp_cache_file):
            try: os.remove(self.temp_cache_file)
            except Exception: pass

    def tearDown(self):
        if os.path.exists(self.temp_cache_file):
            try: os.remove(self.temp_cache_file)
            except Exception: pass

    def test_search_result_formatting(self):
        sr = SearchResult(title="Python 3.12", snippet="Python release notes", url="https://python.org")
        fmt = sr.to_formatted_snippet()
        self.assertIn("**Python 3.12**", fmt)
        self.assertIn("Python release notes", fmt)

    def test_search_cache_put_get(self):
        cache = SearchCache(cache_file=self.temp_cache_file, ttl_seconds=10.0)
        sr = SearchResult(title="Test", snippet="Sample snippet", source="test")
        cache.put("latest python news", [sr], provider="test")

        results, is_stale = cache.get("latest python news")
        self.assertIsNotNone(results)
        self.assertFalse(is_stale)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Test")

    def test_search_cache_similarity_match(self):
        cache = SearchCache(cache_file=self.temp_cache_file, ttl_seconds=10.0)
        sr = SearchResult(title="Test", snippet="Similar snippet", source="test")
        cache.put("what is python programming language", [sr], provider="test")

        # Query with slightly different phrasing
        results, is_stale = cache.get("what is python programming language?")
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 1)

    def test_network_manager_probe(self):
        nm = NetworkManager.get_instance()
        state = nm.check_network_status()
        self.assertIn(state, list(NetworkState))
        status = nm.get_status_dict()
        self.assertIn("state", status)
        self.assertIn("is_online", status)

    def test_smart_search_planner(self):
        planner = SmartSearchPlanner()
        # Companion queries should NOT search
        self.assertFalse(planner.is_search_needed("How are you today?", categories=["greeting"]))
        # Informational / news / health queries SHOULD search
        self.assertTrue(planner.is_search_needed("What is the latest news about Python 3.13?"))

    def test_internet_manager_facade(self):
        im = get_internet_manager()
        self.assertIsNotNone(im)
        # Register dummy provider
        dummy = DummyProvider()
        im.register_provider(dummy)
        
        # Test searching via InternetManager
        res = im.search("test query", force_refresh=True)
        self.assertTrue(isinstance(res, str))
        
        status = im.get_status()
        self.assertTrue(status.get("enabled"))
        self.assertIn("dummy", status.get("registered_providers", []))

    def test_duckduckgo_provider_interface(self):
        ddg = DuckDuckGoProvider()
        self.assertEqual(ddg.name(), "duckduckgo")
        self.assertTrue(ddg.is_available())

if __name__ == "__main__":
    unittest.main()
