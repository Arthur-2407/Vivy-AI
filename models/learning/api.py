"""
Vivy AI - ML Learning Service Facade
Exposes Online Learning / Experience Replay loop managed by the CPU Orchestrator.
Safely logs interactions and builds datasets for offline retraining.
"""
import sys
import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from evolution.experience_replay import get_experience_replay

def log_experience(user_input: str, ai_response: str, context: dict, emotion: str, reward: float = 0.0):
    """
    Logs an interaction securely to the JSONL dataset for future offline training.
    Prevents live neural degradation.
    """
    replay = get_experience_replay()
    replay.log_interaction(
        user_input=user_input,
        ai_response=ai_response,
        context_state=context,
        emotion_state=emotion,
        reward_proxy=reward
    )

def trigger_offline_training():
    """
    Hooks into the offline consolidation loop. 
    Can be run during idle CPU cycles to validate and tune embedding networks.
    """
    replay = get_experience_replay()
    replay.consolidate_learning()
