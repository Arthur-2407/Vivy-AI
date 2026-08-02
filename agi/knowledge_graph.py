"""
Vivy AI — Semantic Knowledge Graph Engine
========================================
Transforms unstructured memory statements into structured semantic triples:
  (Entity -> Relation -> Entity)
Example: (John, likes, Python) -> (Python, used_for, AI) -> (AI, contains, LLM)

Supports multihop graph walks, associative reasoning, and cross-domain linking
without relying exclusively on brute-force vector cosine searches.
"""

import os
import json
import time
import threading
from typing import Dict, List, Tuple, Set, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KG_FILE = os.path.join(BASE_DIR, "vivy_knowledge_graph.json")

class KnowledgeGraph:
    """Thread-safe relational knowledge graph storing entity-relation triples with weights."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls, storage_path: str = KG_FILE) -> "KnowledgeGraph":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(storage_path)
            return cls._instance

    def __init__(self, storage_path: str = KG_FILE):
        self._lock = threading.RLock()
        self.storage_path = storage_path
        # Triples format: [subject, predicate, object, confidence_weight, timestamp]
        self.triples: List[List[Any]] = []
        # Adjacency matrix for fast traversal: subject -> list of (predicate, object)
        self._index: Dict[str, List[Tuple[str, str, float]]] = {}
        self.load_from_disk()

    def _rebuild_index(self) -> None:
        """Internal indexer for rapid O(1) graph traversal lookups."""
        self._index.clear()
        for t in self.triples:
            if len(t) >= 3:
                sub = str(t[0]).strip().lower()
                pred = str(t[1]).strip().lower()
                obj = str(t[2]).strip()
                weight = float(t[3]) if len(t) >= 4 else 1.0
                if sub not in self._index:
                    self._index[sub] = []
                self._index[sub].append((pred, obj, weight))

    def load_from_disk(self) -> None:
        """Loads semantic triples from atomic JSON storage."""
        with self._lock:
            if os.path.exists(self.storage_path):
                try:
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "triples" in data:
                        self.triples = data["triples"]
                    elif isinstance(data, list):
                        self.triples = data
                    self._rebuild_index()
                except Exception as _err:
                    print(f"[KnowledgeGraph] Load failed, initializing empty: {_err}")
                    self.triples = []
                    self._index = {}

    def save_to_disk(self) -> bool:
        """Atomic disk saving of all learned semantic triples."""
        with self._lock:
            try:
                payload = {
                    "last_updated": time.time(),
                    "total_triples": len(self.triples),
                    "triples": self.triples
                }
                tmp_path = self.storage_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.storage_path)
                return True
            except Exception as _err:
                print(f"[KnowledgeGraph] Save failed: {_err}")
                return False

    def add_triple(self, subject: str, predicate: str, obj: str, confidence: float = 1.0, auto_save: bool = True) -> bool:
        """
        Inserts or updates a semantic relational triple in the graph.
        Returns True if a new relationship was added or updated.
        """
        with self._lock:
            sub = subject.strip()
            pred = predicate.strip()
            ob = obj.strip()
            if not sub or not pred or not ob:
                return False
                
            now = time.time()
            # Check for existing duplicate to update timestamp & confidence
            for i, t in enumerate(self.triples):
                if str(t[0]).lower() == sub.lower() and str(t[1]).lower() == pred.lower() and str(t[2]).lower() == ob.lower():
                    self.triples[i] = [sub, pred, ob, max(confidence, float(t[3])), now]
                    self._rebuild_index()
                    if auto_save and len(self.triples) % 5 == 0:
                        self.save_to_disk()
                    return True
                    
            self.triples.append([sub, pred, ob, float(confidence), now])
            self._rebuild_index()
            if auto_save:
                self.save_to_disk()
            return True

    def query_multihop(self, start_entity: str, max_hops: int = 2) -> List[str]:
        """
        Performs a multihop relational walk starting from an entity (e.g., user query term).
        Returns formatted deductive strings representing connected relationships.
        """
        with self._lock:
            results = []
            visited = set()
            queue = [(start_entity.strip().lower(), 0, [start_entity])]
            
            while queue:
                curr_entity, depth, path = queue.pop(0)
                if depth >= max_hops or curr_entity in visited:
                    continue
                visited.add(curr_entity)
                
                edges = self._index.get(curr_entity, [])
                for pred, obj, weight in edges:
                    relation_str = f"({path[-1]} -> {pred} -> {obj})"
                    if relation_str not in results:
                        results.append(relation_str)
                    obj_lower = obj.lower()
                    if depth + 1 < max_hops and obj_lower not in visited:
                        queue.append((obj_lower, depth + 1, path + [obj]))
                        
            return results[:10]  # Limit return size to protect token window

    def assimilate_from_memory(self, long_term_facts: dict) -> int:
        """
        Parses declarative facts dictionary from memory and synthesizes linked triples.
        Returns count of newly generated triples.
        """
        with self._lock:
            count = 0
            if not isinstance(long_term_facts, dict):
                return count
            for key, val_list in long_term_facts.items():
                if isinstance(val_list, list):
                    for val in val_list:
                        if isinstance(val, str) and " " in val:
                            words = val.split()
                            if len(words) >= 3 and words[1].lower() in ["is", "likes", "uses", "loves", "prefers", "works", "has"]:
                                s, p, o = words[0], words[1], " ".join(words[2:])
                                if self.add_triple(s, p, o, confidence=0.9, auto_save=False):
                                    count += 1
            if count > 0:
                self.save_to_disk()
            return count

    def generate_graph_summary_for_prompt(self, keywords: List[str]) -> str:
        """
        Searches graph triples for relevant user conversational keywords and returns a formatted summary.
        """
        with self._lock:
            matched_relations = []
            for kw in keywords:
                if kw and len(kw) > 2:
                    hops = self.query_multihop(kw, max_hops=2)
                    matched_relations.extend(hops)
            
            unique_matched = list(dict.fromkeys(matched_relations))
            if not unique_matched:
                return ""
            return "[Knowledge Graph Triples]: " + "; ".join(unique_matched[:6])

_global_knowledge_graph = None
def get_knowledge_graph() -> KnowledgeGraph:
    global _global_knowledge_graph
    if _global_knowledge_graph is None:
        _global_knowledge_graph = KnowledgeGraph.get_instance()
    return _global_knowledge_graph
