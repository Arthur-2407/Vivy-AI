"""
relationship/attachment_engine.py
=================================
Implements psychological Attachment Theory modeling for Vivy AI.
Governs the continuous, dynamic evolution of core attachment variables:
  - Safety (0.0 - 1.0)
  - Reliability (0.0 - 1.0)
  - Comfort (0.0 - 1.0)
  - Trust (0.0 - 1.0)
  - Respect (0.0 - 1.0)
  - Closeness (0.0 - 1.0)
  - Emotional Security (0.0 - 1.0)
"""

import time
import threading
from typing import Dict, Any, Optional

class AttachmentEngine:
    """Manages long-term companion attachment variables that grow over interaction history."""
    
    def __init__(self, initial_state: Optional[Dict[str, Any]] = None):
        self._lock = threading.RLock()
        state = initial_state or {}
        self.safety: float = float(state.get("safety", 0.40))
        self.reliability: float = float(state.get("reliability", 0.35))
        self.comfort: float = float(state.get("comfort", 0.35))
        self.trust: float = float(state.get("trust", 0.30))
        self.respect: float = float(state.get("respect", 0.50))
        self.closeness: float = float(state.get("closeness", 0.20))
        self.emotional_security: float = float(state.get("emotional_security", 0.30))
        self.last_updated: float = float(state.get("last_updated", time.time()))

    def update_attachment(
        self,
        interaction_quality: float,
        is_consistent: bool = True,
        vulnerability_expressed: bool = False,
        conflict_resolved: bool = False,
        days_active: int = 1
    ) -> Dict[str, float]:
        """
        Evolves attachment dimensions based on interaction quality (0.0 to 1.0), consistency,
        vulnerability sharing, and long-term conversation frequency without sudden jumps.
        """
        with self._lock:
            delta = (interaction_quality - 0.5) * 0.02
            
            # Reliability increases with consistency over repeated days
            if is_consistent:
                self.reliability = min(1.0, self.reliability + 0.01 + (days_active * 0.001))
                
            # Safety and Emotional Security strengthen dramatically when vulnerability is welcomed or conflict resolved
            if vulnerability_expressed:
                self.safety = min(1.0, self.safety + 0.03)
                self.comfort = min(1.0, self.comfort + 0.025)
            if conflict_resolved:
                self.emotional_security = min(1.0, self.emotional_security + 0.04)
                self.trust = min(1.0, self.trust + 0.035)

            # Continuous incremental maturation
            self.trust = min(1.0, max(0.05, self.trust + delta + (0.1 * (self.reliability - self.trust))))
            self.comfort = min(1.0, max(0.05, self.comfort + delta + (0.05 * (self.safety - self.comfort))))
            self.respect = min(1.0, max(0.20, self.respect + (delta * 0.5)))
            self.closeness = min(1.0, max(0.05, self.closeness + delta + (0.08 * (self.trust - self.closeness))))
            self.emotional_security = min(1.0, max(0.05, self.emotional_security + delta + (0.1 * (self.safety - self.emotional_security))))
            self.last_updated = time.time()
            
            return self.snapshot()

    def snapshot(self) -> Dict[str, Any]:
        """Return clean dictionary representation of attachment metrics."""
        with self._lock:
            return {
                "safety": round(self.safety, 3),
                "reliability": round(self.reliability, 3),
                "comfort": round(self.comfort, 3),
                "trust": round(self.trust, 3),
                "respect": round(self.respect, 3),
                "closeness": round(self.closeness, 3),
                "emotional_security": round(self.emotional_security, 3),
                "composite_attachment_level": round(self.get_composite_attachment(), 3),
                "last_updated": self.last_updated
            }

    def get_composite_attachment(self) -> float:
        """Calculate weighted composite attachment score (0.0 - 1.0)."""
        with self._lock:
            weights = [self.trust * 0.25, self.safety * 0.20, self.comfort * 0.15,
                       self.reliability * 0.15, self.emotional_security * 0.15, self.closeness * 0.10]
            return sum(weights)

    def generate_prompt_guidance(self) -> str:
        """Produce natural companion prompt advice based on matured attachment metrics."""
        with self._lock:
            comp = self.get_composite_attachment()
            if comp >= 0.80:
                return "Attachment Level: Deeply Secure & Bonded. Be completely open, conversational, empathetic, and warmly familiar."
            elif comp >= 0.55:
                return "Attachment Level: Trusted & Comfortable. Engage with comfortable warmth, playful ease, and supportive reliability."
            elif comp >= 0.35:
                return "Attachment Level: Developing Comfort. Maintain polite friendliness, encouraging rapport, and warm engagement."
            else:
                return "Attachment Level: New Connection. Be respectful, gentle, welcoming, and curious to build psychological safety."
