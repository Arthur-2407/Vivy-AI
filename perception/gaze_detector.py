"""
perception/gaze_detector.py
============================
Vivy AI — Gaze & Eye Contact Engine
Performs real-time gaze estimation, eye contact scoring, head pose fusion,
blink frequency analysis, and pupil target mapping.

Outputs:
  - Gaze Direction: "Looking At Vivy", "Looking Away", "Looking Left/Right/Up/Down",
                    "Looking At Screen", "Looking At Keyboard", "Eyes Closed", "Unknown"
  - Eye Contact Score: 0.0 → 1.0
  - Eye Contact Strength: "Strong", "Medium", "Weak", "None"
  - Blink State: "Normal", "Long Blink", "Rapid Blink", "Eye Fatigue"
  - Pupil Look Target: Normalized screen target (x=0..1, y=0..1)
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from typing import List, Dict, Optional, Tuple, Any

from perception.perception_state import FaceData, GazeData, Point3D

logger = logging.getLogger(__name__)


class GazeDetector:
    """
    Real-time gaze and eye contact detector.
    """

    def __init__(self):
        self._blink_timestamps = deque(maxlen=60) # rolling window of blinks (seconds)
        self._last_blink_time: float = 0.0
        self._is_blinking_prev: bool = False
        self._blink_duration_start: float = 0.0
        
        # Temporal smoothing buffers
        self._gaze_history = deque(maxlen=15)
        self._contact_score_history = deque(maxlen=15)

    def estimate_gaze(self, faces: List[FaceData], frame_width: int = 640, frame_height: int = 480) -> GazeData:
        """
        Estimate gaze metrics from the primary visible face.
        """
        if not faces:
            return GazeData(
                gaze_direction="Unknown",
                gaze_confidence=0.0,
                eye_contact_score=0.0,
                eye_contact_strength="None",
                blink_frequency_bpm=0.0,
                blink_state="Normal",
                pupil_look_target=Point3D(x=0.5, y=0.5, z=0.0)
            )

        primary_face = faces[0]
        now = time.time()

        # 1. Blink Analysis
        is_blinking = primary_face.left_eye.is_blinking and primary_face.right_eye.is_blinking
        avg_ear = (primary_face.left_eye.ear + primary_face.right_eye.ear) / 2.0
        avg_openness = (primary_face.left_eye.eye_openness + primary_face.right_eye.eye_openness) / 2.0

        blink_state, bpm = self._update_blink_metrics(is_blinking, now)

        # 2. Eye Closed check
        if avg_openness < 0.15 or is_blinking:
            return GazeData(
                gaze_direction="Eyes Closed" if avg_openness < 0.15 else "Looking At Vivy",
                gaze_confidence=0.9,
                eye_contact_score=0.0 if avg_openness < 0.15 else 0.5,
                eye_contact_strength="None" if avg_openness < 0.15 else "Weak",
                blink_frequency_bpm=bpm,
                blink_state=blink_state,
                pupil_look_target=Point3D(x=0.5, y=0.5, z=0.0)
            )

        # 3. Head Pose & Pupil Target Mapping
        yaw = primary_face.head_pose.yaw
        pitch = primary_face.head_pose.pitch

        # Extract true ocular relative position if computed by landmark_detector
        pupil_x = 0.5
        pupil_y = 0.5
        
        # If eye_position is non-zero, landmark_detector successfully extracted relative positions
        if primary_face.left_eye.eye_position.x > 0 and primary_face.right_eye.eye_position.x > 0:
            pupil_x = (primary_face.left_eye.eye_position.x + primary_face.right_eye.eye_position.x) / 2.0
            pupil_y = (primary_face.left_eye.eye_position.y + primary_face.right_eye.eye_position.y) / 2.0

        # Normalize look target on screen (0.0 to 1.0)
        look_target_x = min(1.0, max(0.0, 0.5 + (yaw / 60.0) + (pupil_x - 0.5) * 0.5))
        look_target_y = min(1.0, max(0.0, 0.5 + (-pitch / 60.0) + (pupil_y - 0.5) * 0.5))

        # 4. Gaze Direction & Eye Contact Classification (Smoothed)
        raw_gaze_dir, raw_contact_score, _ = self._classify_gaze_direction(
            yaw=yaw, pitch=pitch, pupil_x=pupil_x, pupil_y=pupil_y
        )
        
        self._gaze_history.append(raw_gaze_dir)
        self._contact_score_history.append(raw_contact_score)
        
        # Temporal Validation: majority vote for gaze, average for score
        import statistics
        gaze_dir = statistics.mode(self._gaze_history)
        contact_score = sum(self._contact_score_history) / len(self._contact_score_history)
        
        # Re-derive strength from smoothed score
        if contact_score >= 0.75:
            contact_strength = "Strong"
        elif contact_score >= 0.45:
            contact_strength = "Medium"
        elif contact_score >= 0.20:
            contact_strength = "Weak"
        else:
            contact_strength = "None"

        return GazeData(
            gaze_direction=gaze_dir,
            gaze_confidence=round(min(1.0, primary_face.confidence * 0.95), 2),
            eye_contact_score=round(contact_score, 2),
            eye_contact_strength=contact_strength,
            blink_frequency_bpm=round(bpm, 1),
            blink_state=blink_state,
            pupil_look_target=Point3D(x=round(look_target_x, 3), y=round(look_target_y, 3), z=0.0)
        )

    # ── Internal Helpers ──────────────────────────────────────────────────────

    def _classify_gaze_direction(self, yaw: float, pitch: float, pupil_x: float, pupil_y: float) -> Tuple[str, float, str]:
        # Compute angular deviation from camera axis
        dev_angle = math.sqrt(yaw ** 2 + pitch ** 2)

        # Eye Contact Score: 1.0 when facing directly at camera, decaying with angle
        contact_score = max(0.0, min(1.0, 1.0 - (dev_angle / 35.0)))

        # Primary Gaze classification using true pupil geometry
        # pupil_x & y are normalized 0.0 -> 1.0, centered around 0.5.
        
        # Combine head pose dev angle with pupil deviation for a true eye-contact score
        gaze_yaw = yaw + (pupil_x - 0.5) * 80.0
        gaze_pitch = pitch + (pupil_y - 0.5) * 80.0
        gaze_deviation = math.sqrt(gaze_yaw**2 + gaze_pitch**2)
        
        contact_score = max(0.0, min(1.0, 1.0 - (gaze_deviation / 45.0)))

        # Classification thresholds strictly using pupil tracking
        if contact_score >= 0.70:
            gaze_dir = "Looking At Vivy"
            strength = "Strong"
        elif contact_score >= 0.40:
            gaze_dir = "Looking At Screen"
            strength = "Medium"
        elif pupil_y > 0.65:
            gaze_dir = "Looking At Keyboard" if (abs(pupil_x - 0.5) < 0.15) else "Looking Down"
            strength = "Weak"
        elif pupil_x < 0.35:
            gaze_dir = "Looking Left"
            strength = "Weak" if contact_score > 0.1 else "None"
        elif pupil_x > 0.65:
            gaze_dir = "Looking Right"
            strength = "Weak" if contact_score > 0.1 else "None"
        elif pupil_y < 0.25:
            gaze_dir = "Looking Up"
            strength = "None"
        else:
            gaze_dir = "Looking Away"
            strength = "None"

        return gaze_dir, contact_score, strength

    def _update_blink_metrics(self, is_blinking: bool, now: float) -> Tuple[str, float]:
        blink_state = "Normal"

        # Detect blink edge (start -> end)
        if is_blinking and not self._is_blinking_prev:
            self._blink_duration_start = now
        elif not is_blinking and self._is_blinking_prev:
            duration = now - self._blink_duration_start
            self._blink_timestamps.append(now)
            if duration > 0.4:
                blink_state = "Long Blink"

        self._is_blinking_prev = is_blinking

        # Calculate BPM from rolling window
        bpm = 15.0
        if len(self._blink_timestamps) >= 2:
            window_sec = now - self._blink_timestamps[0]
            if window_sec > 0:
                bpm = (len(self._blink_timestamps) / window_sec) * 60.0

        if bpm > 35:
            blink_state = "Rapid Blink"
        elif bpm < 6 and len(self._blink_timestamps) > 5:
            blink_state = "Eye Fatigue"

        return blink_state, bpm
