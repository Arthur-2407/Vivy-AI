"""
perception/perception_guard.py
================================
Vivy AI — Perception Claim Guard

Centralizes the confidence-threshold policy for all downstream visual claim
generation. Enforces the strict no-fake-perception rule:

  - All visual claims must originate from real, validated detector outputs.
  - If a detection is heuristic or confidence < threshold: return honest response.
  - Heuristic detections NEVER produce strong visual claims.

Architecture
------------
  conversation.py (and any future code making visual claims)
      │
      └── perception_guard.is_face_claimable(face_dict)
          perception_guard.is_object_claimable(obj_dict)
          perception_guard.is_gaze_claimable(gaze_dict)
              │
              └── If False → honest_uncertainty_response(query_type)

Usage
-----
  from perception.perception_guard import is_face_claimable, honest_uncertainty_response

  if is_face_claimable(perception_state.get("primary_face")):
      return f"Yes, I can see your face clearly!"
  else:
      return honest_uncertainty_response("face")
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Confidence Thresholds ─────────────────────────────────────────────────────
# These are the minimum confidence values required for Vivy to make a strong
# visual claim. Below these values, Vivy must use honest uncertainty language.

#: Minimum confidence to claim "I can see your face clearly"
FACE_CLAIM_MIN_CONFIDENCE: float = 0.50

#: Minimum confidence to claim "I can see [object]"
OBJECT_CLAIM_MIN_CONFIDENCE: float = 0.50

#: Minimum gaze_confidence to claim gaze direction or eye contact state
GAZE_CLAIM_MIN_CONFIDENCE: float = 0.40

#: Minimum face confidence to report emotion state
EMOTION_CLAIM_MIN_CONFIDENCE: float = 0.60


# ── Core Claim Validators ─────────────────────────────────────────────────────

def is_face_claimable(face_data: Optional[Dict[str, Any]]) -> bool:
    """
    Return True only if this face detection is reliable enough for Vivy to
    make strong visual claims (e.g., "I can see your face clearly").

    A detection is NOT claimable if:
      - face_data is None or empty
      - validation_state is "heuristic" (pixel-variance fallback)
      - validation_state is "undetected"
      - confidence < FACE_CLAIM_MIN_CONFIDENCE
    """
    if not face_data or not isinstance(face_data, dict):
        return False
    state = face_data.get("validation_state", "undetected")
    if state in ("heuristic", "undetected"):
        logger.debug(f"[PerceptionGuard] Face rejected: validation_state={state!r}")
        return False
    conf = float(face_data.get("confidence", 0.0))
    if conf < FACE_CLAIM_MIN_CONFIDENCE:
        logger.debug(f"[PerceptionGuard] Face rejected: confidence={conf:.2f} < {FACE_CLAIM_MIN_CONFIDENCE}")
        return False
    return True


def is_object_claimable(obj_data: Optional[Dict[str, Any]]) -> bool:
    """
    Return True only if this object detection is reliable enough for Vivy to
    say "I can see [object]".

    A detection is NOT claimable if:
      - obj_data is None or empty
      - validation_state is "heuristic" (contour region proposal)
      - confidence < OBJECT_CLAIM_MIN_CONFIDENCE
    """
    if not obj_data or not isinstance(obj_data, dict):
        return False
    state = obj_data.get("validation_state", "verified")
    if state == "heuristic":
        logger.debug(f"[PerceptionGuard] Object rejected: validation_state=heuristic ({obj_data.get('label', '?')})")
        return False
    conf = float(obj_data.get("confidence", 0.0))
    if conf < OBJECT_CLAIM_MIN_CONFIDENCE:
        logger.debug(f"[PerceptionGuard] Object rejected: confidence={conf:.2f} < {OBJECT_CLAIM_MIN_CONFIDENCE}")
        return False
    return True


def is_gaze_claimable(gaze_data: Optional[Dict[str, Any]]) -> bool:
    """
    Return True only if the gaze data has sufficient confidence for Vivy to
    report gaze direction or eye contact strength.

    A gaze is NOT claimable if:
      - gaze_data is None or empty
      - validation_state is "undetected"
      - gaze_confidence < GAZE_CLAIM_MIN_CONFIDENCE
    """
    if not gaze_data or not isinstance(gaze_data, dict):
        return False
    state = gaze_data.get("validation_state", "undetected")
    if state == "undetected":
        return False
    conf = float(gaze_data.get("gaze_confidence", 0.0))
    if conf < GAZE_CLAIM_MIN_CONFIDENCE:
        return False
    return True


def is_emotion_claimable(face_data: Optional[Dict[str, Any]]) -> bool:
    """
    Return True only if the emotion data embedded in a face detection has
    sufficient confidence to make an emotional claim.
    """
    if not face_data or not isinstance(face_data, dict):
        return False
    emotion = face_data.get("emotion", {})
    if not emotion:
        return False
    label = emotion.get("label", "undetected")
    if label in ("undetected", "neutral") and emotion.get("confidence", 0.0) == 0.0:
        return False
    return float(emotion.get("confidence", 0.0)) >= EMOTION_CLAIM_MIN_CONFIDENCE


def filter_claimable_objects(objects: list) -> list:
    """
    Filter a list of object dicts, returning only those that pass is_object_claimable.
    Safe to call with None or empty lists.
    """
    if not objects:
        return []
    return [o for o in objects if isinstance(o, dict) and is_object_claimable(o)]


# ── Honest Uncertainty Responses ──────────────────────────────────────────────

def honest_uncertainty_response(query_type: str = "general") -> str:
    """
    Return an honest, warm, on-persona response when perception data is not
    reliable enough to make a visual claim.

    Parameters
    ----------
    query_type : str
        One of: "face", "object", "gaze", "emotion", "shirt", "general"
    """
    _RESPONSES: Dict[str, str] = {
        "face": (
            "I couldn't detect your face with enough confidence right now. "
            "Make sure you're facing the camera in good light!"
        ),
        "object": (
            "I'm not confident enough to identify what's in the frame. "
            "Try centering the object closer to the camera!"
        ),
        "gaze": (
            "I can see the camera is active, but I couldn't determine your "
            "gaze direction with confidence. Are you facing the camera?"
        ),
        "emotion": (
            "I couldn't determine your emotional state with confidence right now."
        ),
        "shirt": (
            "My camera is active, but fine details like clothing color require "
            "better lighting or a clearer camera angle right now!"
        ),
        "general": (
            "I couldn't determine that with enough confidence right now. "
            "Make sure the camera is active and well-lit!"
        ),
    }
    return _RESPONSES.get(query_type, _RESPONSES["general"])


# ── Convenience: Build face claim guard from full perception_state ─────────────

def get_primary_face_claim_status(perception_state: Optional[Dict[str, Any]]) -> tuple[bool, Optional[Dict]]:
    """
    Convenience function: given the full perception_state dict, determine
    if the primary face is claimable and return it.

    Returns
    -------
    (is_claimable: bool, face_dict: Optional[Dict])
    """
    if not perception_state:
        return False, None
    face_dict = perception_state.get("primary_face")
    if not face_dict:
        # Fallback: check face_count only
        if perception_state.get("face_count", 0) > 0 and perception_state.get("camera_active", False):
            # face_count > 0 but no primary_face dict — can't verify quality
            return False, None
        return False, None
    return is_face_claimable(face_dict), face_dict
