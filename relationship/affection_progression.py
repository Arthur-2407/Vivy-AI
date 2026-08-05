"""
relationship/affection_progression.py
=====================================
Implements the Non-Linear Affection Progression Model for Vivy AI.
Replaces simplisitic "+1 affection per compliment" mechanisms with an interdependent
system where:
   Trust -> Comfort -> Shared Experiences -> Reliability -> Affection
Everything influences everything dynamically.
"""

import math
import threading
from typing import Dict, Any, Optional

class AffectionProgressionEngine:
    """Calculates non-linear emotional affection dynamics across companionship dimensions."""

    def __init__(self, initial_affection: float = 0.45):
        self._lock = threading.RLock()
        # Normalized between 0.0 and 1.0 (or scaled 0-100 for compatibility)
        self.current_affection: float = float(initial_affection if initial_affection <= 1.0 else initial_affection / 100.0)
        self.momentum: float = 0.0

    def calculate_progression(
        self,
        trust: float,
        comfort: float,
        reliability: float,
        shared_experiences_count: int,
        interaction_valance: float = 0.5
    ) -> float:
        """
        Derives non-linear affection growth based on the synergistic product of trust, comfort,
        reliability, and logarithmic growth from shared experiential memories.
        """
        with self._lock:
            # Normalize inputs if delivered in 0-100 scale
            n_trust = trust / 100.0 if trust > 1.0 else max(0.01, min(1.0, trust))
            n_comfort = comfort / 100.0 if comfort > 1.0 else max(0.01, min(1.0, comfort))
            n_reliability = reliability / 100.0 if reliability > 1.0 else max(0.01, min(1.0, reliability))
            
            # Shared experience saturation function (logarithmic curve preventing runaway farming)
            exp_factor = max(0.1, min(1.0, math.log1p(max(1, shared_experiences_count)) / math.log1p(100)))

            # Synergistic interaction core: affection matures fastest when trust, comfort, and reliability converge
            synergy = (n_trust * 0.35) + (n_comfort * 0.25) + (n_reliability * 0.20) + (exp_factor * 0.20)
            
            # Non-linear delta modulation
            valance_delta = (interaction_valance - 0.5) * 0.03
            target_affection = min(1.0, max(0.05, (synergy * 0.9) + (self.current_affection * 0.1) + valance_delta))

            # Apply momentum to prevent abrupt personality mood swings
            delta = target_affection - self.current_affection
            self.momentum = (self.momentum * 0.7) + (delta * 0.3)
            self.current_affection = round(min(1.0, max(0.05, self.current_affection + self.momentum)), 3)

            return self.current_affection

    def get_affection_level_100(self) -> float:
        """Return compatibility score on 0-100 scale."""
        with self._lock:
            return round(self.current_affection * 100.0, 1)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "affection_normalized": self.current_affection,
                "affection_level": self.get_affection_level_100(),
                "momentum": round(self.momentum, 4)
            }
