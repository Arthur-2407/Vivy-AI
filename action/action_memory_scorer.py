"""
Vivy AI — Action Memory Scorer
==============================
Filters and scores action results before they enter long-term memory.
Prevents the Evolution Engine from being poisoned by high-volume, low-value
repetitive tasks, ensuring it only learns from significant experiences.

Spec Reference: § Memory Filtering & Evolution Pipeline
"""
import time
from typing import Dict, Any, Tuple
from action.intent_model import IntentModel, ActionResult

class ActionMemoryScorer:
    """Evaluates action significance for memory and self-evolution."""
    
    def __init__(self):
        # Ephemeral history to calculate repetition penalties (in-memory tracking)
        self._recent_actions = [] 

    def score_action(self, intent: IntentModel, result: ActionResult, session: Any) -> Tuple[float, str]:
        """
        Calculates the evolutionary value of an action outcome.
        Returns: (score, category)
        category can be: "telemetry", "aggregate", "memory"
        """
        score = 0.0
        
        # 1. Failure Recovery Value (High learning value)
        if result.success and getattr(result, "recovery_attempted", False):
            score += 0.4
        elif not result.success:
            # Failures are valuable to learn what doesn't work
            score += 0.3

        # 2. Novelty & Task Importance
        # Multi-step tasks or high-risk tasks are inherently more important
        if intent.risk_level in ["HIGH_RISK", "MEDIUM_RISK"]:
            score += 0.3
            
        # 3. User Preference Signal
        # Actions with constraints (e.g. specific filters) show preference
        if intent.constraints:
            score += 0.2

        # 4. Repetition Penalty
        # Check recent actions to penalize repetitive tasks (e.g. volume adjustments)
        repetition_count = self._calculate_repetition(intent)
        if repetition_count > 0:
            penalty = min(0.5, repetition_count * 0.1)
            score -= penalty
            
        # Inherently low-value routine intents get an immediate penalty
        if intent.domain == "device" and intent.action == "adjust":
            score -= 0.3
            
        # Boost novelty if it's the first time doing this action ever
        if repetition_count == 0:
            score += 0.2
            
        # Ensure bounds
        score = max(0.0, min(1.0, score))
        
        # Determine Routing Category
        if score >= 0.7:
            category = "memory"
        elif score >= 0.4:
            category = "aggregate"
        else:
            category = "telemetry"
            
        # Update ephemeral history
        self._record_recent(intent)
        
        return score, category

    def _calculate_repetition(self, intent: IntentModel) -> int:
        """Count how many times this specific action+target was executed recently."""
        count = 0
        now = time.time()
        # Clean old history (e.g., older than 1 hour)
        self._recent_actions = [a for a in self._recent_actions if now - a["ts"] < 3600]
        
        for act in self._recent_actions:
            if act["domain"] == intent.domain and act["action"] == intent.action and act["target"] == intent.target:
                count += 1
        return count

    def _record_recent(self, intent: IntentModel):
        self._recent_actions.append({
            "domain": intent.domain,
            "action": intent.action,
            "target": intent.target,
            "ts": time.time()
        })
        
        # Keep list bounded
        if len(self._recent_actions) > 100:
            self._recent_actions.pop(0)


_global_scorer = None
def get_action_scorer() -> ActionMemoryScorer:
    global _global_scorer
    if _global_scorer is None:
        _global_scorer = ActionMemoryScorer()
    return _global_scorer
