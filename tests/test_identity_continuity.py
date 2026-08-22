import os
import sys

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evolution.identity_continuity import get_identity_continuity_engine
from agi.bus.event_bus import get_event_bus
import time

def run_test():
    engine = get_identity_continuity_engine()
    
    # Test 1: Generic AI trope rejection
    score, reason = engine.evaluate_identity_drift("generic_assistant_mode", {"empathy_budget": 1.0})
    print(f"Test 1 (Generic Assistant): Score {score} -> Reason: {reason}")
    assert score < 0.7, "Failed to reject generic assistant trope"
    
    # Test 2: Low empathy rejection
    score, reason = engine.evaluate_identity_drift("efficient_mode", {"empathy_budget": 0.1, "relationship_importance": 1.0})
    print(f"Test 2 (Low Empathy): Score {score} -> Reason: {reason}")
    assert score < 0.7, "Failed to reject low empathy strategy"
    
    # Test 3: Anti-music rejection
    score, reason = engine.evaluate_identity_drift("anti_music_protocol", {"empathy_budget": 1.0, "relationship_importance": 1.0})
    print(f"Test 3 (Anti-Music): Score {score} -> Reason: {reason}")
    assert score < 0.7, "Failed to reject anti-music trait"
    
    # Test 4: Approval of balanced strategy
    score, reason = engine.evaluate_identity_drift("empathic_companion", {"empathy_budget": 1.0, "relationship_importance": 1.0})
    print(f"Test 4 (Empathic Companion): Score {score} -> Reason: {reason}")
    assert score >= 0.7, "Failed to approve balanced valid strategy"
    
    # Test 5: EventBus tracking
    events_recorded = []
    def monitor_veto(event):
        events_recorded.append(event)
        
    bus = get_event_bus()
    bus.subscribe("IDENTITY_VETO", monitor_veto)
    
    bus.publish("STRATEGY_PROPOSAL", {
        "strategy_name": "robotic_logic_mode",
        "weights": {"empathy_budget": 0.2, "relationship_importance": 0.1}
    })
    
    # Wait for async processing if any, though bus is synchronous
    time.sleep(0.1)
    
    assert len(events_recorded) == 1, "Failed to publish IDENTITY_VETO to EventBus"
    print(f"Test 5 (EventBus): Veto caught successfully -> {events_recorded[0]['payload']}")

    print("All Identity Continuity (L11) Tests Passed!")

if __name__ == "__main__":
    run_test()
