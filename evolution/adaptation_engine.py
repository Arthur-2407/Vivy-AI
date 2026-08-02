"""
evolution/adaptation_engine.py
==================================
Vivy AI — Evolution Engine: Short-Term Adaptation

Implements online incremental learning, contextual multi-armed bandits,
confidence estimation, and temporary policy snapshots for rapid micro-adjustments.
"""

from __future__ import annotations
import os
import time
import math
import random
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Any, Tuple, Optional
from evolution.perception_layer import Experience, get_perception_layer

@dataclass
class PolicySnapshot:
    snapshot_id: str
    timestamp: float
    weights: Dict[str, float]
    confidence_score: float
    is_active: bool = True

class ContextualBandit:
    """
    LinUCB / Epsilon-Greedy contextual bandit for online policy selection
    (e.g., prompt style, search trigger threshold tuning, context budget allocation).
    """
    def __init__(self, actions: List[str], epsilon: float = 0.1):
        self.actions = actions
        self.epsilon = epsilon
        self.counts = {a: 0 for a in actions}
        self.values = {a: 0.5 for a in actions}  # Initial estimated reward

    def select_action(self, context_vector: List[float]) -> str:
        if random.random() < self.epsilon:
            return random.choice(self.actions)
        # Exploitation: pick highest estimated reward
        best_action = max(self.values.items(), key=lambda x: x[1])[0]
        return best_action

    def update(self, action: str, reward: float):
        if action in self.counts:
            self.counts[action] += 1
            n = self.counts[action]
            # Incremental average update
            self.values[action] += (reward - self.values[action]) / float(n)

class AdaptationEngine:
    """
    Short-Term Adaptation Manager:
    Evaluates experiences and updates temporary policy snapshots.
    """
    def __init__(self, confidence_threshold: float = 0.85):
        self._lock = threading.Lock()
        self._confidence_threshold = confidence_threshold
        self._prompt_bandit = ContextualBandit(["concise", "balanced", "empathic"])
        self._search_bandit = ContextualBandit(["standard_threshold", "aggressive_threshold", "conservative_threshold"])
        self._active_snapshot: Optional[PolicySnapshot] = None
        self._snapshot_history: List[PolicySnapshot] = []

    def evaluate_confidence(self, experiences: List[Experience]) -> float:
        """Calculate statistical confidence based on recent feedback trends."""
        if not experiences:
            return 0.5
        scores = [e.feedback_score for e in experiences[-20:]]
        mean_score = sum(scores) / len(scores)
        variance = sum((x - mean_score) ** 2 for x in scores) / max(1, len(scores))
        std_dev = math.sqrt(variance)
        # Higher mean + lower variance = higher confidence score
        confidence = max(0.0, min(1.0, mean_score * (1.0 - (std_dev * 0.5))))
        return round(confidence, 4)

    def process_adaptation_step(self) -> Optional[PolicySnapshot]:
        """
        Runs one incremental adaptation step over recent experiences.
        Creates a temporary policy snapshot if confidence threshold is met.
        """
        perception = get_perception_layer()
        recent_exps = perception.get_recent_experiences(30)
        if len(recent_exps) < 5:
            return None

        confidence = self.evaluate_confidence(recent_exps)

        with self._lock:
            # Update bandit reward based on latest experience
            last_exp = recent_exps[-1]
            reward = last_exp.feedback_score
            selected_style = self._prompt_bandit.select_action(last_exp.feature_vector)
            self._prompt_bandit.update(selected_style, reward)

            if confidence >= self._confidence_threshold:
                snapshot_id = f"snap_{int(time.time() * 1000)}"
                new_weights = {
                    "prompt_style": selected_style,
                    "search_threshold": self._search_bandit.select_action(last_exp.feature_vector),
                    "context_budget_modifier": 1.1 if reward > 0.8 else 0.9,
                    "rie_min_score": 0.75
                }
                snapshot = PolicySnapshot(
                    snapshot_id=snapshot_id,
                    timestamp=time.time(),
                    weights=new_weights,
                    confidence_score=confidence,
                    is_active=True
                )
                self._active_snapshot = snapshot
                self._snapshot_history.append(snapshot)
                return snapshot

        return None

    def get_active_policy(self) -> Dict[str, Any]:
        with self._lock:
            if self._active_snapshot and self._active_snapshot.is_active:
                return self._active_snapshot.weights
            return {
                "prompt_style": "balanced",
                "search_threshold": "standard_threshold",
                "context_budget_modifier": 1.0,
                "rie_min_score": 0.75
            }

_global_adaptation_engine: Optional[AdaptationEngine] = None
_adaptation_lock = threading.Lock()

def get_adaptation_engine() -> AdaptationEngine:
    global _global_adaptation_engine
    if _global_adaptation_engine is None:
        with _adaptation_lock:
            if _global_adaptation_engine is None:
                _global_adaptation_engine = AdaptationEngine()
    return _global_adaptation_engine
