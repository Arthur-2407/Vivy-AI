"""
evolution/meta_learning.py
==================================
Vivy AI — Evolution Engine: Meta Learning

Optimizes learning strategies, manages curriculum scheduling, and dynamically tunes
adaptation hyperparameters based on environmental stability.
"""

from __future__ import annotations
import os
import time
import math
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from evolution.perception_layer import get_perception_layer
from evolution.adaptation_engine import get_adaptation_engine

@dataclass
class HyperparameterConfig:
    learning_rate: float = 0.05
    exploration_rate: float = 0.10
    token_budget_scale: float = 1.0
    rie_threshold: float = 0.75
    curriculum_stage: str = "standard_dialogue"

class MetaLearningEngine:
    """
    Meta-learning controller for hyperparameter adaptation and curriculum scheduling.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._current_config = HyperparameterConfig()
        self._curriculum_stages = ["greeting_warmup", "standard_dialogue", "deep_companion", "complex_task_solving"]
        self._current_stage_idx = 1  # Default: standard_dialogue

    def optimize_hyperparameters(self) -> HyperparameterConfig:
        perception = get_perception_layer()
        exps = perception.get_recent_experiences(40)

        with self._lock:
            if not exps:
                return self._current_config

            avg_feedback = sum(e.feedback_score for e in exps) / len(exps)

            # Adaptive exploration rate: reduce exploration when performance is high
            if avg_feedback > 0.85:
                self._current_config.exploration_rate = max(0.02, self._current_config.exploration_rate * 0.95)
                self._current_config.learning_rate = min(0.1, self._current_config.learning_rate * 1.02)
            else:
                self._current_config.exploration_rate = min(0.25, self._current_config.exploration_rate * 1.05)
                self._current_config.learning_rate = max(0.01, self._current_config.learning_rate * 0.95)

            # Advance curriculum stage if consistently performing well
            if avg_feedback > 0.90 and len(exps) >= 30 and self._current_stage_idx < len(self._curriculum_stages) - 1:
                self._current_stage_idx += 1
                self._current_config.curriculum_stage = self._curriculum_stages[self._current_stage_idx]

            return self._current_config

    def get_config(self) -> HyperparameterConfig:
        with self._lock:
            return self._current_config

_global_meta_learning_engine: Optional[MetaLearningEngine] = None
_meta_learning_lock = threading.Lock()

def get_meta_learning_engine() -> MetaLearningEngine:
    global _global_meta_learning_engine
    if _global_meta_learning_engine is None:
        with _meta_learning_lock:
            if _global_meta_learning_engine is None:
                _global_meta_learning_engine = MetaLearningEngine()
    return _global_meta_learning_engine
