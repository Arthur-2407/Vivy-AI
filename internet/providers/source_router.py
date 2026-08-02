"""
Vivy AI — Multi-Source Information Router & Dispatch Layer
==========================================================
Dynamically analyzes queries and directs them to the optimal retrieval providers:
  **Question -> Source Router -> [Search | Wikipedia | ArXiv | GitHub | Official Docs | Forums | News | Local KB]**
Enables relationship-aware multi-source information acquisition without hardcoded bounds.
"""

import threading
from typing import List, Dict, Any, Optional

class SourceRouter:
    """Intelligent dispatcher selecting optimal retrieval adapters for a given query."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "SourceRouter":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def route_query(self, query: str, force_source: Optional[str] = None) -> List[str]:
        """
        Evaluates query semantics and returns an ordered list of target search provider names.
        Always prioritizes local knowledge base (RAG) as the baseline source.
        """
        if force_source:
            return [force_source, "local_rag", "duckduckgo"]

        q_lower = query.strip().lower()
        selected_providers = ["local_rag"]  # Always check local personal KB first

        # 1. Academic & Scientific literature check
        if any(k in q_lower for k in ["arxiv", "paper", "research", "pubmed", "theorem", "study", "journal", "hypothesis"]):
            selected_providers.extend(["academic_literature", "wikipedia", "duckduckgo"])

        # 2. Programming Official Docs & GitHub check
        elif any(k in q_lower for k in ["python", "fastapi", "pytorch", "qt", "cuda", "numpy", "api", "function", "library", "class", "syntax"]):
            selected_providers.extend(["official_docs", "github_package", "forum_discussion", "duckduckgo"])

        # 3. GitHub repositories & package registries check
        elif any(k in q_lower for k in ["github", "pypi", "npm", "crate", "repo", "release notes", "changelog", "package", "dependency"]):
            selected_providers.extend(["github_package", "official_docs", "duckduckgo"])

        # 4. Troubleshooting & Technical Forums check
        elif any(k in q_lower for k in ["error", "bug", "exception", "why did", "how to fix", "stack overflow", "reddit", "hacker news", "forum"]):
            selected_providers.extend(["forum_discussion", "official_docs", "github_package", "duckduckgo"])

        # 5. News, RSS, & Government Statistics check
        elif any(k in q_lower for k in ["news", "latest", "today", "announcement", "rss", "blog", "statistics", "government", "census", "weather"]):
            selected_providers.extend(["rss_monitor", "duckduckgo", "wikipedia"])

        # 6. Encyclopedic & General Definitions check
        elif any(q_lower.startswith(prefix) for prefix in ["what is ", "who is ", "history of ", "define ", "explain "]):
            selected_providers.extend(["wikipedia", "duckduckgo", "academic_literature"])

        # Default multi-source triad
        else:
            selected_providers.extend(["duckduckgo", "wikipedia", "web_crawler"])

        # Ensure unique order preserving priority
        seen = set()
        return [p for p in selected_providers if not (p in seen or seen.add(p))]

_global_source_router = None
def get_source_router() -> SourceRouter:
    global _global_source_router
    if _global_source_router is None:
        _global_source_router = SourceRouter()
    return _global_source_router
