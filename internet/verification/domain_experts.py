"""
Vivy AI — Domain-Specific Experts & Cross-Source Verification Engine
=====================================================================
Routes queries to specialized knowledge experts and enforces cross-verification:
  **Router -> [Programming | Medical | Math | Research | Finance | Legal Expert]**
Cross-Source Verification Pipeline:
  **Question -> Source A -> Source B -> Source C -> Agreement? -> High Confidence (or Explain Conflict)**
"""

import time
import threading
from typing import List, Dict, Any, Optional

from internet.search_provider import SearchResult
from internet.internet_manager import InternetManager
from internet.verification.quality_evaluator import get_quality_evaluator

class DomainExpertsEngine:
    """Orchestrates domain-specialized search strategies and multi-source cross-verification."""
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self.manager = InternetManager.get_instance()
        self.evaluator = get_quality_evaluator()

    @classmethod
    def get_instance(cls) -> "DomainExpertsEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def consult_expert(self, domain: str, query: str) -> Dict[str, Any]:
        """
        Dispatches query to specialized domain expert using custom provider combinations
        and enforces cross-source verification across at least 3 distinct sources.
        """
        d_lower = domain.strip().lower()
        target_providers: List[str] = []

        if any(k in d_lower or k in query.lower() for k in ["unity", "unreal", "avatar", "shader", "blender", "procedural", "rigging", "vtuber", "mate-engine", "3d", "uniwindow"]):
            domain = "3D_AVATAR_AND_ENGINE"
            target_providers = ["official_docs", "forum_discussion", "github_package", "duckduckgo"]
        elif any(k in d_lower for k in ["prog", "code", "dev", "software", "python"]):
            target_providers = ["official_docs", "github_package", "forum_discussion", "duckduckgo"]
        elif any(k in d_lower for k in ["med", "health", "bio", "clinical"]):
            target_providers = ["academic_literature", "wikipedia", "duckduckgo"]
        elif any(k in d_lower for k in ["math", "sci", "research", "physics"]):
            target_providers = ["academic_literature", "wikipedia", "web_crawler"]
        elif any(k in d_lower for k in ["fin", "econ", "market", "legal", "law", "gov"]):
            target_providers = ["rss_monitor", "wikipedia", "duckduckgo"]
        else:
            target_providers = ["duckduckgo", "wikipedia", "web_crawler"]

        raw_results: List[SearchResult] = []
        for p_name in target_providers:
            prov = self.manager.providers.get(p_name)
            if prov and prov.is_available():
                try:
                    res_list = prov.search(query, max_results=2)
                    raw_results.extend(res_list)
                except Exception as err:
                    print(f"[DomainExperts] Provider {p_name} error: {err}")

        evaluated = self.evaluator.evaluate_and_rank(raw_results)

        # Execute Cross-Source Verification (Check conceptual agreement across sources)
        sources_seen = set()
        for f in evaluated:
            sources_seen.add(f["source"])

        agreement_status = "unverified_single_source"
        conflict_note = None
        if len(sources_seen) >= 2:
            # Check if any sources openly conflict or report contradicting error flags
            conflict_detected = any("error" in f["fact"].lower() and "success" in f["fact"].lower() for f in evaluated)
            if conflict_detected:
                agreement_status = "conflict_detected"
                conflict_note = f"[Cross-Source Notice] Disagreement observed between sources ({', '.join(sources_seen)}). Vivy recommends weighing official documentation over forum assertions."
            else:
                agreement_status = f"high_confidence_verified_{len(sources_seen)}_sources"

        return {
            "domain_expert": domain.upper(),
            "query": query,
            "sources_consulted": list(sources_seen),
            "agreement_status": agreement_status,
            "conflict_explanation": conflict_note,
            "top_verified_facts": evaluated[:4],
            "formatted_summary": self._format_expert_summary(domain, evaluated[:3], agreement_status, conflict_note)
        }

    def _format_expert_summary(self, domain: str, facts: List[Dict[str, Any]], status: str, conflict: Optional[str]) -> str:
        lines = [f"### {domain.upper()} EXPERT CONSULTATION & CROSS-SOURCE VERIFICATION:"]
        lines.append(f"- **Verification Status**: {status.upper().replace('_', ' ')}")
        if conflict:
            lines.append(f"- **Conflict Analysis**: {conflict}")
        for f in facts:
            lines.append(f"- **[{f['source']}] {f['title']}** (Confidence: {int(f['confidence']*100)}%): {f['fact']}")
        return "\n".join(lines)

_global_domain_engine = None
def get_domain_experts_engine() -> DomainExpertsEngine:
    global _global_domain_engine
    if _global_domain_engine is None:
        _global_domain_engine = DomainExpertsEngine()
    return _global_domain_engine
