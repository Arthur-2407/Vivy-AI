"""
agi/executive/agency_controller.py
==============================
The highest-level arbiter of Vivy's behavior (Level 9). 
Decides whether to act proactively, react, or remain silent, while utilizing learned strategies from Level 8.
"""
from agi.bus.event_bus import get_event_bus
from agi.executive.self_model import get_self_model
from agi.executive.goal_motivation_engine import get_motivation_engine
from neural.experience_store import get_experience_store

class AgencyController:
    def __init__(self):
        self.proactivity_threshold = 0.7
        self.self_model = get_self_model()
        self.motivation_engine = get_motivation_engine()
        self.experience_store = get_experience_store()
        
        bus = get_event_bus()
        bus.subscribe("PERCEPTION_UPDATE", self.evaluate_context)
        
    def evaluate_context(self, event):
        payload = event.get("payload", {})
        top_goal = self.motivation_engine.get_top_goal()
        mode = self.determine_action_mode(payload, top_goal.get("priority", 0) / 10.0)
        
        # Retrieve learned strategies for the current context
        experiences = self.experience_store.get_similar_experiences(
            current_state=payload.get("perception_state", {}),
            limit=5
        )
        
        # LEVEL 11: Pass candidate strategies through Identity Continuity Gate
        from evolution.identity_continuity import get_identity_continuity_engine
        identity_engine = get_identity_continuity_engine()
        
        successful_strategies = []
        for e in experiences:
            strategy = e.get("response_strategy")
            if strategy and e.get("reward", 0.0) > 0.5:
                # Mock weights for evaluation if not present
                weights = e.get("weights", {"empathy_budget": 1.0, "relationship_importance": 1.0})
                id_score, _ = identity_engine.evaluate_identity_drift(strategy, weights)
                if id_score >= 0.7:
                    successful_strategies.append(strategy)
        
        preferred_strategy = successful_strategies[0] if successful_strategies else None
        
        if mode == 'proactive':
            get_event_bus().publish("EXECUTIVE_DECISION", {
                "action": "initiate_dialogue", 
                "goal": top_goal,
                "strategy": preferred_strategy
            })
        elif mode == 'react':
            get_event_bus().publish("EXECUTIVE_DECISION", {
                "action": "respond",
                "goal": top_goal,
                "strategy": preferred_strategy
            })

    def determine_action_mode(self, context_vector: dict, motivation_state: float) -> str:
        if motivation_state > self.proactivity_threshold:
            return 'proactive'
        elif context_vector.get('user_addressed_ai', False):
            return 'react'
        return 'idle'

_agency_instance = None
def get_agency_controller():
    global _agency_instance
    if _agency_instance is None:
        _agency_instance = AgencyController()
    return _agency_instance
