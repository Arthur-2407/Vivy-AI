"""
Vivy AI — Internet Intelligence Layer: Internet Manager Orchestrator
Central facade coordinating search providers, network monitoring, intelligent caching,
smart search planning, and autonomous knowledge update loops.
"""

import os
import json
import threading
from typing import List, Dict, Any, Optional, Tuple

from internet.search_provider import SearchProvider, SearchResult
from internet.duckduckgo_provider import DuckDuckGoProvider
from internet.network_manager import NetworkManager, NetworkState
from internet.search_cache import SearchCache
from internet.search_planner import SmartSearchPlanner
from internet.knowledge_updater import AutonomousKnowledgeUpdater

class InternetManager:
    """Enterprise Internet Intelligence Manager."""

    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls, config_path: Optional[str] = None) -> "InternetManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(config_path=config_path)
            return cls._instance

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.path.join(os.path.dirname(os.path.dirname(__file__)), "vivy_config.json")
        self.config = self._load_config()

        self.enabled = self.config.get("enabled", True)
        self.network_manager = NetworkManager.get_instance(config=self.config)
        self.cache = SearchCache(
            ttl_seconds=float(self.config.get("cache_ttl_seconds", 86400)),
            max_entries=int(self.config.get("max_cache_entries", 1000))
        )
        self.planner = SmartSearchPlanner(network_manager=self.network_manager, cache=self.cache)
        self.knowledge_updater = AutonomousKnowledgeUpdater(network_manager=self.network_manager)

        # Search Provider Registry
        self.providers: Dict[str, SearchProvider] = {}
        self._register_default_providers()

        # Start autonomous network state monitoring
        self.network_manager.start_monitoring()

    def _load_config(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("internet_intelligence", {})
        except Exception as e:
            print(f"[InternetManager] Config load error: {e}")
        return {}

    def _register_default_providers(self):
        ddg = DuckDuckGoProvider(config=self.config)
        self.register_provider(ddg)
        try:
            from internet.providers.web_crawler_provider import WebCrawlerProvider
            from internet.providers.doc_crawler_provider import OfficialDocsProvider
            from internet.providers.github_package_provider import GitHubPackageProvider
            from internet.providers.academic_literature_provider import AcademicLiteratureProvider
            from internet.providers.rss_monitor_provider import RSSMonitorProvider
            from internet.providers.forum_discussion_provider import ForumDiscussionProvider
            from internet.providers.wikipedia_provider import WikipediaProvider
            for prov_cls in [WebCrawlerProvider, OfficialDocsProvider, GitHubPackageProvider, AcademicLiteratureProvider, RSSMonitorProvider, ForumDiscussionProvider, WikipediaProvider]:
                self.register_provider(prov_cls())
        except Exception as err:
            print(f"[InternetManager] Multi-source provider registration notice: {err}")

    def register_provider(self, provider: SearchProvider):
        """Register a search provider adapter (DuckDuckGo, Wikipedia, etc.)."""
        self.providers[provider.name()] = provider
        print(f"[InternetManager] Registered search provider adapter: '{provider.name()}'")

    def search(self, query: str, max_results: int = 3, force_refresh: bool = False) -> str:
        """
        Main internet search interface for prompt context injection.
        Checks network status, consults cache, executes search via registered provider,
        stores in cache, and returns clean formatted markdown snippets.
        """
        if not self.enabled or not query or len(query.strip()) < 2:
            return ""

        clean_query = query.strip()

        # 1. Check cache first if not forced refresh
        if not force_refresh:
            cached_results, is_stale = self.cache.get(clean_query)
            if cached_results and not is_stale:
                print(f"[InternetManager] Cache hit (fresh) for query: '{clean_query}'")
                snippets = [r.to_formatted_snippet() for r in cached_results[:max_results]]
                return "\n".join(snippets)

        # 2. Check network state
        if not self.network_manager.is_online():
            print(f"[InternetManager] Network offline — invoking offline fallback for query: '{clean_query}'")
            return self.planner.evaluate_offline_fallback(clean_query)

        # 3. Execute search via primary provider
        primary_name = self.config.get("primary_provider", "duckduckgo")
        provider = self.providers.get(primary_name) or self.providers.get("duckduckgo")

        if not provider or not provider.is_available():
            print(f"[InternetManager] Provider '{primary_name}' unavailable. Using offline fallback.")
            return self.planner.evaluate_offline_fallback(clean_query)

        results = provider.search(clean_query, max_results=max_results)

        if results:
            # Store in cache
            self.cache.put(clean_query, results, provider=provider.name())
            # Optionally record in knowledge store if auto-update enabled
            if self.config.get("auto_knowledge_update", True):
                summary_text = " ".join([r.snippet for r in results[:2]])
                self.knowledge_updater.update_topic(clean_query, summary_text, source=provider.name())

            snippets = [r.to_formatted_snippet() for r in results[:max_results]]
            return "\n".join(snippets)

        # 4. If online search yielded no results, check if we have stale cache
        cached_results, is_stale = self.cache.get(clean_query)
        if cached_results:
            print(f"[InternetManager] Provider returned 0 results. Using stale cache for: '{clean_query}'")
            snippets = [r.to_formatted_snippet() for r in cached_results[:max_results]]
            return "\n".join(snippets)

        return ""

    def plan_and_search(self, user_input: str, conversation_mode: str = "companion", symptoms: Optional[List[str]] = None) -> Tuple[bool, str]:
        """
        Smart Search Planner pipeline: evaluates if search is needed,
        generates optimized queries, and executes search cycle.
        Returns (did_search: bool, search_results_markdown: str).
        """
        if not self.enabled:
            return False, ""

        queries = self.planner.plan_query(user_input, conversation_mode=conversation_mode, symptoms=symptoms)
        if not queries:
            return False, ""

        combined_snippets = []
        for q in queries:
            snippet = self.search(q)
            if snippet:
                combined_snippets.append(snippet)

        if combined_snippets:
            return True, "\n".join(combined_snippets)

        return False, ""

    def get_status(self) -> Dict[str, Any]:
        """Return comprehensive Internet Intelligence status dict."""
        return {
            "enabled": self.enabled,
            "network": self.network_manager.get_status_dict(),
            "cache": self.cache.get_stats(),
            "registered_providers": list(self.providers.keys()),
            "primary_provider": self.config.get("primary_provider", "duckduckgo")
        }
