"""
perception/perception_events.py
================================
Vivy AI — Perception Event Bus
Decoupled event broadcasting system for real-time perception state events.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Callable, Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Event Name Constants
EVENT_FACE_DETECTED       = "face_detected"
EVENT_FACE_LOST           = "face_lost"
EVENT_GAZE_CHANGED        = "gaze_changed"
EVENT_ATTENTION_CHANGED   = "attention_changed"
EVENT_EYE_CONTACT_STARTED = "eye_contact_started"
EVENT_EYE_CONTACT_LOST    = "eye_contact_lost"
EVENT_PRESENCE_DETECTED   = "presence_detected"
EVENT_PRESENCE_LOST       = "presence_lost"
EVENT_USER_RETURNED       = "user_returned"
EVENT_MULTIPLE_FACES      = "multiple_faces"


class PerceptionEventHub:
    """
    Thread-safe event hub that manages subscribers and dispatches events asynchronously
    or synchronously to subscribers without blocking perception loops.
    Includes sliding-window deduplication to suppress duplicate event emissions.
    """

    def __init__(self, dedup_window_seconds: float = 0.5):
        self._subscribers: Dict[str, List[Callable[[str, Dict[str, Any]], None]]] = {}
        self._lock = threading.Lock()
        self._dedup_window = dedup_window_seconds
        self._recent_event_fingerprints: Dict[str, float] = {}

    def subscribe(self, event_type: str, callback: Callable[[str, Dict[str, Any]], None]):
        """Subscribe a callback to a specific event_type, or '*' for all events."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)
            logger.debug(f"[PerceptionEventHub] Callback registered for '{event_type}'.")

    def unsubscribe(self, event_type: str, callback: Callable[[str, Dict[str, Any]], None]):
        """Unsubscribe callback from event_type."""
        with self._lock:
            if event_type in self._subscribers and callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)

    def publish(self, event_type: str, data: Optional[Dict[str, Any]] = None, async_dispatch: bool = True):
        """
        Publish an event to all registered listeners with sliding-window deduplication.
        If async_dispatch is True, dispatches to subscribers in background thread workers.
        """
        now = time.time()
        payload = data or {}

        # Construct fingerprint for deduplication (excluding timestamp)
        try:
            clean_payload = {k: v for k, v in payload.items() if k not in ("timestamp", "event_type")}
            payload_str = json.dumps(clean_payload, sort_keys=True, default=str)
            fingerprint = f"{event_type}:{payload_str}"
        except Exception:
            fingerprint = f"{event_type}:{str(payload)}"

        with self._lock:
            # Clean up old fingerprints
            expired_keys = [k for k, t in self._recent_event_fingerprints.items() if (now - t) > self._dedup_window]
            for k in expired_keys:
                del self._recent_event_fingerprints[k]

            # Check if this exact event was published recently
            if fingerprint in self._recent_event_fingerprints:
                if (now - self._recent_event_fingerprints[fingerprint]) < self._dedup_window:
                    logger.debug(f"[PerceptionEventHub] Deduplicated event emission '{event_type}'.")
                    return

            self._recent_event_fingerprints[fingerprint] = now

            targets = list(self._subscribers.get(event_type, []))
            wildcards = list(self._subscribers.get("*", []))

        all_targets = targets + wildcards
        if not all_targets:
            return

        payload.setdefault("timestamp", now)
        payload.setdefault("event_type", event_type)

        def _dispatch():
            for cb in all_targets:
                try:
                    cb(event_type, payload)
                except Exception as ex:
                    logger.error(f"[PerceptionEventHub] Listener error on '{event_type}': {ex}")

        if async_dispatch:
            threading.Thread(target=_dispatch, daemon=True, name=f"EventDispatch-{event_type}").start()
        else:
            _dispatch()


_hub_instance: Optional[PerceptionEventHub] = None
_hub_lock = threading.Lock()


def get_event_hub() -> PerceptionEventHub:
    """Get or create global process-level PerceptionEventHub singleton."""
    global _hub_instance
    if _hub_instance is None:
        with _hub_lock:
            if _hub_instance is None:
                _hub_instance = PerceptionEventHub()
    return _hub_instance
