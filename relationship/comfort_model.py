"""
relationship/comfort_model.py
=============================
Evaluates psychological safety and emotional vulnerability comfort during interactions.
Ensures Vivy respects comfort thresholds before attempting banter, deep discussions, or intimacy.
"""

import re
import threading
from typing import Dict, Any, Optional

class ComfortModel:
    """Models emotional security and comfort levels across varied conversation topics."""

    def __init__(self, initial_state: Optional[Dict[str, Any]] = None):
        self._lock = threading.RLock()
        state = initial_state or {}
        self.base_comfort: float = float(state.get("base_comfort", 0.40))
        self.topic_comfort_map: Dict[str, float] = state.get("topic_comfort_map", {})

    def evaluate_topic_comfort(self, topic: str, attachment_comfort: float, is_sensitive: bool = False) -> float:
        """
        Derives real-time conversational comfort for a specific topic, scaled by
        overall attachment comfort and sensitive theme boundaries.
        """
        with self._lock:
            t_clean = topic.strip().lower() if topic else "general"
            stored = self.topic_comfort_map.get(t_clean, self.base_comfort)
            
            # Blend stored topic comfort with active attachment comfort
            effective = (stored * 0.6) + (attachment_comfort * 0.4)
            if is_sensitive and effective < 0.6:
                # Require greater care on sensitive subjects when trust is developing
                effective *= 0.85
            return round(min(1.0, max(0.05, effective)), 3)

    def register_positive_interaction(self, topic: str, increment: float = 0.03) -> None:
        """Increment comfort on a topic following supportive interaction."""
        with self._lock:
            t_clean = topic.strip().lower() if topic else "general"
            current = self.topic_comfort_map.get(t_clean, self.base_comfort)
            self.topic_comfort_map[t_clean] = round(min(1.0, current + increment), 3)
            self.base_comfort = round(min(1.0, self.base_comfort + (increment * 0.2)), 3)

    def is_banter_safe(self, topic: str, attachment_comfort: float) -> bool:
        """Determines if playful humor and teasing are psychologically safe on this topic."""
        with self._lock:
            effective = self.evaluate_topic_comfort(topic, attachment_comfort)
            return effective >= 0.50

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "base_comfort": round(self.base_comfort, 3),
                "topic_comfort_map": dict(self.topic_comfort_map)
            }
