"""
evolution/consolidation_layer.py
==================================
Vivy AI — Evolution Engine: Consolidation Layer

Manages selective replay buffers, consolidates skills into long-term memory,
and maintains versioned prompt templates.
"""

from __future__ import annotations
import os
import json
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from evolution.perception_layer import Experience, get_perception_layer

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
_SHARED_DIR = os.path.join(_PROJECT_ROOT, "shared")
_SKILL_MEMORY_FILE = os.path.join(_PROJECT_ROOT, "vivy_skill_memory.json")

@dataclass
class PromptVersion:
    version_id: str
    timestamp: float
    template_name: str
    prompt_text: str
    performance_score: float
    is_active: bool = True

class ConsolidationLayer:
    """
    Consolidates short-term experiences into persistent skills & versioned prompts.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._prompt_versions: List[PromptVersion] = []
        self._skill_registry: Dict[str, Dict[str, Any]] = self._load_skill_memory()

    def _load_skill_memory(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(_SKILL_MEMORY_FILE):
            try:
                with open(_SKILL_MEMORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as _err:
                print(f"[consolidation_layer.py] Silenced exception: {_err}")
        return {
            "conversational_flow": {"level": 1, "success_rate": 0.9, "version": 1.0},
            "emotional_empathy": {"level": 1, "success_rate": 0.88, "version": 1.0},
            "web_search_synthesis": {"level": 1, "success_rate": 0.85, "version": 1.0}
        }

    def save_skill_memory(self):
        try:
            tmp = _SKILL_MEMORY_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._skill_registry, f, indent=2)
            os.replace(tmp, _SKILL_MEMORY_FILE)
        except Exception as _err:
            print(f"[consolidation_layer.py] Silenced exception: {_err}")

    def consolidate_experiences(self) -> Dict[str, Any]:
        """
        Extract high-value interaction patterns and update consolidated skills.
        """
        perception = get_perception_layer()
        experiences = perception.get_recent_experiences(50)
        if not experiences:
            return {"consolidated_count": 0}

        high_val = [e for e in experiences if e.feedback_score > 0.85]

        with self._lock:
            if high_val:
                # Incrementally consolidate skills
                conv_skill = self._skill_registry.get("conversational_flow", {})
                conv_skill["success_rate"] = round(
                    (conv_skill.get("success_rate", 0.9) * 0.9) + (0.1 * (len(high_val) / len(experiences))), 4
                )
                conv_skill["version"] = round(conv_skill.get("version", 1.0) + 0.01, 2)
                self._skill_registry["conversational_flow"] = conv_skill

            self.save_skill_memory()

        return {
            "consolidated_count": len(high_val),
            "total_experiences": len(experiences),
            "updated_skills": list(self._skill_registry.keys())
        }

    def register_prompt_version(self, template_name: str, prompt_text: str, score: float = 0.9) -> PromptVersion:
        now = time.time()
        ver_id = f"v_{template_name}_{int(now * 1000)}"
        version = PromptVersion(
            version_id=ver_id,
            timestamp=now,
            template_name=template_name,
            prompt_text=prompt_text,
            performance_score=score,
            is_active=True
        )

        with self._lock:
            # Deactivate older versions of the same template
            for pv in self._prompt_versions:
                if pv.template_name == template_name:
                    pv.is_active = False
            self._prompt_versions.append(version)

        return version

    def get_active_prompt(self, template_name: str) -> Optional[PromptVersion]:
        with self._lock:
            for pv in reversed(self._prompt_versions):
                if pv.template_name == template_name and pv.is_active:
                    return pv
        return None

_global_consolidation_layer: Optional[ConsolidationLayer] = None
_consolidation_lock = threading.Lock()

def get_consolidation_layer() -> ConsolidationLayer:
    global _global_consolidation_layer
    if _global_consolidation_layer is None:
        with _consolidation_lock:
            if _global_consolidation_layer is None:
                _global_consolidation_layer = ConsolidationLayer()
    return _global_consolidation_layer
