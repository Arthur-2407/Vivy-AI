"""
presence/presence_manager.py
==============================
Vivy AI — Presence State Engine
Continuously monitors user presence state and broadcasts lifecycle presence events.

States:
  - User Present: Active single user detected in view.
  - User Missing: No faces visible in camera view.
  - User Returned: User entered view after being missing.
  - Multiple People: Two or more faces detected simultaneously.
  - Unknown: Camera inactive or initializing.

Broadcasts events via perception_events.py:
  presence_detected, presence_lost, user_returned, multiple_faces_detected
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

from perception.perception_state import FaceData
from perception.perception_events import (
    get_event_hub,
    EVENT_PRESENCE_DETECTED,
    EVENT_PRESENCE_LOST,
    EVENT_USER_RETURNED,
    EVENT_MULTIPLE_FACES,
)

logger = logging.getLogger(__name__)


class PresenceManager:
    """
    Presence state machine and lifecycle event generator.
    """

    STATE_PRESENT   = "User Present"
    STATE_MISSING   = "User Missing"
    STATE_RETURNED  = "User Returned"
    STATE_MULTIPLE  = "Multiple People"
    STATE_UNKNOWN   = "Unknown"

    def __init__(self, missing_grace_seconds: float = 3.0):
        self._missing_grace_seconds = missing_grace_seconds

        self._current_state = self.STATE_UNKNOWN
        self._last_face_seen_time: float = 0.0
        self._was_missing: bool = False
        self._state_start_time: float = time.time()

    def update_presence(self, faces: List[FaceData], camera_active: bool = True) -> str:
        """
        Evaluate current face detections and transition presence state.
        Returns the new presence_state string.
        """
        now = time.time()
        hub = get_event_hub()

        if not camera_active:
            new_state = self.STATE_UNKNOWN
            self._transition_to(new_state)
            return self._current_state

        face_count = len(faces)

        if face_count > 0:
            self._last_face_seen_time = now
            if face_count > 1:
                new_state = self.STATE_MULTIPLE
                if self._current_state != self.STATE_MULTIPLE:
                    hub.publish(EVENT_MULTIPLE_FACES, {"face_count": face_count})
            elif self._was_missing:
                new_state = self.STATE_RETURNED
                hub.publish(EVENT_USER_RETURNED, {"returned_at": now})
                hub.publish(EVENT_PRESENCE_DETECTED, {"face_count": 1})
                self._was_missing = False
            else:
                new_state = self.STATE_PRESENT
                if self._current_state == self.STATE_UNKNOWN or self._current_state == self.STATE_MISSING:
                    hub.publish(EVENT_PRESENCE_DETECTED, {"face_count": 1})
        else:
            # Check grace period before flipping to User Missing
            time_since_seen = now - self._last_face_seen_time
            if time_since_seen > self._missing_grace_seconds:
                new_state = self.STATE_MISSING
                if self._current_state != self.STATE_MISSING:
                    hub.publish(EVENT_PRESENCE_LOST, {"last_seen": self._last_face_seen_time})
                    self._was_missing = True
            else:
                new_state = self._current_state

        self._transition_to(new_state)
        return self._current_state

    def get_state(self) -> str:
        return self._current_state

    def _transition_to(self, new_state: str):
        if self._current_state != new_state:
            old_state = self._current_state
            self._current_state = new_state
            self._state_start_time = time.time()
            logger.info(f"[PresenceManager] State transition: '{old_state}' ──► '{new_state}'")
