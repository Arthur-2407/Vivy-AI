"""
Vivy AI — Continual Learning & Autonomous Curiosity Engine
======================================================
Instead of waiting passively for user prompts, the Continual Learning Engine asks itself:
  - What don't I understand? (Knowledge gaps)
  - What should I study next? (Curiosity priorities)
  - Which skill limits my performance? (Bottleneck analysis)
  - How can I improve without catastrophic forgetting? (Episodic replay buffer retention)
"""

import os
import json
import time
import threading
from typing import Dict, List, Any, Optional
from agi.skill_system import get_skill_system
from agi.blackboard import get_cognitive_blackboard

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEARNING_FILE = os.path.join(BASE_DIR, "vivy_learning_schedule.json")

class LearningEngine:
    """Thread-safe continual learning monitor and curiosity scheduler."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls, storage_path: str = LEARNING_FILE) -> "LearningEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(storage_path)
            return cls._instance

    def __init__(self, storage_path: str = LEARNING_FILE):
        self._lock = threading.RLock()
        self.storage_path = storage_path
        self.knowledge_gaps: List[Dict[str, Any]] = []
        self.study_schedule: List[Dict[str, Any]] = []
        self.mistake_log: List[Dict[str, Any]] = []
        self.retention_buffer: List[Dict[str, Any]] = [] # Protects against catastrophic forgetting
        self.load_from_disk()

    def load_from_disk(self) -> None:
        with self._lock:
            if os.path.exists(self.storage_path):
                try:
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.knowledge_gaps = data.get("knowledge_gaps", [])
                    self.study_schedule = data.get("study_schedule", [])
                    self.mistake_log = data.get("mistake_log", [])
                    self.retention_buffer = data.get("retention_buffer", [])
                except Exception as _err:
                    print(f"[LearningEngine] Load error: {_err}")

    def save_to_disk(self) -> bool:
        with self._lock:
            try:
                payload = {
                    "last_updated": time.time(),
                    "knowledge_gaps": self.knowledge_gaps[-30:],
                    "study_schedule": self.study_schedule[-20:],
                    "mistake_log": self.mistake_log[-30:],
                    "retention_buffer": self.retention_buffer[-50:]
                }
                tmp_path = self.storage_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.storage_path)
                return True
            except Exception as _err:
                print(f"[LearningEngine] Save error: {_err}")
                return False

    def log_interaction_evaluation(self, user_text: str, reply_text: str, eval_score: float, topic: str = "General", error_detail: Optional[str] = None) -> None:
        """
        Evaluates post-turn performance. Low scores or explicit errors trigger learning
        schedule queues and curiosity gaps.
        """
        with self._lock:
            now = time.time()
            if eval_score < 0.6 or error_detail:
                # Log mistake for reflective review
                self.mistake_log.append({
                    "timestamp": now,
                    "topic": topic,
                    "user_query": user_text[:100],
                    "error_detail": error_detail or "Low emotional or relevance score (<0.6)"
                })
                # Schedule autonomous curiosity study item
                gap_item = f"Deepen comprehension of topic: {topic}"
                if not any(g["topic"] == topic for g in self.knowledge_gaps):
                    self.knowledge_gaps.append({"topic": topic, "identified_at": now, "status": "open"})
                    self.study_schedule.append({"task": gap_item, "scheduled_for": now + 3600, "priority": "high"})
            else:
                # High score: deposit in retention buffer to protect against catastrophic forgetting during replay
                self.retention_buffer.append({
                    "timestamp": now,
                    "topic": topic,
                    "successful_pattern": f"Query on {topic} handled with high satisfaction"
                })
                # Hook into existing ML learning API if available
                try:
                    import models.learning.api as l_api
                    l_api.log_experience(user_input=user_text, ai_response=reply_text, context={"topic": topic}, emotion="joy", reward=1.0)
                except Exception as _e:
                    print(f"[LearningEngine] ML learning API log failed: {_e}")

            # Inspect skills for performance bottlenecks
            try:
                sk_sys = get_skill_system()
                for sk_name, sk_data in sk_sys.skills.items():
                    if sk_data.get("success_rate", 1.0) < 0.65:
                        bot_task = f"Practice and refine capability: {sk_name}"
                        if not any(s["task"] == bot_task for s in self.study_schedule):
                            self.study_schedule.append({"task": bot_task, "scheduled_for": now + 1800, "priority": "urgent"})
            except Exception as _e:
                print(f"[LearningEngine] Skill system inspection failed: {_e}")

            self.save_to_disk()
            try:
                get_cognitive_blackboard().publish_state("active_learning_schedule", self.study_schedule, source_engine="LearningEngine")
            except Exception as _e:
                print(f"[LearningEngine] Blackboard publish failed: {_e}")

    def get_curiosity_prompt_hint(self) -> str:
        """Returns autonomous study items to inform proactive conversation topics."""
        with self._lock:
            if not self.study_schedule:
                return ""
            top = sorted(self.study_schedule, key=lambda x: 0 if x["priority"]=="urgent" else 1)
            return f"[Autonomous Curiosity]: Proactively interested in exploring: '{top[0]['task']}'"

_global_learning_engine = None
def get_learning_engine() -> LearningEngine:
    global _global_learning_engine
    if _global_learning_engine is None:
        _global_learning_engine = LearningEngine.get_instance()
    return _global_learning_engine
