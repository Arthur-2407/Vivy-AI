import sys
import os

# Add Vivy directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from action import get_action_system
from action.intent_model import ActionState, IntentModel

def test_pipeline():
    print("Testing Action Pipeline...")
    manager = get_action_system()
    
    # Test 1: Intent Detection
    print("\n--- Test 1: Intent Detection ---")
    intent = manager.detect_intent_only("play in the end", {})
    if intent:
        print(f"Success: Detected intent: {intent.domain} -> {intent.action} (target: {intent.target})")
    else:
        print("Failed: No intent detected.")

    # Test 2: Execution Path
    print("\n--- Test 2: LOW_RISK Execution ---")
    result = manager.handle("play in the end", {})
    print(f"State: {result.state}")
    print(f"Message: {result.message}")
    print(f"Success: {result.success}")
    
    # Test 3: HIGH_RISK Execution Gate
    print("\n--- Test 3: HIGH_RISK Purchase Gate ---")
    purchase_intent = manager.detect_intent_only("buy a speaker", {})
    if purchase_intent:
        # Override to ensure it is evaluated as high risk
        purchase_intent.action = "purchase"
        purchase_intent.domain = "shopping"
        # The intent model specifies high risk if action is purchase, etc.
        res = manager.handle("buy a speaker", {}, predetected_intent=purchase_intent)
        print(f"Result State: {res.state} (Expected: {ActionState.WAITING_FOR_USER.value} or {ActionState.PLANNED.value})")
        print(f"Requires Confirmation: {res.requires_confirmation}")
        
    print("\nDone.")

if __name__ == '__main__':
    test_pipeline()
