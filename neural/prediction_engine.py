"""
neural/prediction_engine.py
==============================
Predicts the outcome of actions and compares them to actual events to calculate prediction errors.
"""

class PredictionEngine:
    def __init__(self):
        self.active_predictions = {}

    def register_prediction(self, context_id: str, expected_outcomes: dict):
        """
        Registers a prediction for a given context (e.g. session_id, trace_id, or task_id).
        expected_outcomes could include keys like 'task_success', 'user_feedback', etc.
        """
        self.active_predictions[context_id] = expected_outcomes

    def evaluate_outcome(self, context_id: str, actual_outcomes: dict) -> float:
        """
        Returns prediction error magnitude (0.0 to 1.0).
        Calculates the Mean Squared Error (MSE) between expected and actual outcome signals.
        """
        if context_id not in self.active_predictions:
            return 0.0
            
        expected = self.active_predictions.pop(context_id)
        
        error_sum = 0.0
        count = 0
        for k, v_exp in expected.items():
            if k in actual_outcomes:
                v_act = actual_outcomes[k]
                if isinstance(v_exp, (int, float)) and isinstance(v_act, (int, float)):
                    error_sum += (v_act - v_exp) ** 2
                    count += 1
                    
        if count == 0:
            return 0.0
            
        mse = error_sum / count
        # Clamp to [0, 1]
        return min(max(mse, 0.0), 1.0)

_prediction_engine_instance = None
def get_prediction_engine() -> PredictionEngine:
    global _prediction_engine_instance
    if _prediction_engine_instance is None:
        _prediction_engine_instance = PredictionEngine()
    return _prediction_engine_instance
