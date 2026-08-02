"""
evolution/perception_layer.py
==================================
Vivy AI — Evolution Engine: Perception Layer

Ingests streaming system telemetry, maintains experience buffers, and extracts
compact feature representations for short-term and long-term self-adaptation.

Design Principles:
- CPU-only execution (never consumes GPU cycles reserved for LLM / Vision).
- Non-blocking thread-safe experience replay buffer.
- Backward compatible: zero side-effects on base pipeline.
"""

from __future__ import annotations
import os
import json
import time
import math
import threading
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
_SHARED_DIR = os.path.join(_PROJECT_ROOT, "shared")

@dataclass
class Experience:
    """A single interaction experience unit for self-evolution learning."""
    experience_id: str
    timestamp: float
    user_input: str
    system_reply: str
    emotion_label: str
    rie_score: float
    latency_seconds: float
    perception_context_len: int
    circadian_phase: str
    feedback_score: float = 1.0  # Normalized implicit feedback [0.0 - 1.0]
    feature_vector: List[float] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class PerceptionLayer:
    """
    Ingests runtime telemetry and maintains thread-safe circular experience buffers.
    """
    def __init__(self, max_buffer_size: int = 1000):
        self._lock = threading.Lock()
        self._max_buffer_size = max_buffer_size
        self._buffer: deque[Experience] = deque(maxlen=max_buffer_size)
        self._telemetry_history: deque[Dict[str, Any]] = deque(maxlen=500)
        self._last_telemetry_time = 0.0

    def extract_feature_vector(self, text: str, latency: float, rie_score: float) -> List[float]:
        """
        Lightweight CPU feature extraction:
        [text_length, word_count, latency_s, rie_score, uppercase_ratio, question_mark_present]
        """
        if not text:
            return [0.0, 0.0, latency, rie_score, 0.0, 0.0]
        words = text.split()
        upper_cnt = sum(1 for c in text if c.isupper())
        return [
            float(len(text)),
            float(len(words)),
            float(latency),
            float(rie_score),
            float(upper_cnt / max(1, len(text))),
            1.0 if "?" in text else 0.0
        ]

    def record_experience(
        self,
        user_input: str,
        system_reply: str,
        emotion_label: str = "neutral",
        rie_score: float = 0.8,
        latency_seconds: float = 0.5,
        perception_context_len: int = 0,
        circadian_phase: str = "Afternoon",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Experience:
        """Construct and record an experience unit."""
        now = time.time()
        exp_id = f"exp_{int(now * 1000)}"
        feat_vec = self.extract_feature_vector(user_input, latency_seconds, rie_score)

        # Implicit feedback score heuristic (higher RIE score & reasonable latency = higher feedback)
        feedback = min(1.0, max(0.0, (rie_score * 0.7) + (0.3 if latency_seconds < 3.0 else 0.1)))

        exp = Experience(
            experience_id=exp_id,
            timestamp=now,
            user_input=user_input,
            system_reply=system_reply,
            emotion_label=emotion_label,
            rie_score=rie_score,
            latency_seconds=latency_seconds,
            perception_context_len=perception_context_len,
            circadian_phase=circadian_phase,
            feedback_score=feedback,
            feature_vector=feat_vec,
            metadata=metadata or {}
        )

        with self._lock:
            self._buffer.append(exp)

        return exp

    def record_telemetry(self, metrics: Dict[str, Any]):
        """Record real-time system resource & performance telemetry."""
        with self._lock:
            metrics["timestamp"] = time.time()
            self._telemetry_history.append(metrics)

    def get_recent_experiences(self, limit: int = 50) -> List[Experience]:
        """Return the N most recent experiences."""
        with self._lock:
            return list(self._buffer)[-limit:]

    def get_telemetry_snapshot(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent telemetry records."""
        with self._lock:
            return list(self._telemetry_history)[-limit:]

    def get_buffer_size(self) -> int:
        with self._lock:
            return len(self._buffer)

_global_perception_layer: Optional[PerceptionLayer] = None
_perception_lock = threading.Lock()

def get_perception_layer() -> PerceptionLayer:
    global _global_perception_layer
    if _global_perception_layer is None:
        with _perception_lock:
            if _global_perception_layer is None:
                _global_perception_layer = PerceptionLayer()
    return _global_perception_layer
