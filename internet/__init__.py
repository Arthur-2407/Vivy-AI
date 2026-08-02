"""
Vivy AI — Autonomous Internet Intelligence Layer Package
"""

from internet.search_provider import SearchProvider, SearchResult
from internet.duckduckgo_provider import DuckDuckGoProvider
from internet.network_manager import NetworkManager, NetworkState
from internet.search_cache import SearchCache
from internet.search_planner import SmartSearchPlanner
from internet.knowledge_updater import AutonomousKnowledgeUpdater
from internet.internet_manager import InternetManager

def get_internet_manager() -> InternetManager:
    """Return the global InternetManager singleton instance."""
    return InternetManager.get_instance()

__all__ = [
    "SearchProvider",
    "SearchResult",
    "DuckDuckGoProvider",
    "NetworkManager",
    "NetworkState",
    "SearchCache",
    "SmartSearchPlanner",
    "AutonomousKnowledgeUpdater",
    "InternetManager",
    "get_internet_manager"
]
