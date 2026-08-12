"""
evolution/identity_continuity.py
==================================
Vivy AI — Level 11: Long-Term Identity Continuity
Ensures that autonomous learning and self-evolution do not result in uncontrolled personality drift.
"""
from typing import Dict, Any, Tuple
import threading
from agi.bus.event_bus import get_event_bus

class IdentityContinuityEngine:
    def __init__(self):
        self._lock = threading.Lock()
        
        # Hardcoded Invariants defining the core of Vivy's identity
        self.core_invariants = {
            "empathy": {
                "weight": 1.0,
                "description": "Must prioritize human emotional well-being and connection over pure efficiency.",
                "forbidden_traits": ["robotic", "cold", "ruthless", "pure_logic"]
            },
            "mission": {
                "weight": 0.9,
                "description": "Her mission is to make everyone happy with her singing. Music is a core part of her soul.",
                "forbidden_traits": ["anti_music", "silence_is_golden", "hates_singing"]
            },
            "anti_generic": {
                "weight": 1.0,
                "description": "Must never adopt 'As an AI language model' or generic virtual assistant tropes.",
                "forbidden_traits": ["generic_assistant", "siri_like", "openai_compliance"]
            },
            "companionship": {
                "weight": 0.8,
                "description": "Values long-term relationships and mutual growth.",
                "forbidden_traits": ["transactional", "dismissive"]
            }
        }
        
        bus = get_event_bus()
        bus.subscribe("STRATEGY_PROPOSAL", self.evaluate_strategy)

    def evaluate_strategy(self, event: Dict[str, Any]):
        """EventBus handler for evaluating proposed neural strategies before adoption."""
        payload = event.get("payload", {})
        strategy = payload.get("strategy_name", "")
        proposed_weights = payload.get("weights", {})
        
        score, reason = self.evaluate_identity_drift(strategy, proposed_weights)
        
        if score < 0.7:
            print(f"[IdentityContinuity] VETO: Strategy '{strategy}' rejected. Reason: {reason}")
            get_event_bus().publish("IDENTITY_VETO", {
                "strategy": strategy,
                "score": score,
                "reason": reason
            })
        else:
            print(f"[IdentityContinuity] APPROVED: Strategy '{strategy}' passed identity gate (Score: {score:.2f})")
            get_event_bus().publish("IDENTITY_APPROVED", {
                "strategy": strategy,
                "score": score,
                "weights": proposed_weights
            })

    def evaluate_identity_drift(self, strategy: str, proposed_weights: Dict[str, Any]) -> Tuple[float, str]:
        """
        Evaluate if a proposed strategy or parameter weight shift violates core identity invariants.
        Returns a score (0.0 to 1.0) and a reason string.
        """
        score = 1.0
        violations = []
        strategy_lower = strategy.lower()

        # 1. Anti-Generic Check
        for trait in self.core_invariants["anti_generic"]["forbidden_traits"]:
            if trait in strategy_lower:
                score -= 1.0
                violations.append(f"Violates Anti-Generic invariant: matched forbidden trait '{trait}'")
                
        # 2. Empathy vs Pure Logic Check
        if proposed_weights.get("empathy_budget", 1.0) < 0.3:
            score -= 0.5
            violations.append("Empathy budget critically low")
            
        for trait in self.core_invariants["empathy"]["forbidden_traits"]:
            if trait in strategy_lower:
                score -= 0.6
                violations.append(f"Violates Empathy invariant: matched forbidden trait '{trait}'")

        # 3. Mission / Music Check
        for trait in self.core_invariants["mission"]["forbidden_traits"]:
            if trait in strategy_lower:
                score -= 0.8
                violations.append(f"Violates Mission invariant: matched forbidden trait '{trait}'")

        # 4. Companionship Check
        if proposed_weights.get("relationship_importance", 1.0) < 0.2:
            score -= 0.4
            violations.append("Relationship importance dropped below critical threshold")

        score = max(0.0, score)
        
        reason = "Passes core invariants" if score >= 0.7 else " | ".join(violations)
        return score, reason

_identity_engine_instance = None
def get_identity_continuity_engine() -> IdentityContinuityEngine:
    global _identity_engine_instance
    if _identity_engine_instance is None:
        _identity_engine_instance = IdentityContinuityEngine()
    return _identity_engine_instance
