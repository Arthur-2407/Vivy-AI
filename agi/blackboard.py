"""
Vivy AI — Cognitive Blackboard System
====================================
Thread-safe shared memory architectural pattern for complex AI coordination.
Enables specialized cognitive sub-engines (Vision, Memory, Planner, Emotion, 
World Model, Reasoner, LLM) to publish state hypotheses and subscribe to shared
cognitive channels without tight inter-module coupling.
"""

import time
import threading
from typing import Dict, List, Any, Optional

class CognitiveBlackboard:
    """
    Central shared workspace for all Vivy cognitive subsystems.
    Maintains active hypothesis frames, perceptual events, goals, and reflections.
    """
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "CognitiveBlackboard":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self, max_channel_history: int = 50):
        self._lock = threading.RLock()
        self.max_channel_history = max_channel_history
        # Shared state storage organized by subsystem channel name
        self.state_channels: Dict[str, Any] = {}
        # Chronological event log of cognitive assertions
        self.event_stream: List[Dict[str, Any]] = []
        # Registered hypothesis frames for cross-domain synthesis
        self.hypotheses: Dict[str, Dict[str, Any]] = {}
        # Sub-engine heartbeat tracking
        self.subsystem_heartbeats: Dict[str, float] = {}

    def publish_state(self, channel: str, data: Any, source_engine: str = "unknown") -> None:
        """
        Publishes or replaces the canonical current state for a given cognitive channel
        (e.g., 'emotion_state', 'vision_gaze', 'world_context', 'current_plan').
        """
        with self._lock:
            now = time.time()
            self.state_channels[channel] = {
                "data": data,
                "source": source_engine,
                "timestamp": now
            }
            self.subsystem_heartbeats[source_engine] = now
            
            # Log event in stream
            event = {
                "type": "STATE_PUBLISHED",
                "channel": channel,
                "source": source_engine,
                "timestamp": now,
                "summary": str(data)[:100] if not isinstance(data, dict) else f"dict_keys({list(data.keys())})"
            }
            self.event_stream.append(event)
            if len(self.event_stream) > self.max_channel_history * 5:
                self.event_stream = self.event_stream[-self.max_channel_history * 2:]

    def get_state(self, channel: str, default: Any = None) -> Any:
        """Retrieves the current payload stored in a given cognitive channel."""
        with self._lock:
            entry = self.state_channels.get(channel)
            return entry["data"] if entry else default

    def assert_hypothesis(self, hypothesis_id: str, proposition: str, confidence: float, source_engine: str, evidence: Optional[List[str]] = None) -> None:
        """
        Registers an active cognitive hypothesis (e.g., 'User is stressed about code compilation').
        Subsystems can inspect, endorse, or contradict active hypotheses.
        """
        with self._lock:
            now = time.time()
            self.hypotheses[hypothesis_id] = {
                "id": hypothesis_id,
                "proposition": proposition,
                "confidence": float(max(0.0, min(1.0, confidence))),
                "source": source_engine,
                "evidence": evidence or [],
                "timestamp": now
            }
            self.subsystem_heartbeats[source_engine] = now

    def rescind_hypothesis(self, hypothesis_id: str) -> bool:
        """Removes a hypothesis if invalidated or archived."""
        with self._lock:
            if hypothesis_id in self.hypotheses:
                del self.hypotheses[hypothesis_id]
                return True
            return False

    def get_active_hypotheses(self, min_confidence: float = 0.5) -> List[Dict[str, Any]]:
        """Returns a list of high-confidence active cognitive hypotheses."""
        with self._lock:
            results = []
            for h in self.hypotheses.values():
                if h["confidence"] >= min_confidence:
                    results.append(dict(h))
            return sorted(results, key=lambda x: x["confidence"], reverse=True)

    def synthesize_cognitive_snapshot(self) -> Dict[str, Any]:
        """
        Synthesizes a holistic snapshot of all active cognitive channels and hypotheses,
        formatted for immediate injection into reasoning prompts or telemetry dashboards.
        """
        with self._lock:
            snapshot = {}
            for ch, entry in self.state_channels.items():
                snapshot[ch] = entry["data"]
            snapshot["active_hypotheses"] = [
                f"{h['proposition']} (conf: {int(h['confidence']*100)}%)" 
                for h in self.get_active_hypotheses(min_confidence=0.4)
            ]
            snapshot["heartbeats"] = dict(self.subsystem_heartbeats)
            return snapshot

    def clear_transients(self) -> None:
        """Clears short-term conversational event streams while preserving durable states."""
        with self._lock:
            self.event_stream.clear()

_global_blackboard = None
def get_cognitive_blackboard() -> CognitiveBlackboard:
    global _global_blackboard
    if _global_blackboard is None:
        _global_blackboard = CognitiveBlackboard.get_instance()
    return _global_blackboard
