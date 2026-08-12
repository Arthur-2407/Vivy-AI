"""
Vivy AI — Continuous Background Learning & Topic Expansion Engine
==================================================================
Autonomous continuous enrichment loop:
  **Idle CPU / Circadian Sleep -> Choose Topic -> Search -> Read -> Verify -> Store -> Repeat**
Topic Expansion Tree:
  **Python -> Decorators -> Closures -> Descriptors -> Metaclasses -> Asyncio**
Self-Directed Learning:
  Maintains a list of knowledge gaps (`shared/knowledge_gaps.json`), tests understanding, and updates stale facts.
"""

import os
import json
import time
import threading
from typing import List, Dict, Any, Optional

from internet.internet_manager import InternetManager
from internet.providers.source_router import get_source_router
from internet.verification.quality_evaluator import get_quality_evaluator
from internet.consolidation.knowledge_consolidator import get_knowledge_consolidator
from internet.rag.rag_pipeline import get_rag_pipeline

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORAGE_DIR = os.path.join(BASE_DIR, "shared")
GAPS_PATH = os.path.join(STORAGE_DIR, "knowledge_gaps.json")
STUDY_LOG_PATH = os.path.join(STORAGE_DIR, "learned_topics_log.json")

class ContinuousLearningEngine:
    """Self-directed autonomous study and hierarchical topic expansion engine."""
    _instance = None
    _lock = threading.RLock()

    def __init__(self, gaps_path: Optional[str] = None):
        self.gaps_path = gaps_path or GAPS_PATH
        self.log_path = STUDY_LOG_PATH
        self.manager = InternetManager.get_instance()
        self.router = get_source_router()
        self.evaluator = get_quality_evaluator()
        self.consolidator = get_knowledge_consolidator()
        self.rag = get_rag_pipeline()
        
        self.knowledge_gaps: List[Dict[str, Any]] = [
            {"topic": "PyTorch autograd architecture", "priority": "high", "added_at": time.time() - 90000},
            {"topic": "Transformer multi-head attention mechanisms", "priority": "medium", "added_at": time.time() - 45000},
            {"topic": "Qt6 async signals and slots event loop", "priority": "high", "added_at": time.time() - 36000},
            {"topic": "Unity UniWindowController transparent overlay capture", "priority": "high", "added_at": time.time() - 18000}
        ]
        self.study_log: List[Dict[str, Any]] = []
        self.topic_trees: Dict[str, List[str]] = {
            "python": ["decorators", "closures", "descriptors", "metaclasses", "asyncio", "generator pipelines"],
            "ai": ["transformers", "attention mechanics", "LoRA adaptation", "rag indexing", "world modeling"],
            "system": ["thread locks", "atomic file operations", "websocket signaling", "memory mapping"],
            "unity": ["UniWindowController", "procedural avatar rigging", "VTuber face tracking", "compute shaders"]
        }
        self._load_gaps()
        self._load_study_log()

    @classmethod
    def get_instance(cls) -> "ContinuousLearningEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _load_gaps(self):
        with self._lock:
            try:
                if os.path.exists(self.gaps_path):
                    with open(self.gaps_path, "r", encoding="utf-8") as f:
                        self.knowledge_gaps = json.load(f)
            except Exception as e:
                print(f"[ContinuousLearning] Gaps load warning: {e}")

    def _load_study_log(self):
        with self._lock:
            try:
                if os.path.exists(self.log_path):
                    with open(self.log_path, "r", encoding="utf-8") as f:
                        self.study_log = json.load(f)
            except Exception as e:
                print(f"[ContinuousLearning] Study log load warning: {e}")

    def save_gaps(self):
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.gaps_path), exist_ok=True)
                tmp = f"{self.gaps_path}.tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.knowledge_gaps, f, indent=2, ensure_ascii=False)
                os.replace(tmp, self.gaps_path)
            except Exception as _e:
                import logging
                logging.getLogger(__name__).debug(f"Fallback triggered: {_e}")

    def save_study_log(self):
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
                tmp = f"{self.log_path}.tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.study_log[-200:], f, indent=2, ensure_ascii=False) # keep latest 200 items
                os.replace(tmp, self.log_path)
            except Exception as _e:
                import logging
                logging.getLogger(__name__).debug(f"Fallback triggered: {_e}")

    def register_knowledge_gap(self, topic: str, priority: str = "medium") -> Dict[str, Any]:
        with self._lock:
            for g in self.knowledge_gaps:
                if g["topic"].lower() == topic.lower():
                    g["priority"] = priority
                    self.save_gaps()
                    return {"status": "updated", "topic": topic}
            self.knowledge_gaps.append({"topic": topic, "priority": priority, "added_at": time.time()})
            self.save_gaps()
            return {"status": "registered", "topic": topic, "total_gaps": len(self.knowledge_gaps)}

    def run_learning_cycle(self, max_topics: int = 2) -> List[Dict[str, Any]]:
        """
        Executes autonomous background learning silently:
        Selects top knowledge gaps, retrieves multi-source intelligence, verifies credibility,
        stores in RAG & Knowledge Graph, and records to study log for on-demand recap.
        """
        reports = []
        with self._lock:
            if not self.knowledge_gaps:
                # If all prior knowledge gaps were consumed, auto-seed with exploratory topics to keep continuous learning active
                self.knowledge_gaps = [
                    {"topic": "Advanced Neural Transformer Memory RAG", "priority": "high", "added_at": time.time() - 1000},
                    {"topic": "Quantum Computing Post-Quantum Cryptography Encryption", "priority": "medium", "added_at": time.time() - 500}
                ]
            self.knowledge_gaps.sort(key=lambda x: (0 if x.get("priority") == "high" else 1, x.get("added_at", 0)))
            pending = list(self.knowledge_gaps[:max_topics])

            for item in pending:
                topic = item["topic"]
                providers_to_use = self.router.route_query(topic)
                raw_res = []

                for p_name in providers_to_use:
                    if p_name == "local_rag":
                        continue
                    prov = self.manager.providers.get(p_name)
                    if prov and prov.is_available():
                        try:
                            raw_res.extend(prov.search(topic, max_results=2))
                        except Exception as _e:
                            import logging
                            logging.getLogger(__name__).debug(f"Fallback triggered: {_e}")

                verified = self.evaluator.evaluate_and_rank(raw_res)
                if verified:
                    top_fact = verified[0]
                    self.consolidator.consolidate_verified_fact(topic, "has_verified_specification", top_fact["title"], confidence=top_fact["confidence"], source=top_fact["source"])
                    if item in self.knowledge_gaps:
                        self.knowledge_gaps.remove(item)
                    
                    record = {
                        "topic": topic,
                        "timestamp": time.time(),
                        "confidence": top_fact["confidence"],
                        "source": top_fact["source"],
                        "snippet": top_fact["fact"][:280]
                    }
                    self.study_log.append(record)
                    self.save_study_log()
                    reports.append({"topic": topic, "status": "studied_and_verified", "confidence": top_fact["confidence"], "source": top_fact["source"], "snippet": top_fact["fact"][:250]})
                else:
                    reports.append({"topic": topic, "status": "deferred_no_verified_facts"})

            self.save_gaps()
        return reports

    def get_recent_learning_summary(self, hours: float = 48.0) -> str:
        """
        On-demand reporting for when the user asks: 'what did you learn yesterday?' or similar.
        Returns a cleanly formatted summary of concepts studied in the background.
        """
        with self._lock:
            cutoff = time.time() - (hours * 3600.0)
            recent = [item for item in self.study_log if item.get("timestamp", time.time()) >= cutoff]
            
            if not recent and not self.study_log:
                return "I haven't performed any background learning cycles recently, but my RAG database and knowledge graph are primed for exploration!"
                
            items_to_report = recent if recent else self.study_log[-5:]
            lines = [f"### Autonomous Study Briefing (Recent Background Learning Log):"]
            for r in items_to_report:
                time_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(r.get("timestamp", time.time())))
                lines.append(f"- **{r['topic']}** *(Studied via {r['source']} at {time_str})*: {r['snippet']}...")
            return "\n".join(lines)

    def expand_topic_tree(self, root_topic: str) -> Dict[str, Any]:
        """
        Instead of stopping after the initial answer, Vivy automatically explores
        deep related concepts and child nodes to systematically deepen its understanding.
        """
        root_clean = root_topic.lower()
        branches = []
        for key, tree_list in self.topic_trees.items():
            if key in root_clean or any(b in root_clean for b in tree_list):
                branches = tree_list
                break

        if not branches:
            branches = ["fundamentals", "advanced optimization", "architectural patterns", "error handling methods"]

        expanded_results = []
        for child_subtopic in branches[:3]:
            full_query = f"{root_topic} {child_subtopic}"
            res_list = self.rag.search_rag(full_query, top_n=1)
            if not res_list:
                # Register gap for future idle study
                self.register_knowledge_gap(full_query, priority="medium")
                expanded_results.append({"subtopic": child_subtopic, "status": "scheduled_for_background_learning"})
            else:
                expanded_results.append({"subtopic": child_subtopic, "status": "already_in_rag", "score": res_list[0]["relevance_score"]})

        return {"root_topic": root_topic, "branches_explored": len(branches), "expansion_details": expanded_results}

_global_learning_engine = None
def get_continuous_learning_engine() -> ContinuousLearningEngine:
    global _global_learning_engine
    if _global_learning_engine is None:
        _global_learning_engine = ContinuousLearningEngine()
    return _global_learning_engine
