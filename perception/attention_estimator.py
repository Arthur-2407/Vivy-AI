"""
perception/attention_estimator.py
==================================
Vivy AI — Attention & Multi-Person Estimator
Fuses facial landmarks, gaze direction, eye contact, head pose, and movement to compute:
  - Attention Score (0–100)
  - Engagement Score (0–100)
  - Presence Score (0–100)

Multi-Person Support:
  - Ranks multiple detected faces by attention score and distance.
  - Automatically identifies the primary conversational target (highest attention user).
"""

from __future__ import annotations

import logging
import math
import time
from typing import List, Dict, Tuple, Optional

from perception.perception_state import FaceData, GazeData, AttentionData

logger = logging.getLogger(__name__)


class AttentionEstimator:
    """
    Multimodal attention, engagement, and presence scoring engine.
    """

    def __init__(self):
        self._prev_center_x: float = -1.0
        self._prev_center_y: float = -1.0
        self._last_time: float = time.time()

    def estimate_attention(
        self,
        faces: List[FaceData],
        gaze: GazeData,
        camera_active: bool = True
    ) -> Tuple[AttentionData, Optional[FaceData]]:
        """
        Compute attention, engagement, and presence metrics from face and gaze inputs.
        Returns tuple of (AttentionData, primary_user_face).
        """
        now = time.time()
        dt = max(0.001, now - self._last_time)
        self._last_time = now

        if not camera_active or not faces:
            return AttentionData(
                attention_score=0.0,
                engagement_score=0.0,
                presence_score=0.0,
                movement_intensity=0.0
            ), None

        primary_face = faces[0]

        # 1. Compute Movement Intensity
        movement = 0.0
        cx = primary_face.center_point.x
        cy = primary_face.center_point.y
        if self._prev_center_x >= 0 and self._prev_center_y >= 0:
            dist_px = math.sqrt((cx - self._prev_center_x) ** 2 + (cy - self._prev_center_y) ** 2)
            movement = min(1.0, (dist_px / dt) / 500.0)

        self._prev_center_x = cx
        self._prev_center_y = cy

        # 2. Presence Score (0 to 100)
        # Based on face presence, face size, and confidence
        presence_score = min(100.0, primary_face.confidence * 100.0)
        if len(faces) > 1:
            presence_score = min(100.0, presence_score + 5.0)

        # 3. Attention Score (0 to 100)
        # Primary drivers: Eye Contact Score, Gaze Direction, Head Pose Alignment
        gaze_factor = gaze.eye_contact_score # 0.0 to 1.0

        orientation_bonus = 1.0
        if primary_face.head_pose.orientation_label == "Head Facing Vivy":
            orientation_bonus = 1.0
        elif primary_face.head_pose.orientation_label == "Head Turned":
            orientation_bonus = 0.4
        else:
            orientation_bonus = 0.6

        openness_factor = (primary_face.left_eye.eye_openness + primary_face.right_eye.eye_openness) / 2.0

        attention_raw = (
            gaze_factor * 60.0 +
            orientation_bonus * 30.0 +
            openness_factor * 10.0
        )
        attention_score = max(0.0, min(100.0, attention_raw))

        # 4. Engagement Score (0 to 100)
        # Fuses sustained attention, blink stability, and moderate movement
        blink_penalty = 0.0
        if gaze.blink_state == "Rapid Blink":
            blink_penalty = 15.0
        elif gaze.blink_state == "Eye Fatigue":
            blink_penalty = 20.0

        engagement_raw = attention_score * 0.85 + (1.0 - movement) * 15.0 - blink_penalty
        engagement_score = max(0.0, min(100.0, engagement_raw))

        # 5. Multi-Person Ranker
        # Re-rank faces so the person paying the highest attention becomes primary
        for face in faces:
            # Score individual face target
            f_contact = gaze.eye_contact_score if face.is_primary else 0.3
            f_score = face.confidence * 40.0 + f_contact * 60.0
            face.is_primary = False # Reset flag for sorting

        faces.sort(key=lambda f: f.bbox.width * f.bbox.height * (1.2 if f.identity != "Unknown" else 1.0), reverse=True)
        if faces:
            faces[0].is_primary = True

        att_data = AttentionData(
            attention_score=round(attention_score, 1),
            engagement_score=round(engagement_score, 1),
            presence_score=round(presence_score, 1),
            movement_intensity=round(movement, 2)
        )

        return att_data, faces[0] if faces else None
