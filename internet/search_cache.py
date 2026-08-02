"""
Vivy AI — Internet Intelligence Layer: Search Cache System
Implements an intelligent TTL search cache supporting query normalization,
keyword & similarity retrieval, metadata tracking, and stale data refresh.
"""

import os
import json
import time
import re
import threading
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional, Tuple

from internet.search_provider import SearchResult

class SearchCache:
    """Intelligent search cache with TTL, metadata, and similarity matching."""

    def __init__(self, cache_file: str = "shared/search_cache.json", ttl_seconds: float = 86400, max_entries: int = 1000):
        self.cache_file = cache_file
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.lock = threading.Lock()

        self._cache: Dict[str, Dict[str, Any]] = {}
        self._load_cache()

    def _load_cache(self):
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
                print(f"[SearchCache] Loaded {len(self._cache)} search cache entries.")
        except Exception as e:
            print(f"[SearchCache] Failed to load search cache: {e}")
            self._cache = {}

    def save_cache(self):
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            tmp_file = self.cache_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
            os.replace(tmp_file, self.cache_file)
        except Exception as e:
            print(f"[SearchCache] Failed to save search cache: {e}")

    def normalize_query(self, query: str) -> str:
        """Clean and normalize query string for indexing."""
        clean = re.sub(r'[^\w\s]', '', query.lower()).strip()
        return " ".join(clean.split())

    def get(self, query: str) -> Tuple[Optional[List[SearchResult]], bool]:
        """
        Retrieve cached results for a query.
        Returns (results: Optional[List[SearchResult]], is_stale: bool).
        If query is not in cache or expired beyond 2x TTL, returns (None, False).
        """
        norm = self.normalize_query(query)
        with self.lock:
            entry = self._cache.get(norm)
            if not entry:
                # Try similarity search against cached queries
                entry, norm = self._find_similar_entry(norm)

            if not entry:
                return None, False

            timestamp = entry.get("timestamp", 0)
            age = time.time() - timestamp

            raw_results = entry.get("results", [])
            results = [SearchResult.from_dict(r) for r in raw_results]

            is_stale = age > self.ttl_seconds
            return results, is_stale

    def _find_similar_entry(self, norm_query: str, threshold: float = 0.88) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        for k, entry in self._cache.items():
            ratio = SequenceMatcher(None, norm_query, k).ratio()
            if ratio >= threshold:
                return entry, k
        return None, None

    def put(self, query: str, results: List[SearchResult], provider: str = "unknown"):
        """Store query results in cache with metadata."""
        if not results:
            return

        norm = self.normalize_query(query)
        payload = {
            "query": query,
            "normalized_query": norm,
            "provider": provider,
            "timestamp": time.time(),
            "results": [r.to_dict() for r in results]
        }

        with self.lock:
            self._cache[norm] = payload
            # Evict oldest if exceeding max entries
            if len(self._cache) > self.max_entries:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].get("timestamp", 0))
                del self._cache[oldest_key]
            self.save_cache()

    def clear(self):
        with self.lock:
            self._cache.clear()
            self.save_cache()

    def size(self) -> int:
        with self.lock:
            return len(self._cache)

    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            total = len(self._cache)
            now = time.time()
            stale_count = sum(1 for e in self._cache.values() if (now - e.get("timestamp", 0)) > self.ttl_seconds)
            return {
                "total_entries": total,
                "stale_entries": stale_count,
                "fresh_entries": total - stale_count,
                "ttl_seconds": self.ttl_seconds
            }
