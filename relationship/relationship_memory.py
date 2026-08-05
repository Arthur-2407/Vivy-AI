"""
relationship/relationship_memory.py
===================================
Manages Weighted Experiential Memories for Vivy AI.
Where traditional factual memory stores static data ("User likes coffee"),
Relationship Memory stores shared human experiences with emotional weights and confidence:
  - "We laughed together today" | Importance: 70 | Emotion: Joy | Confidence: 0.95
  - "First meeting with user"     | Importance: 100 | Emotion: Curiosity | Confidence: 1.0
  - "Shared a deep conversation" | Importance: 85 | Emotion: Warmth | Confidence: 0.92
"""

import time
import threading
from typing import Dict, Any, List, Optional

class RelationshipMemoryManager:
    """Stores, ranks, and retrieves shared conversational experiences by emotional weight."""

    def __init__(self, initial_memories: Optional[List[Dict[str, Any]]] = None):
        self._lock = threading.RLock()
        # Each memory is a dict: {"event": str, "importance": int, "emotion": str, "confidence": float, "timestamp": float}
        self.experiences: List[Dict[str, Any]] = list(initial_memories) if initial_memories else []
        self._ensure_default_milestones()

    def _ensure_default_milestones(self):
        if not any("meet" in m["event"].lower() or "first" in m["event"].lower() for m in self.experiences):
            self.add_experience("Meeting user for our companion journey", importance=100, emotion="Curiosity", confidence=1.0)

    def add_experience(self, event: str, importance: int, emotion: str = "Warmth", confidence: float = 0.95) -> Dict[str, Any]:
        """
        Register a new experiential companion memory with an emotional importance score (0-100) and confidence (0.0-1.0).
        """
        with self._lock:
            # Prevent duplicate event spam by updating confidence/importance if identical
            for mem in self.experiences:
                if mem.get("event", "").strip().lower() == event.strip().lower():
                    mem["importance"] = max(mem["importance"], importance)
                    mem["confidence"] = min(1.0, max(mem.get("confidence", 0.9), confidence))
                    mem["timestamp"] = time.time()
                    return mem

            new_record = {
                "event": event.strip(),
                "importance": int(max(1, min(100, importance))),
                "emotion": str(emotion).capitalize(),
                "confidence": round(float(max(0.05, min(1.0, confidence))), 2),
                "timestamp": time.time()
            }
            self.experiences.append(new_record)
            # Sort descending by importance, then recency
            self.experiences.sort(key=lambda x: (x["importance"], x["timestamp"]), reverse=True)
            if len(self.experiences) > 250:
                self.experiences = self.experiences[:250]
            return new_record

    def retrieve_relevant_experiences(self, current_mood: str = "", limit: int = 4) -> List[Dict[str, Any]]:
        """
        Retrieve highest importance memories, boosting items matching active conversational mood.
        """
        with self._lock:
            if not self.experiences:
                return []
                
            scored = []
            now = time.time()
            for rec in self.experiences:
                base_score = float(rec.get("importance", 50))
                # Boost if emotion matches current dialogue atmosphere
                if current_mood and rec.get("emotion", "").lower() == current_mood.lower():
                    base_score += 15.0
                # Slight recency bonus for recent high-impact moments
                days_ago = (now - rec.get("timestamp", now)) / 86400.0
                recency_mod = max(0.0, 10.0 - min(10.0, days_ago * 0.5))
                scored.append((base_score + recency_mod, rec))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [item[1] for item in scored[:limit]]

    def format_for_prompt(self, limit: int = 3) -> str:
        """Format top weighted experiential memories into clean prompt grounding."""
        with self._lock:
            top = self.retrieve_relevant_experiences(limit=limit)
            if not top:
                return ""
            lines = ["Shared Experiential Memories:"]
            for rec in top:
                lines.append(f"- \"{rec['event']}\" (Importance: {rec['importance']}/100, Emotion: {rec['emotion']}, Conf: {rec['confidence']})")
            return "\n".join(lines)

    def snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.experiences)
