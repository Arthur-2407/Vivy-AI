"""
neural/reward_engine.py
==============================
Computes intrinsic and extrinsic rewards based on user interaction and goal satisfaction.
"""

class RewardEngine:
    def __init__(self):
        self.weights = {
            "task_success": 0.3,
            "user_feedback": 0.3,
            "emotional_outcome": 0.15,
            "factual_accuracy": 0.1,
            "efficiency": 0.05,
            "relationship_consistency": 0.1
        }

    def compute_reward(self, 
                       task_success: float = 0.0, 
                       user_feedback: float = 0.0, 
                       emotional_outcome: float = 0.0,
                       factual_accuracy: float = 0.0,
                       efficiency: float = 0.0,
                       relationship_consistency: float = 0.0) -> float:
        """
        Combines multiple outcome signals to generate a scalar reward signal.
        All inputs should ideally be normalized to [-1.0, 1.0].
        """
        reward = (
            (task_success * self.weights["task_success"]) +
            (user_feedback * self.weights["user_feedback"]) +
            (emotional_outcome * self.weights["emotional_outcome"]) +
            (factual_accuracy * self.weights["factual_accuracy"]) +
            (efficiency * self.weights["efficiency"]) +
            (relationship_consistency * self.weights["relationship_consistency"])
        )
        return reward

def get_reward_engine():
    return RewardEngine()
