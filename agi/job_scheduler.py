"""
Vivy AI — Autonomous Job Scheduler & Workflow Engine (AGI Subsystem)
====================================================================
Provides durable background job scheduling, persistent reminders, repeating interval timers,
and long-horizon multi-day task check-ins. Features:
  - Thread-safe disk persistence (`shared/scheduled_jobs.json`)
  - Asynchronous check-in evaluations without blocking conversation loops
  - Seamless bridge with `LongHorizonPlanner` for multi-day goal monitoring
  - Automatic event publishing to `CognitiveBlackboard` upon task trigger
"""

import os
import time
import json
import uuid
import threading
from typing import Dict, List, Optional, Any, Callable

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORAGE_DIR = os.path.join(BASE_DIR, "shared")
DEFAULT_PATH = os.path.join(STORAGE_DIR, "scheduled_jobs.json")

class JobScheduler:
    """Durable autonomous task scheduler and long-horizon workflow manager."""
    _instance = None
    _lock = threading.RLock()

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or DEFAULT_PATH
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._load_from_disk()

    @classmethod
    def get_instance(cls) -> "JobScheduler":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _load_from_disk(self):
        with self._lock:
            try:
                if os.path.exists(self.storage_path):
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        self.jobs = json.load(f)
            except Exception as err:
                print(f"[JobScheduler] Silenced load warning: {err}")
                self.jobs = {}

    def _save_to_disk(self) -> bool:
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
                tmp_path = self.storage_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self.jobs, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.storage_path)
                return True
            except Exception as err:
                print(f"[JobScheduler] Silenced save warning: {err}")
                return False

    def schedule_once(self, title: str, prompt_or_payload: Any, delay_seconds: float, job_type: str = "reminder", target_goal_id: Optional[str] = None) -> str:
        """Schedules a one-time execution job to trigger after delay_seconds."""
        with self._lock:
            job_id = f"job_{str(uuid.uuid4())[:8]}"
            trigger_time = time.time() + max(0.1, delay_seconds)
            self.jobs[job_id] = {
                "job_id": job_id,
                "title": title,
                "payload": prompt_or_payload,
                "job_type": job_type,
                "target_goal_id": target_goal_id,
                "trigger_time": trigger_time,
                "interval_seconds": None,
                "recurring": False,
                "status": "pending",
                "created_at": time.time(),
                "last_run": None,
                "run_count": 0
            }
            self._save_to_disk()
            return job_id

    def schedule_recurring(self, title: str, prompt_or_payload: Any, interval_seconds: float, job_type: str = "cron", max_runs: Optional[int] = None, target_goal_id: Optional[str] = None) -> str:
        """Schedules a repeating recurring job executing every interval_seconds."""
        with self._lock:
            job_id = f"cron_{str(uuid.uuid4())[:8]}"
            trigger_time = time.time() + max(0.5, interval_seconds)
            self.jobs[job_id] = {
                "job_id": job_id,
                "title": title,
                "payload": prompt_or_payload,
                "job_type": job_type,
                "target_goal_id": target_goal_id,
                "trigger_time": trigger_time,
                "interval_seconds": interval_seconds,
                "recurring": True,
                "max_runs": max_runs,
                "status": "active",
                "created_at": time.time(),
                "last_run": None,
                "run_count": 0
            }
            self._save_to_disk()
            return job_id

    def register_long_horizon_goal(self, goal_id: str, check_interval_hours: float = 12.0) -> str:
        """Bridges LongHorizonPlanner goals into autonomous periodic check-ins."""
        return self.schedule_recurring(
            title=f"Goal Check-In: {goal_id}",
            prompt_or_payload={"action": "check_goal_progress", "goal_id": goal_id},
            interval_seconds=check_interval_hours * 3600.0,
            job_type="long_horizon_goal",
            target_goal_id=goal_id
        )

    def register_evolution_cycle(self) -> str:
        """Phase 3 Integration: Register nightly self-evolution cycle."""
        return self.schedule_recurring(
            title="Nightly Self-Evolution Cycle",
            prompt_or_payload={"action": "run_evolution"},
            interval_seconds=12.0 * 3600.0,
            job_type="evolution_cycle"
        )

    def evaluate_due_jobs(self, current_time: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Evaluates all scheduled jobs and returns due triggers for cognitive processing.
        Automatically updates recurring intervals and advances completed milestones.
        """
        with self._lock:
            now = current_time or time.time()
            due_list = []
            dirty = False

            for job_id, job in list(self.jobs.items()):
                if job.get("status") in ["completed", "cancelled"]:
                    continue

                if now >= job.get("trigger_time", 0.0):
                    job["last_run"] = now
                    job["run_count"] = job.get("run_count", 0) + 1
                    
                    event_package = {
                        "job_id": job_id,
                        "title": job["title"],
                        "payload": job["payload"],
                        "job_type": job["job_type"],
                        "target_goal_id": job["target_goal_id"],
                        "triggered_at": now,
                        "run_count": job["run_count"]
                    }
                    due_list.append(event_package)
                    dirty = True

                    # Notify Cognitive Blackboard
                    try:
                        from agi.blackboard import get_cognitive_blackboard
                        bb = get_cognitive_blackboard()
                        bb.publish_state(f"scheduled_job_{job_id}", event_package, source_engine="JobScheduler")
                        if job["job_type"] == "long_horizon_goal" and job["target_goal_id"]:
                            # Advance or audit LongHorizonPlanner goal
                            from agi.long_horizon_planner import get_long_horizon_planner
                            lhp = get_long_horizon_planner()
                            g_data = lhp.get_goal(job["target_goal_id"])
                            if g_data and g_data.get("status") == "completed":
                                job["status"] = "completed"
                                
                        elif job["job_type"] == "evolution_cycle":
                            # Phase 4 Integration: Link to true circadian rhythm
                            from evolution.evolution_engine import get_evolution_engine
                            try:
                                from circadian_intelligence import get_circadian_intelligence
                                ci = get_circadian_intelligence()
                                current_phase = ci.get_current_phase()
                            except Exception:
                                current_phase = "Night"
                            
                            get_evolution_engine().run_evolution_cycle(circadian_phase=current_phase)
                            
                    except Exception as _bb_err:
                        print(f"[JobScheduler] Silenced blackboard event notification warning: {_bb_err}")

                    if job["recurring"]:
                        max_r = job.get("max_runs")
                        if max_r and job["run_count"] >= max_r:
                            job["status"] = "completed"
                        else:
                            job["trigger_time"] = now + max(1.0, float(job.get("interval_seconds", 3600.0)))
                    else:
                        job["status"] = "completed"

            if dirty:
                self._save_to_disk()
            return due_list

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id]["status"] = "cancelled"
                self._save_to_disk()
                return True
            return False

    def get_active_jobs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [j for j in self.jobs.values() if j.get("status") in ["pending", "active"]]

_global_job_scheduler = None
def get_job_scheduler() -> JobScheduler:
    global _global_job_scheduler
    if _global_job_scheduler is None:
        _global_job_scheduler = JobScheduler()
    return _global_job_scheduler
