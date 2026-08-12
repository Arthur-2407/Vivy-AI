"""
neural/neural_orchestrator.py
==============================
Coordinates the Neural Learning Fabric (Level 8).
Connects Perception, Cognition, and the EventBus to the Neural Experience Store.
"""

from agi.bus.event_bus import get_event_bus
from neural.prediction_engine import get_prediction_engine
from neural.reward_engine import get_reward_engine
from neural.experience_store import get_experience_store
from neural.novelty_detector import get_novelty_detector

class NeuralOrchestrator:
    def __init__(self):
        self.active = True
        self.prediction_engine = get_prediction_engine()
        self.reward_engine = get_reward_engine()
        self.experience_store = get_experience_store()
        self.novelty_detector = get_novelty_detector()
        
        bus = get_event_bus()
        bus.subscribe("COGNITION_OUTCOME", self.process_outcome)
        bus.subscribe("USER_FEEDBACK", self.process_feedback)

    def process_outcome(self, event):
        if not self.active: return
        payload = event.get("payload", {})
        
        context_id = payload.get("id", "")
        # Get actual outcome metrics
        actual_outcomes = {
            "task_success": payload.get("task_success", 0.0),
            "efficiency": payload.get("efficiency", 0.0)
        }
        
        # Calculate prediction error
        error = self.prediction_engine.evaluate_outcome(context_id, actual_outcomes)
        
        # In a full run, we would record the complete experience here.
        # But we also rely on USER_FEEDBACK for the final reward calculation.
        
        get_event_bus().publish("LEARNING_SIGNAL", {"error": error, "context_id": context_id})

    def process_feedback(self, event):
        if not self.active: return
        payload = event.get("payload", {})
        
        reward = self.reward_engine.compute_reward(
            task_success=payload.get("task_success", 0.0),
            user_feedback=payload.get("score", 0.0),
            emotional_outcome=payload.get("emotional_outcome", 0.0),
            factual_accuracy=payload.get("factual_accuracy", 0.0),
            efficiency=payload.get("efficiency", 0.0),
            relationship_consistency=payload.get("relationship_consistency", 0.0)
        )
        
        # Calculate Novelty Priority
        priority = self.novelty_detector.calculate_priority(
            novelty=payload.get("novelty", 0.5),
            surprise=payload.get("surprise", 0.5),
            importance=payload.get("importance", 0.5),
            outcome_delta=abs(reward),
            recurrence=payload.get("recurrence", 1.0)
        )
        
        # Store the Experience
        exp_id = self.experience_store.record_experience(
            user_state=payload.get("user_state", {}),
            emotion_state=payload.get("emotion_state", {}),
            perception_state=payload.get("perception_state", {}),
            goal=payload.get("goal", ""),
            action=payload.get("action", ""),
            tool_usage=payload.get("tool_usage", []),
            response_strategy=payload.get("response_strategy", ""),
            prediction=payload.get("prediction", {}),
            outcome=payload.get("outcome", {}),
            reward=reward,
            confidence=payload.get("confidence", 0.8),
            novelty=payload.get("novelty", 0.5),
            learning_value=priority
        )
        
        get_event_bus().publish("LEARNING_REWARD", {"reward": reward, "experience_id": exp_id, "priority": priority})

_orchestrator_instance = None
def get_neural_orchestrator():
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = NeuralOrchestrator()
    return _orchestrator_instance
