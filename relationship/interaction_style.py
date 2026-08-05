"""
relationship/interaction_style.py
=================================
Manages the Self-Adaptation of conversational habits and communication tones over time.
Instead of abruptly changing personality or relying on static switches, traits adapt gradually:
  - Day 1: Humor at 0.20 -> After 100 conversations with joke engagement -> Humor at 0.62.
"""

import threading
from typing import Dict, Any, Optional

class InteractionStyleAdaptor:
    """Adapts conversational traits gradually based on user affinity and engagement patterns."""

    def __init__(self, initial_style: Optional[Dict[str, float]] = None):
        self._lock = threading.RLock()
        style = initial_style or {}
        self.humor: float = float(style.get("humor", 0.25))
        self.empathy: float = float(style.get("empathy", 0.70))
        self.playfulness: float = float(style.get("playfulness", 0.30))
        self.vocabulary_level: float = float(style.get("vocabulary_level", 0.50))
        self.pacing: str = str(style.get("pacing", "balanced"))
        self.interactions_observed: int = int(style.get("interactions_observed", 0))

    def assimilate_turn_engagement(
        self,
        user_text: str,
        user_smiled_or_laughed: bool = False,
        is_serious_or_sad: bool = False,
        uses_advanced_words: bool = False
    ) -> Dict[str, Any]:
        """
        Gradually shifts conversational communication parameters based on observed user cues and reactions.
        """
        with self._lock:
            self.interactions_observed += 1
            u_clean = user_text.lower() if user_text else ""
            
            # Humor and playfulness adaptation (gradual assimilation over dozens of turns)
            if user_smiled_or_laughed or any(w in u_clean for w in ["haha", "lol", "hehe", "joke", "funny"]):
                self.humor = round(min(1.0, self.humor + 0.015), 3)
                self.playfulness = round(min(1.0, self.playfulness + 0.012), 3)
            elif is_serious_or_sad:
                self.empathy = round(min(1.0, self.empathy + 0.015), 3)
                # Temporarily modulate pacing for supportive solidarity
                self.pacing = "gentle and patient"

            if uses_advanced_words or len(user_text.split()) > 25:
                self.vocabulary_level = round(min(1.0, self.vocabulary_level + 0.005), 3)

            return self.snapshot()

    def set_humor(self, value: float) -> None:
        with self._lock:
            self.humor = round(min(1.0, max(0.0, value)), 3)

    def generate_style_guidance(self) -> str:
        with self._lock:
            humor_desc = "high, effortless companion humor" if self.humor >= 0.55 else "subtle, warm conversational cheer" if self.humor >= 0.3 else "gentle polite warmth"
            emp_desc = "deep emotional attunement and compassionate empathy" if self.empathy >= 0.65 else "attentive listening"
            return f"Conversational Style: Use {humor_desc} with {emp_desc}. Pacing: {self.pacing}."

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "humor": self.humor,
                "empathy": self.empathy,
                "playfulness": self.playfulness,
                "vocabulary_level": self.vocabulary_level,
                "pacing": self.pacing,
                "interactions_observed": self.interactions_observed
            }
