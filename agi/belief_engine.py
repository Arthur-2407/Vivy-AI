"""
Vivy AI — Epistemic Belief Engine
=================================
Replaces flat static memory recall with structured belief evaluation:
  - Belief Proposition & ID
  - Confidence Coefficient (0.0 to 1.0)
  - Evidence Audit Trail (citations & observational sources)
  - Last Updated Timestamp
  - Reliability & Decay Scoring
  - Contradiction Discovery & Revision Loops
"""

import os
import json
import time
import threading
from typing import Dict, List, Optional, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BELIEF_FILE = os.path.join(BASE_DIR, "vivy_beliefs.json")

class BeliefEngine:
    """Thread-safe epistemic belief management and contradiction resolution engine."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls, storage_path: str = BELIEF_FILE) -> "BeliefEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(storage_path)
            return cls._instance

    def __init__(self, storage_path: str = BELIEF_FILE):
        self._lock = threading.RLock()
        self.storage_path = storage_path
        # Dictionary mapping belief_id -> belief struct
        self.beliefs: Dict[str, Dict[str, Any]] = {}
        self.load_from_disk()

    def load_from_disk(self) -> None:
        with self._lock:
            if os.path.exists(self.storage_path):
                try:
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "beliefs" in data:
                        self.beliefs = data["beliefs"]
                    else:
                        self.beliefs = data
                except Exception as _err:
                    print(f"[BeliefEngine] Load error, defaulting to empty: {_err}")
                    self.beliefs = {}

    def save_to_disk(self) -> bool:
        with self._lock:
            try:
                payload = {
                    "last_sync": time.time(),
                    "total_beliefs": len(self.beliefs),
                    "beliefs": self.beliefs
                }
                tmp_path = self.storage_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.storage_path)
                return True
            except Exception as _err:
                print(f"[BeliefEngine] Save error: {_err}")
                return False

    def assert_belief(self, proposition: str, confidence: float = 0.8, evidence: Optional[str] = None, category: str = "general") -> str:
        """
        Registers or updates an epistemic belief. If a contradicting belief exists,
        triggers contradiction marking and confidence calibration.
        Returns the canonical belief ID.
        """
        with self._lock:
            prop_clean = proposition.strip()
            if not prop_clean:
                return ""
                
            # Generate deterministic short ID based on words
            words = [w.lower() for w in prop_clean.split() if len(w) > 2][:5]
            b_id = "_" + "_".join(words) if words else f"b_{int(time.time()*1000)}"
            now = time.time()

            # Check for existing updates
            if b_id in self.beliefs:
                old_conf = self.beliefs[b_id]["confidence"]
                # Bayes-inspired reinforcement: repeated observations increase confidence
                new_conf = round(min(0.99, old_conf + (confidence * 0.15)), 3)
                self.beliefs[b_id]["confidence"] = new_conf
                self.beliefs[b_id]["last_updated"] = now
                if evidence and evidence not in self.beliefs[b_id]["evidence"]:
                    self.beliefs[b_id]["evidence"].append(evidence)
                    self.beliefs[b_id]["evidence"] = self.beliefs[b_id]["evidence"][-6:] # keep last 6 citations
                self.save_to_disk()
                return b_id

            # Discover Contradictions with naive semantic opposition check
            contradictions = []
            prop_lower = prop_clean.lower()
            for ext_id, ext_b in self.beliefs.items():
                ext_prop = ext_b["proposition"].lower()
                # Check for antonym pairs or explicit negation overlap
                if ("not " in prop_lower and prop_lower.replace("not ", "") in ext_prop) or \
                   ("hates " in prop_lower and "likes " in ext_prop and prop_lower.split()[-1] == ext_prop.split()[-1]):
                    contradictions.append(ext_id)
                    # Down-weight older contradictory belief
                    ext_b["confidence"] = round(max(0.05, ext_b["confidence"] - 0.25), 3)
                    if ext_id not in ext_b.get("contradictions", []):
                        ext_b["contradictions"] = ext_b.get("contradictions", []) + [b_id]

            self.beliefs[b_id] = {
                "id": b_id,
                "proposition": prop_clean,
                "confidence": float(max(0.01, min(1.0, confidence))),
                "category": category,
                "evidence": [evidence] if evidence else [],
                "contradictions": contradictions,
                "created": now,
                "last_updated": now,
                "reliability_score": 0.85
            }
            self.save_to_disk()
            return b_id

    def revise_belief(self, b_id: str, new_confidence: float, reason: str = "") -> bool:
        """Explicitly alters confidence of a belief (e.g. after human correction or test)."""
        with self._lock:
            if b_id in self.beliefs:
                self.beliefs[b_id]["confidence"] = round(float(max(0.0, min(1.0, new_confidence))), 3)
                self.beliefs[b_id]["last_updated"] = time.time()
                if reason:
                    self.beliefs[b_id]["evidence"].append(f"Revision: {reason}")
                self.save_to_disk()
                return True
            return False

    def get_high_confidence_beliefs(self, min_confidence: float = 0.6, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns sorted list of reliable beliefs for context grounding."""
        with self._lock:
            res = []
            for b in self.beliefs.values():
                if b["confidence"] >= min_confidence:
                    if category is None or b["category"] == category:
                        res.append(dict(b))
            return sorted(res, key=lambda x: x["confidence"], reverse=True)

    def generate_belief_summary_for_prompt(self) -> str:
        """Produces a compact markdown summary of authoritative active beliefs."""
        with self._lock:
            top_beliefs = self.get_high_confidence_beliefs(min_confidence=0.7)
            if not top_beliefs:
                return ""
            statements = [f"'{b['proposition']}' (conf: {int(b['confidence']*100)}%)" for b in top_beliefs[:5]]
            return "[Core Beliefs & Episteme]: " + "; ".join(statements)

_global_belief_engine = None
def get_belief_engine() -> BeliefEngine:
    global _global_belief_engine
    if _global_belief_engine is None:
        _global_belief_engine = BeliefEngine.get_instance()
    return _global_belief_engine
