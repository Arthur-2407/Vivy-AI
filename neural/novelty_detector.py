"""
neural/novelty_detector.py
==============================
Calculates the learning priority of an experience based on novelty, surprise, importance, outcome delta, and recurrence.
"""

class NoveltyDetector:
    def __init__(self):
        pass

    def calculate_priority(self, 
                           novelty: float, 
                           surprise: float, 
                           importance: float, 
                           outcome_delta: float, 
                           recurrence: float) -> float:
        """
        Calculates a scalar learning priority for an experience.
        
        learning_priority = novelty * surprise * importance * outcome_delta * recurrence
        
        A high priority indicates the experience should be consolidated into strategy/memory rapidly.
        """
        # Ensure values don't multiply to zero unless strictly necessary
        nov = max(novelty, 0.1)
        sur = max(surprise, 0.1)
        imp = max(importance, 0.1)
        out = max(outcome_delta, 0.1)
        rec = max(recurrence, 0.1)
        
        return nov * sur * imp * out * rec

def get_novelty_detector():
    return NoveltyDetector()
