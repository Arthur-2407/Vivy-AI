"""
neural/experience_store.py
==============================
Stores structured metadata for the Neural Learning Fabric.
Used for experience replay and strategy adaptation.
"""

import json
import os
import uuid
import time
from typing import Dict, Any, List

class ExperienceStore:
    def __init__(self, storage_path="d:/Vivy/data/neural_experiences.json"):
        self.storage_path = storage_path
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        self.experiences = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.storage_path):
            with open(self.storage_path, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return []
        return []

    def _save(self):
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self.experiences, f, indent=2)

    def record_experience(self, 
                          user_state: dict, 
                          emotion_state: dict, 
                          perception_state: dict, 
                          goal: str,
                          action: str, 
                          tool_usage: list, 
                          response_strategy: str,
                          prediction: dict, 
                          outcome: dict, 
                          reward: float, 
                          confidence: float, 
                          novelty: float, 
                          learning_value: float,
                          source: str = "conversation") -> str:
        
        experience = {
            "experience_id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "user_state": user_state,
            "emotion_state": emotion_state,
            "perception_state": perception_state,
            "goal": goal,
            "action": action,
            "tool_usage": tool_usage,
            "response_strategy": response_strategy,
            "prediction": prediction,
            "outcome": outcome,
            "reward": reward,
            "confidence": confidence,
            "novelty": novelty,
            "learning_value": learning_value,
            "source": source
        }
        
        self.experiences.append(experience)
        self._save()
        return experience["experience_id"]
        
    def get_similar_experiences(self, current_state: dict, limit: int = 5) -> List[Dict]:
        # Placeholder for vector similarity search over context embeddings
        # For now, return most recent experiences
        return sorted(self.experiences, key=lambda x: x["timestamp"], reverse=True)[:limit]

_store_instance = None
def get_experience_store() -> ExperienceStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = ExperienceStore()
    return _store_instance
