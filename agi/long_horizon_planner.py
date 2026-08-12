"""
Vivy AI — Long-Horizon Planner & Objective Decomposition Engine
============================================================
Enables Vivy to transition from short-term conversational QA ("Answer this question")
toward persistent long-term task execution ("Spend three weeks achieving this objective").

Workflow Hierarchy:
  Goal -> Milestones -> Tasks -> Dependencies -> Execution -> Review -> Revision
"""

import os
import json
import time
import threading
from typing import Dict, List, Optional, Any
from agi.blackboard import get_cognitive_blackboard

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOALS_FILE = os.path.join(BASE_DIR, "vivy_goals.json")

class LongHorizonPlanner:
    """Thread-safe hierarchical task and long-term objective planner."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls, storage_path: str = GOALS_FILE) -> "LongHorizonPlanner":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(storage_path)
            return cls._instance

    def __init__(self, storage_path: str = GOALS_FILE):
        self._lock = threading.RLock()
        self.storage_path = storage_path
        # Map goal_id -> goal dictionary struct
        self.goals: Dict[str, Dict[str, Any]] = {}
        self.active_goal_id: Optional[str] = None
        self.load_from_disk()

    def load_from_disk(self) -> None:
        with self._lock:
            if os.path.exists(self.storage_path):
                try:
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "goals" in data:
                        self.goals = data["goals"]
                        self.active_goal_id = data.get("active_goal_id")
                    else:
                        self.goals = data
                except Exception as _err:
                    print(f"[LongHorizonPlanner] Load error, using default empty: {_err}")
                    self.goals = {}

    def save_to_disk(self) -> bool:
        with self._lock:
            try:
                payload = {
                    "last_modified": time.time(),
                    "active_goal_id": self.active_goal_id,
                    "total_goals": len(self.goals),
                    "goals": self.goals
                }
                tmp_path = self.storage_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.storage_path)
                return True
            except Exception as _err:
                print(f"[LongHorizonPlanner] Atomic save failed: {_err}")
                return False

    def create_goal(self, title: str, description: str, target_days: int = 7, milestones: Optional[List[str]] = None) -> str:
        """
        Decomposes a new high-level objective into structured milestones and dependency tasks.
        Returns unique goal ID.
        """
        with self._lock:
            now = time.time()
            words = [w.lower() for w in title.split() if len(w) > 2][:4]
            g_id = "goal_" + ("_".join(words) if words else str(int(now)))
            
            msts = []
            if milestones:
                for idx, m_title in enumerate(milestones):
                    msts.append({
                        "id": f"{g_id}_m_{idx+1}",
                        "title": m_title,
                        "status": "pending",
                        "dependencies": [f"{g_id}_m_{idx}"] if idx > 0 else [],
                        "tasks": [
                            {"title": f"Research & structure {m_title}", "status": "pending"},
                            {"title": f"Execute implementation for {m_title}", "status": "pending"},
                            {"title": f"Validate & verify {m_title}", "status": "pending"}
                        ]
                    })
            else:
                msts = [
                    {"id": f"{g_id}_m_1", "title": "Phase 1: Initial Research & Foundation", "status": "pending", "dependencies": [], "tasks": [{"title": "Explore scope and gathering context", "status": "pending"}]},
                    {"id": f"{g_id}_m_2", "title": "Phase 2: Execution & Development", "status": "pending", "dependencies": [f"{g_id}_m_1"], "tasks": [{"title": "Implement primary components", "status": "pending"}]},
                    {"id": f"{g_id}_m_3", "title": "Phase 3: Final Verification & Review", "status": "pending", "dependencies": [f"{g_id}_m_2"], "tasks": [{"title": "Conduct verification suite", "status": "pending"}]}
                ]

            self.goals[g_id] = {
                "id": g_id,
                "title": title.strip(),
                "description": description.strip(),
                "created_at": now,
                "target_completion": now + (target_days * 86400),
                "status": "active",
                "progress_percentage": 0.0,
                "milestones": msts,
                "revision_history": []
            }
            if self.active_goal_id is None or self.goals.get(self.active_goal_id, {}).get("status") == "completed":
                self.active_goal_id = g_id
                
            self.save_to_disk()
            # Publish new goal state to Cognitive Blackboard
            try:
                get_cognitive_blackboard().publish_state("active_long_horizon_goal", self.goals[g_id], source_engine="LongHorizonPlanner")
            except Exception as _e:
                print(f"[LongHorizonPlanner] Blackboard publish failed: {_e}")
            return g_id

    def update_task_progress(self, goal_id: str, milestone_idx: int, task_idx: int, status: str) -> bool:
        """Updates task status ('pending', 'in_progress', 'completed') and recalculates goal progress."""
        with self._lock:
            goal = self.goals.get(goal_id)
            if not goal or milestone_idx >= len(goal["milestones"]):
                return False
            m = goal["milestones"][milestone_idx]
            if task_idx >= len(m["tasks"]):
                return False
                
            m["tasks"][task_idx]["status"] = status
            # If all tasks completed, mark milestone completed
            if all(t["status"] == "completed" for t in m["tasks"]):
                m["status"] = "completed"
            elif any(t["status"] in ("in_progress", "completed") for t in m["tasks"]):
                m["status"] = "in_progress"
                
            # Recalculate global percentage
            total_tasks = sum(len(mst["tasks"]) for mst in goal["milestones"])
            comp_tasks = sum(sum(1 for t in mst["tasks"] if t["status"] == "completed") for mst in goal["milestones"])
            goal["progress_percentage"] = round((comp_tasks / max(1, total_tasks)) * 100.0, 1)
            
            if goal["progress_percentage"] >= 99.9:
                goal["status"] = "completed"
                
            self.save_to_disk()
            try:
                get_cognitive_blackboard().publish_state("active_long_horizon_goal", goal, source_engine="LongHorizonPlanner")
            except Exception as _e:
                print(f"[LongHorizonPlanner] Blackboard publish failed: {_e}")
            return True

    def revise_plan(self, goal_id: str, reason: str, new_milestone_title: Optional[str] = None) -> bool:
        """Autonomous plan revision when roadblocks or failures occur."""
        with self._lock:
            goal = self.goals.get(goal_id)
            if not goal:
                return False
            now = time.time()
            goal["revision_history"].append({"timestamp": now, "reason": reason})
            if new_milestone_title:
                idx = len(goal["milestones"]) + 1
                goal["milestones"].append({
                    "id": f"{goal_id}_m_{idx}_rev",
                    "title": new_milestone_title,
                    "status": "pending",
                    "dependencies": [],
                    "tasks": [{"title": "Execute revised strategy", "status": "pending"}]
                })
            self.save_to_disk()
            return True

    def get_active_goal_summary(self) -> str:
        """Returns concise summary of active objective for conversational planning."""
        with self._lock:
            if not self.active_goal_id or self.active_goal_id not in self.goals:
                return ""
            goal = self.goals[self.active_goal_id]
            if goal["status"] == "completed":
                return ""
            curr_m = next((m for m in goal["milestones"] if m["status"] != "completed"), None)
            m_text = f" | Active Milestone: {curr_m['title']}" if curr_m else ""
            return f"[Long-Horizon Objective]: '{goal['title']}' ({goal['progress_percentage']}% complete){m_text}"

_global_planner = None
def get_long_horizon_planner() -> LongHorizonPlanner:
    global _global_planner
    if _global_planner is None:
        _global_planner = LongHorizonPlanner.get_instance()
    return _global_planner
