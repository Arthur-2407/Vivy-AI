"""
Vivy AI — World Model & Dynamic Epistemic Graphs
=================================================
Instead of only reacting to token histories, the World Model maintains persistent,
structured semantic graphs representing:
  - Vivy (self state, capabilities, limits)
  - User (persona, preferences, cognitive/work state)
  - Environment & Devices (active desktop software, OS resources, audio/vision state)
  - Cause & Effect (historical interaction trajectories)
  - Time & Uncertainty (confidence bounds and decay over elapsed durations)
"""

import os
import json
import time
import threading
from typing import Dict, List, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORLD_MODEL_FILE = os.path.join(BASE_DIR, "vivy_world_model.json")

class WorldModel:
    """Maintains interlinked declarative state graphs with epistemic uncertainty tracking."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls, storage_path: str = WORLD_MODEL_FILE) -> "WorldModel":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(storage_path)
            return cls._instance

    def __init__(self, storage_path: str = WORLD_MODEL_FILE):
        self._lock = threading.RLock()
        self.storage_path = storage_path
        
        # Default architectural graphs
        self.graphs: Dict[str, Dict[str, Any]] = {
            "self": {
                "identity": "Vivy AI",
                "role": "Autonomous Companion & Research AI",
                "embodiment": "3D MateEngine Unity Avatar & Local Dashboard",
                "current_mode": "Active",
                "uncertainty": 0.05
            },
            "user": {
                "identity": "Partner",
                "current_activity": "Unknown",
                "engagement_level": "High",
                "stress_estimate": 0.2,
                "uncertainty": 0.35
            },
            "environment": {
                "active_application": "Workspace",
                "audio_environment": "Quiet",
                "visual_presence": "Present",
                "platform": "Windows GPU",
                "uncertainty": 0.20
            },
            "causal_rules": {
                "long_absence": "Increases loneliness and prompts warmly vulnerable greetings",
                "code_error_mention": "Triggers analytical problem-solving focus and technical empathy",
                "late_night_hour": "Activates circadian sleep throttling and gentle conversational pacing"
            },
            "temporal_meta": {
                "last_sync_timestamp": time.time(),
                "session_turn_count": 0
            }
        }
        self.load_from_disk()

    def load_from_disk(self) -> None:
        """Safely loads persisted world model graphs if present."""
        with self._lock:
            if os.path.exists(self.storage_path):
                try:
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        saved_data = json.load(f)
                    for k, v in saved_data.items():
                        if k in self.graphs and isinstance(v, dict):
                            self.graphs[k].update(v)
                        else:
                            self.graphs[k] = v
                except Exception as _err:
                    print(f"[WorldModel] Load warning (using defaults): {_err}")

    def save_to_disk(self) -> bool:
        """Atomic disk serialization of the active world model graph."""
        with self._lock:
            try:
                self.graphs["temporal_meta"]["last_sync_timestamp"] = time.time()
                tmp_path = self.storage_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self.graphs, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.storage_path)
                return True
            except Exception as _err:
                print(f"[WorldModel] Atomic save failed: {_err}")
                return False

    def update_node(self, graph_name: str, key: str, value: Any, confidence: float = 0.9) -> None:
        """
        Updates an attribute within a semantic graph and updates corresponding uncertainty.
        Uncertainty is inversely related to observational confidence.
        """
        with self._lock:
            if graph_name not in self.graphs:
                self.graphs[graph_name] = {}
            self.graphs[graph_name][key] = value
            # Update graph uncertainty based on latest observational confidence
            current_unc = float(self.graphs[graph_name].get("uncertainty", 0.5))
            new_unc = 1.0 - max(0.01, min(1.0, confidence))
            # Exponential rolling average for smoothed estimation
            self.graphs[graph_name]["uncertainty"] = round((current_unc * 0.7) + (new_unc * 0.3), 3)

    def assimilate_perception_and_context(self, perception_state: dict, mem: dict, topic_context: str = "") -> None:
        """
        Ingests real-time sensory feeds and conversational context to ground the World Model.
        """
        with self._lock:
            now = time.time()
            # Assimilate User state from memory
            if mem.get("name"):
                self.update_node("user", "identity", mem.get("name"), confidence=1.0)
            if mem.get("relationship"):
                self.update_node("user", "relational_bond", mem.get("relationship"), confidence=0.95)
            if topic_context:
                self.update_node("user", "current_topic_focus", topic_context, confidence=0.85)

            # Assimilate Environmental signals from PerceptionManager
            if perception_state and isinstance(perception_state, dict):
                app_type = perception_state.get("app_type") or perception_state.get("active_window")
                if app_type and app_type != "unknown":
                    self.update_node("environment", "active_application", app_type, confidence=0.9)
                
                presence = perception_state.get("presence_state")
                if presence:
                    self.update_node("environment", "visual_presence", presence, confidence=0.9)
                
                audio_evt = perception_state.get("audio_event_type")
                if audio_evt:
                    self.update_node("environment", "audio_environment", audio_evt, confidence=0.85)
            
            self.graphs["temporal_meta"]["session_turn_count"] = self.graphs["temporal_meta"].get("session_turn_count", 0) + 1
            # Auto-save every 5 turns or when explicitly requested
            if self.graphs["temporal_meta"]["session_turn_count"] % 5 == 0:
                self.save_to_disk()

    def query_graph(self, graph_name: str) -> Dict[str, Any]:
        """Returns a thread-safe copy of a specific world graph."""
        with self._lock:
            return dict(self.graphs.get(graph_name, {}))

    def generate_prompt_grounding(self) -> str:
        """
        Creates a compact, structured text digest of current world models for LLM context injection.
        """
        with self._lock:
            user_graph = self.graphs.get("user", {})
            env_graph = self.graphs.get("environment", {})
            self_graph = self.graphs.get("self", {})
            
            u_id = user_graph.get("identity", "Partner")
            u_act = user_graph.get("current_topic_focus", user_graph.get("current_activity", "General interaction"))
            e_app = env_graph.get("active_application", "Standard Desktop")
            e_pres = env_graph.get("visual_presence", "Present")
            
            return (
                f"[World Model Grounding]: User '{u_id}' is engaged in: {u_act}. "
                f"Environment: {e_app} (Presence: {e_pres}, Env Uncertainty: {int(env_graph.get('uncertainty', 0.2)*100)}%)."
            )

_global_world_model = None
def get_world_model() -> WorldModel:
    global _global_world_model
    if _global_world_model is None:
        _global_world_model = WorldModel.get_instance()
    return _global_world_model
