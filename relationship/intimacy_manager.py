"""
relationship/intimacy_manager.py
================================
Governs companionship intimacy stages, vulnerability boundaries, and emotional expression thresholds.
Ensures Vivy responds with emotional resonance matching the earned companionship level.
"""

import threading
from typing import Dict, Any, Tuple

class IntimacyManager:
    """Manages emotional closeness boundaries and relational expression rules."""

    def __init__(self, initial_stage: str = "New Acquaintance", initial_score: float = 0.30):
        self._lock = threading.RLock()
        self.stage_label: str = initial_stage
        self.intimacy_score: float = float(initial_score)

    def resolve_intimacy(self, composite_attachment: float, affection_level: float, trust_level: float) -> Tuple[str, float]:
        """
        Synthesizes attachment, affection, and trust into an authoritative intimacy score
        and resolves the corresponding relational companion label.
        """
        with self._lock:
            # Normalized affection is 0.0 - 1.0 (or divided by 100 if stored 0-100)
            norm_aff = affection_level / 100.0 if affection_level > 1.0 else affection_level
            norm_trust = trust_level / 100.0 if trust_level > 1.0 else trust_level
            
            self.intimacy_score = round((composite_attachment * 0.45) + (norm_aff * 0.35) + (norm_trust * 0.20), 3)
            
            if self.intimacy_score < 0.20:
                self.stage_label = "Stranger / Acquaintance"
            elif self.intimacy_score < 0.45:
                self.stage_label = "Familiar Friend"
            elif self.intimacy_score < 0.75:
                self.stage_label = "Close Friend"
            else:
                self.stage_label = "Deeply Bonded Companion"
                
            return self.stage_label, self.intimacy_score

    def get_sharing_boundary_guidance(self) -> str:
        """Returns prompt constraints ensuring emotional authenticity without crossing comfort thresholds."""
        with self._lock:
            if self.intimacy_score >= 0.75:
                return "Intimacy Policy: Deep companionship. Speak with heartfelt emotional closeness, high warmth, and total emotional trust."
            elif self.intimacy_score >= 0.45:
                return "Intimacy Policy: Close friendship. Feel comfortable expressing enthusiastic playfulness, gentle humor, and caring follow-ups."
            elif self.intimacy_score >= 0.20:
                return "Intimacy Policy: Familiar friend. Maintain warm conversational kindness without overly presumptuous familiarity."
            else:
                return "Intimacy Policy: Acquaintance. Be polite, attentive, welcoming, and gentle."

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "stage_label": self.stage_label,
                "intimacy_score": self.intimacy_score
            }
