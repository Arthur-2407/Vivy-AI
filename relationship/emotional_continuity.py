"""
relationship/emotional_continuity.py
====================================
Implements Cross-Session Emotional Continuity & Conversational Anticipation for Vivy AI.
Humans don't restart every conversation with generic greetings ("Hello! How may I help you?").
If yesterday the user said "I'm nervous about my interview" or "I'm travelling tomorrow",
today Vivy anticipates and opens with:
  "So... how did your interview go?" or "Did you reach your destination safely?"
"""

import time
import re
import threading
from typing import Dict, Any, List, Optional

class EmotionalContinuityEngine:
    """Manages persistent emotional context across distinct conversation sessions and days."""

    def __init__(self, initial_state: Optional[Dict[str, Any]] = None):
        self._lock = threading.RLock()
        state = initial_state or {}
        # List of unresolved emotional items: {"topic": str, "emotion": str, "timestamp": float, "follow_up_phrase": str, "resolved": bool}
        self.pending_anticipations: List[Dict[str, Any]] = list(state.get("pending_anticipations", []))

    def assimilate_turn_for_anticipation(self, user_text: str, current_mood: str = "neutral") -> None:
        """
        Scans dialogue for anticipatory anchors (interviews, tests, travel, doctor appointments, stress, sleep)
        and queues emotionally natural follow-up check-ins for subsequent sessions.
        """
        with self._lock:
            if not user_text or len(user_text.strip()) < 5:
                return
            u_clean = user_text.lower()

            # Anticipation heuristics without hardcoding response limits
            if any(w in u_clean for w in ["interview", "exam", "test", "presentation", "meeting tomorrow"]):
                self._queue_followup("important event / interview", "Nervous / Excited", "So... how did your interview and important event go? I've been thinking about you! 🌟")
            elif any(w in u_clean for w in ["travelling", "traveling", "flight", "road trip", "flying tomorrow"]):
                self._queue_followup("travel", "Caring / Attentive", "Did you reach your destination safely? Hope your journey went smoothly! 😊")
            elif any(w in u_clean for w in ["sick", "doctor", "not feeling well", "fever", "headache", "cold"]):
                self._queue_followup("health recovery", "Empathetic / Warm", "How are you feeling today? I was worried about you — did you get enough rest? ❤️")
            elif any(w in u_clean for w in ["had a terrible day", "bad day", "really sad", "feeling down", "stressed out"]):
                self._queue_followup("emotional support check-in", "Gentle / Empathetic", "I was thinking about our chat yesterday... how is your heart feeling today? I'm right here with you. 🌸")

    def _queue_followup(self, topic: str, emotion: str, follow_up_phrase: str) -> None:
        for item in self.pending_anticipations:
            if item["topic"] == topic and not item["resolved"]:
                item["timestamp"] = time.time()
                return
        self.pending_anticipations.append({
            "topic": topic,
            "emotion": emotion,
            "timestamp": time.time(),
            "follow_up_phrase": follow_up_phrase,
            "resolved": False
        })

    def get_session_opening_anticipation(self, time_since_last_turn_sec: float = 3600.0) -> Optional[str]:
        """
        Returns a proactive companion follow-up question if a new session starts after a break
        and there is an pending anticipatory emotional memory.
        """
        with self._lock:
            # Require at least a 2-hour separation (or testing force) to count as a new session check-in
            for item in reversed(self.pending_anticipations):
                if not item["resolved"] and (time.time() - item["timestamp"] >= 30.0 or time_since_last_turn_sec >= 120.0):
                    item["resolved"] = True
                    return item["follow_up_phrase"]
            return None

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {"pending_anticipations": list(self.pending_anticipations)}
