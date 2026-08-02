"""
Vivy AI — Autonomous Skill & Capability Library
=============================================
Instead of hardcoding conversational behaviors and procedural logic, the Skill System
maintains an evolving repository of autonomous capability profiles in `vivy_skill_memory.json`.
Workflow Loop:
  Skill -> Capability -> Evaluation -> Learning -> Upgrade
"""

import os
import json
import time
import threading
from typing import Dict, List, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_FILE = os.path.join(BASE_DIR, "vivy_skill_memory.json")

class SkillSystem:
    """Thread-safe skill progression and capability upgrade engine."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls, storage_path: str = SKILLS_FILE) -> "SkillSystem":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(storage_path)
            return cls._instance

    def __init__(self, storage_path: str = SKILLS_FILE):
        self._lock = threading.RLock()
        self.storage_path = storage_path
        # Map skill_name -> skill schema
        self.skills: Dict[str, Dict[str, Any]] = {
            "conversational_empathy": {"level": 2, "xp": 120.0, "next_tier_xp": 250.0, "success_rate": 0.88, "status": "active", "description": "Detecting human emotional distress and expressing warmth"},
            "code_reasoning": {"level": 3, "xp": 310.0, "next_tier_xp": 500.0, "success_rate": 0.92, "status": "active", "description": "Analyzing software structures and syntactic patterns"},
            "multimodal_sensor_fusion": {"level": 2, "xp": 180.0, "next_tier_xp": 250.0, "success_rate": 0.85, "status": "active", "description": "Synthesizing eye contact, audio transcripts, and screen context"},
            "autonomous_research": {"level": 1, "xp": 45.0, "next_tier_xp": 100.0, "success_rate": 0.78, "status": "learning", "description": "Navigating internet intelligence and knowledge caching"}
        }
        self.load_from_disk()

    def load_from_disk(self) -> None:
        with self._lock:
            if os.path.exists(self.storage_path):
                try:
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        if "skills" in data and isinstance(data["skills"], dict):
                            self.skills.update(data["skills"])
                        else:
                            # Preserve legacy schema if present without overwriting defaults
                            for k, v in data.items():
                                if isinstance(v, dict):
                                    self.skills[k] = v
                except Exception as _err:
                    print(f"[SkillSystem] Load warning, keeping default library: {_err}")

    def save_to_disk(self) -> bool:
        with self._lock:
            try:
                payload = {
                    "last_updated": time.time(),
                    "total_skills": len(self.skills),
                    "skills": self.skills
                }
                tmp_path = self.storage_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.storage_path)
                return True
            except Exception as _err:
                print(f"[SkillSystem] Save error: {_err}")
                return False

    def evaluate_and_upgrade_skill(self, skill_name: str, success: bool, xp_gain: float = 15.0) -> Dict[str, Any]:
        """
        Evaluates capability execution, updates XP and success rate, and triggers recursive
        upgrades when thresholds are reached.
        """
        with self._lock:
            if skill_name not in self.skills:
                self.skills[skill_name] = {
                    "level": 1,
                    "xp": 0.0,
                    "next_tier_xp": 100.0,
                    "success_rate": 0.5,
                    "status": "learning",
                    "description": f"Dynamically acquired capability: {skill_name}"
                }
                
            sk = self.skills[skill_name]
            old_sr = sk.get("success_rate", 0.5)
            # Update moving average success rate
            new_sr = round((old_sr * 0.8) + (1.0 if success else 0.0) * 0.2, 3)
            sk["success_rate"] = new_sr
            
            if success:
                sk["xp"] = round(float(sk.get("xp", 0.0) + xp_gain), 1)
                if sk["xp"] >= float(sk.get("next_tier_xp", 100.0)):
                    sk["level"] = sk.get("level", 1) + 1
                    sk["next_tier_xp"] = round(sk.get("next_tier_xp", 100.0) * 1.8, 1)
                    sk["status"] = "mastered" if sk["level"] >= 5 else "active"
                    print(f"[SkillSystem] UPGRADE! Capability '{skill_name}' advanced to Level {sk['level']}!")
                    
            self.save_to_disk()
            return dict(sk)

    def get_skill_profile(self) -> Dict[str, Any]:
        """Returns full copy of active skill registry."""
        with self._lock:
            return dict(self.skills)

    def generate_skill_prompt_hint(self) -> str:
        """Returns brief summary of top mastered skills for LLM persona instructions."""
        with self._lock:
            active_list = [f"{k} (Lvl {v['level']}, SR: {int(v.get('success_rate', 0.5)*100)}%)" 
                           for k, v in self.skills.items() if v.get("level", 1) >= 2]
            if not active_list:
                return ""
            return "[Active Capabilities]: " + ", ".join(active_list[:4])

_global_skill_system = None
def get_skill_system() -> SkillSystem:
    global _global_skill_system
    if _global_skill_system is None:
        _global_skill_system = SkillSystem.get_instance()
    return _global_skill_system
