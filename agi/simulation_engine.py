"""
Vivy AI — Internal Simulation Engine
====================================
Pre-action mental sandbox executing counterfactual conversational modeling:
  Plan A -> Simulate against User Persona Model -> Score
  Plan B -> Simulate against User Persona Model -> Score
  Choose Best Strategy before executing physical output.
"""

import time
import threading
from typing import Dict, List, Tuple, Any
from agi.world_model import get_world_model

class SimulationEngine:
    """Thread-safe counterfactual action simulation and decision scoring engine."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "SimulationEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._lock = threading.RLock()
        self.simulation_count = 0
        self.simulated_outcomes = []

    def simulate_and_select_plan(self, user_text: str, plan_a: dict, plan_b: dict, mem: dict) -> Tuple[dict, str, Dict[str, float]]:
        """
        Simulates two competing conversational plans against the stored User Persona model.
        Returns the optimal plan, winning strategy name, and simulation evaluation scores.
        """
        with self._lock:
            self.simulation_count += 1
            t_start = time.time()
            
            score_a = self._simulate_outcome(user_text, plan_a, mem)
            score_b = self._simulate_outcome(user_text, plan_b, mem)
            
            winner_plan = plan_a if score_a >= score_b else plan_b
            winner_label = "Plan A (Empathy/Relational Primary)" if score_a >= score_b else "Plan B (Analytical/Brisk Primary)"
            
            latency_ms = round((time.time() - t_start) * 1000.0, 2)
            self.simulated_outcomes.append({
                "timestamp": time.time(),
                "winner": winner_label,
                "score_a": score_a,
                "score_b": score_b,
                "latency_ms": latency_ms
            })
            if len(self.simulated_outcomes) > 30:
                self.simulated_outcomes = self.simulated_outcomes[-30:]
                
            return winner_plan, winner_label, {"score_a": score_a, "score_b": score_b}

    def _simulate_outcome(self, user_text: str, candidate_plan: dict, mem: dict) -> float:
        """Heuristic calculation simulating user relational alignment and cognitive utility."""
        score = 0.5
        user_lower = user_text.lower()
        tone = str(candidate_plan.get("tone", "")).lower()
        stage = str(candidate_plan.get("relationship_stage", "")).lower()
        
        # Reward empathetic tone when user displays stress or pain
        if any(w in user_lower for w in ["sick", "tired", "error", "failed", "stressed", "help"]):
            if "warm" in tone or "empath" in tone or "gentle" in tone:
                score += 0.35
            elif "brisk" in tone or "teasing" in tone or "playful" in tone:
                score -= 0.25
                
        # Reward analytical rigor on technical questions
        if any(w in user_lower for w in ["code", "function", "bug", "compile", "unity", "python"]):
            if "analytical" in tone or "focus" in tone or "clear" in tone:
                score += 0.30

        # Adjust for relationship bonding depth
        if "bonded" in stage or "trusted" in stage or "close" in stage:
            score += 0.15

        return round(float(max(0.01, min(1.0, score))), 3)

    def get_simulation_summary(self) -> str:
        with self._lock:
            if not self.simulated_outcomes:
                return ""
            last_o = self.simulated_outcomes[-1]
            return f"[Mental Simulation]: Selected {last_o['winner']} (Confidence Score: {max(last_o['score_a'], last_o['score_b']):.2f})"

_global_simulation_engine = None
def get_simulation_engine() -> SimulationEngine:
    global _global_simulation_engine
    if _global_simulation_engine is None:
        _global_simulation_engine = SimulationEngine.get_instance()
    return _global_simulation_engine
