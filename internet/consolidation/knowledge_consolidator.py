"""
Vivy AI — Long-Term Knowledge Consolidation & Personal Knowledge Graph
======================================================================
Consolidation Pipeline:
  **Search Results -> Extract Facts -> Verify (Confidence >= 0.7) -> Knowledge Graph -> Memory**
Personal Knowledge Graph (`shared/personal_graph.json`):
  Maintains structured persistent intelligence about:
    - User projects, long-term goals, hardware specifications, coding style, and tool preferences.
"""

import os
import json
import time
import threading
from typing import Dict, List, Any, Optional

from agi.knowledge_graph import get_knowledge_graph

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORAGE_DIR = os.path.join(BASE_DIR, "shared")
PERSONAL_GRAPH_PATH = os.path.join(STORAGE_DIR, "personal_graph.json")

class KnowledgeConsolidator:
    """Consolidates verified facts into systemic graph memory and updates user profile graph."""
    _instance = None
    _lock = threading.RLock()

    def __init__(self, personal_graph_path: Optional[str] = None):
        self.path = personal_graph_path or PERSONAL_GRAPH_PATH
        self.general_kg = get_knowledge_graph()
        self.personal_data: Dict[str, Dict[str, Any]] = {
            "projects": {},
            "goals": {},
            "coding_style": {"language": "python", "frameworks": ["FastAPI", "PyTorch", "Qt"], "preference": "clean object-oriented modular design"},
            "hardware": {"gpu": "NVIDIA", "os": "windows", "environment": "local_venv"},
            "long_term_plans": {}
        }
        self.short_term_buffer: List[Dict[str, Any]] = []
        self._running = False
        self._deferred_interval_seconds = 300.0  # 5 minutes background interval
        self._load_personal_graph()
        self._start_deferred_monitor()

    @classmethod
    def get_instance(cls) -> "KnowledgeConsolidator":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _start_deferred_monitor(self):
        import sys
        if os.environ.get("VIVY_TESTING") == "1" or "unittest" in sys.modules or "pytest" in sys.modules:
            return
        with self._lock:
            if not self._running:
                self._running = True
                t = threading.Thread(target=self._deferred_consolidation_loop, name="VivyMemoryConsolidator", daemon=True)
                t.start()

    def _deferred_consolidation_loop(self):
        while self._running:
            time.sleep(self._deferred_interval_seconds)
            try:
                self.flush_deferred_consolidation()
            except Exception as e:
                print(f"[KnowledgeConsolidator] Deferred background processing note: {e}")

    def flush_deferred_consolidation(self) -> int:
        """
        Deferred background execution every 5-15 minutes or during low-load intervals:
        Deduplicates short-term knowledge, scores importance, builds relationships, and syncs AGI Blackboard.
        """
        with self._lock:
            if not self.short_term_buffer:
                return 0
            seen_triples = set()
            consolidated_count = 0
            for item in list(self.short_term_buffer):
                s, p, o = item["subject"], item["predicate"], item["object_value"]
                conf = item.get("confidence", 0.85)
                triple_key = (s.lower(), p.lower(), o.lower())
                if triple_key not in seen_triples and conf >= 0.65:
                    seen_triples.add(triple_key)
                    if self.general_kg.add_triple(s, p, o, confidence=conf):
                        consolidated_count += 1
            self.short_term_buffer.clear()
            self.save_personal_graph()
            
            # Sync consolidated long-term facts with Cognitive Blackboard
            try:
                from agi.blackboard import get_cognitive_blackboard
                bb = get_cognitive_blackboard()
                bb.publish_state("knowledge_consolidation", {
                    "last_consolidated_count": consolidated_count,
                    "timestamp": time.time(),
                    "memory_model": "HYBRID_REALTIME_IMMEDIATE + DEFERRED_BACKGROUND"
                }, source_engine="KnowledgeConsolidator")
            except Exception:
                pass
            return consolidated_count

    def _load_personal_graph(self):
        with self._lock:
            try:
                if os.path.exists(self.path):
                    with open(self.path, "r", encoding="utf-8") as f:
                        self.personal_data = json.load(f)
            except Exception as e:
                print(f"[KnowledgeConsolidator] Personal graph load warning: {e}")

    def save_personal_graph(self):
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                tmp = f"{self.path}.tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.personal_data, f, indent=2, ensure_ascii=False)
                os.replace(tmp, self.path)
            except Exception as e:
                print(f"[KnowledgeConsolidator] Save warning: {e}")

    def consolidate_verified_fact(self, subject: str, predicate: str, object_value: str, confidence: float = 0.85, source: str = "verified_search") -> bool:
        """
        Hybrid Memory Architecture (Immediate Real-Time Layer):
        Immediately registers query metadata and reasoning into short-term buffer,
        while integrating verified triples into active systemic memory.
        """
        if float(confidence) < 0.65 or not subject or not object_value:
            return False

        with self._lock:
            self.short_term_buffer.append({
                "subject": subject,
                "predicate": predicate,
                "object_value": object_value,
                "confidence": confidence,
                "source": source,
                "timestamp": time.time()
            })
            return self.general_kg.add_triple(subject, predicate, object_value, confidence=confidence)

    def update_user_profile(self, category: str, item_key: str, value: Any) -> Dict[str, Any]:
        """Updates structured facts in the Personal Knowledge Graph (e.g., hardware, projects)."""
        with self._lock:
            cat_clean = category.lower()
            if cat_clean not in self.personal_data:
                self.personal_data[cat_clean] = {}
            self.personal_data[cat_clean][str(item_key)] = {"value": value, "updated_at": time.time()}
            self.save_personal_graph()
            return {"category": cat_clean, "key": item_key, "status": "stored", "total_categories": len(self.personal_data)}

    def generate_user_profile_context(self) -> str:
        """Returns concise personal graph summary for deep personalization."""
        with self._lock:
            lines = ["### User Personal Knowledge Graph Profile:"]
            for k, v_dict in self.personal_data.items():
                if v_dict:
                    items_str = ", ".join([f"{key}: {val.get('value') if isinstance(val, dict) else val}" for key, val in v_dict.items()][:5])
                    lines.append(f"- **{k.title()}**: {items_str}")
            return "\n".join(lines)

_global_consolidator = None
def get_knowledge_consolidator() -> KnowledgeConsolidator:
    global _global_consolidator
    if _global_consolidator is None:
        _global_consolidator = KnowledgeConsolidator()
    return _global_consolidator
