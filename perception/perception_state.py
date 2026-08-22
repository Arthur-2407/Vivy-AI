"""
perception/perception_state.py
===============================
Vivy AI — Perception System State Definitions
Data models for face detection, tracking, gaze estimation, landmark detection,
attention scoring, presence state management, and hardware scheduler telemetry.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional


@dataclass
class BoundingBox:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass
class HandData:
    """Dataclass representing a tracked hand."""
    hand_label: str  # "Left", "Right"
    confidence: float
    bbox: BoundingBox
    center_point: Point3D
    tracking_id: int = 0
    holding_item: bool = False
    gesture: str = "Open Palm"  # "Open Palm", "Closed Fist", "Pinch/Holding", "Pointing"
    gesture_phase: str = "IDLE" # IDLE, CANDIDATE, CONFIRMED, COOLDOWN
    gesture_confidence: float = 0.0
    gesture_newly_confirmed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hand_label": self.hand_label,
            "confidence": round(float(self.confidence), 2),
            "bbox": self.bbox.to_dict(),
            "center_point": self.center_point.to_dict(),
            "holding_item": self.holding_item,
            "gesture": self.gesture,
            "gesture_phase": self.gesture_phase,
            "gesture_confidence": round(float(self.gesture_confidence), 2),
            "gesture_newly_confirmed": self.gesture_newly_confirmed,
        }


@dataclass
class ObjectData:
    """Dataclass representing a detected object in frame."""
    tracking_id: int
    label: str
    confidence: float
    bbox: BoundingBox
    center_point: Point3D
    category: str = "general"
    validation_state: str = "verified"  # verified | heuristic | hand_held

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tracking_id": self.tracking_id,
            "label": self.label,
            "confidence": round(float(self.confidence), 2),
            "bbox": self.bbox.to_dict(),
            "center_point": self.center_point.to_dict(),
            "category": self.category,
            "validation_state": self.validation_state,
        }


@dataclass
class Point3D:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {"x": round(self.x, 3), "y": round(self.y, 3), "z": round(self.z, 3)}


@dataclass
class HeadPose:
    yaw: float = 0.0    # Left (-) / Right (+)
    pitch: float = 0.0  # Down (-) / Up (+)
    roll: float = 0.0   # Tilt left/right
    orientation_label: str = "Head Facing Vivy"  # Facing Vivy, Turned, Down, Up

    def to_dict(self) -> Dict[str, Any]:
        return {
            "yaw": round(self.yaw, 2),
            "pitch": round(self.pitch, 2),
            "roll": round(self.roll, 2),
            "orientation_label": self.orientation_label,
        }


@dataclass
class EyeData:
    eye_position: Point3D = field(default_factory=Point3D)
    pupil_center: Point3D = field(default_factory=Point3D)
    ear: float = 0.3          # Eye Aspect Ratio
    eye_openness: float = 1.0 # 0.0 (closed) to 1.0 (fully open)
    is_blinking: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eye_position": self.eye_position.to_dict(),
            "pupil_center": self.pupil_center.to_dict(),
            "ear": round(self.ear, 3),
            "eye_openness": round(self.eye_openness, 3),
            "is_blinking": self.is_blinking,
        }


@dataclass
class FaceData:
    tracking_id: int = 0
    bbox: BoundingBox = field(default_factory=BoundingBox)
    confidence: float = 0.0
    center_point: Point3D = field(default_factory=Point3D)
    distance_estimate: float = 1.0  # meters approx
    head_pose: HeadPose = field(default_factory=HeadPose)
    landmarks_count: int = 0
    landmarks: List[Point3D] = field(default_factory=list)
    left_eye: EyeData = field(default_factory=EyeData)
    right_eye: EyeData = field(default_factory=EyeData)
    identity: str = "Unknown"
    is_primary: bool = True
    # Emotion defaults to "undetected" — emotion_confidence=0.0 means no inference was run
    emotion_label: str = "undetected"
    emotion_confidence: float = 0.0
    valence: float = 0.0
    arousal: float = 0.0

    source: str = "camera"
    validation_state: str = "verified"
    missing_frames: int = 0
    latency_ms: float = 0.0
    quality: float = 1.0
    freshness: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tracking_id": self.tracking_id,
            "bbox": self.bbox.to_dict(),
            "confidence": round(self.confidence, 3),
            "center_point": self.center_point.to_dict(),
            "distance_estimate": round(self.distance_estimate, 2),
            "head_pose": self.head_pose.to_dict(),
            "landmarks_count": self.landmarks_count,
            "landmarks": [p.to_dict() for p in self.landmarks],
            "left_eye": self.left_eye.to_dict(),
            "right_eye": self.right_eye.to_dict(),
            "identity": self.identity,
            "is_primary": self.is_primary,
            "emotion": {
                "label": self.emotion_label,
                "confidence": round(self.emotion_confidence, 2),
                "valence": round(self.valence, 2),
                "arousal": round(self.arousal, 2)
            },
            "source": self.source,
            "validation_state": self.validation_state,
            "latency_ms": round(self.latency_ms, 2),
            "quality": round(self.quality, 2),
            "freshness": round(self.freshness, 2),
        }


@dataclass
class GazeData:
    # Defaults are deliberately zeroed — "unknown until a detector provides real data"
    gaze_direction: str = "Unknown"
    gaze_confidence: float = 0.0
    eye_contact_score: float = 0.0      # 0.0 to 1.0  (0.0 = no data, not looking)
    eye_contact_strength: str = "None" # Strong, Medium, Weak, None
    blink_frequency_bpm: float = 0.0
    blink_state: str = "Normal"        # Normal, Long Blink, Rapid Blink, Fatigue
    pupil_look_target: Point3D = field(default_factory=Point3D) # Normalized screen target (0-1)
    source: str = "gaze_detector"
    validation_state: str = "undetected"  # undetected | heuristic | verified
    latency_ms: float = 0.0
    quality: float = 0.0
    freshness: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gaze_direction": self.gaze_direction,
            "gaze_confidence": round(self.gaze_confidence, 2),
            "eye_contact_score": round(self.eye_contact_score, 2),
            "eye_contact_strength": self.eye_contact_strength,
            "blink_frequency_bpm": round(self.blink_frequency_bpm, 1),
            "blink_state": self.blink_state,
            "pupil_look_target": self.pupil_look_target.to_dict(),
            "source": self.source,
            "validation_state": self.validation_state,
            "latency_ms": round(self.latency_ms, 2),
            "quality": round(self.quality, 2),
            "freshness": round(self.freshness, 2),
        }


@dataclass
class AttentionData:
    attention_score: float = 100.0   # 0 to 100
    engagement_score: float = 100.0  # 0 to 100
    presence_score: float = 100.0    # 0 to 100
    movement_intensity: float = 0.0
    source: str = "attention_estimator"
    validation_state: str = "verified"
    latency_ms: float = 0.0
    quality: float = 1.0
    freshness: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attention_score": round(self.attention_score, 1),
            "engagement_score": round(self.engagement_score, 1),
            "presence_score": round(self.presence_score, 1),
            "movement_intensity": round(self.movement_intensity, 2),
            "source": self.source,
            "validation_state": self.validation_state,
            "latency_ms": round(self.latency_ms, 2),
            "quality": round(self.quality, 2),
            "freshness": round(self.freshness, 2),
        }


@dataclass
class HardwareSchedulerState:
    backend: str = "CPU"               # CPU, CUDA, DirectML, Vulkan, ONNX
    mode: str = "Avatar OFF Mode"      # Avatar OFF Mode, Avatar ON Mode, Balanced Hybrid Mode
    cpu_utilization: float = 0.0       # percent
    gpu_utilization: float = 0.0       # percent
    vram_used_mb: float = 0.0
    vram_total_mb: float = 0.0
    fps: float = 30.0
    perception_latency_ms: float = 0.0
    migration_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "mode": self.mode,
            "cpu_utilization": round(self.cpu_utilization, 1),
            "gpu_utilization": round(self.gpu_utilization, 1),
            "vram_used_mb": round(self.vram_used_mb, 1),
            "vram_total_mb": round(self.vram_total_mb, 1),
            "fps": round(self.fps, 1),
            "perception_latency_ms": round(self.perception_latency_ms, 1),
            "migration_count": self.migration_count,
        }


@dataclass
class PerceptionSystemState:
    camera_active: bool = False
    camera_fps: float = 0.0
    presence_state: str = "User Missing" # User Present, User Missing, User Returned, Multiple People
    primary_face: Optional[FaceData] = None
    all_faces: List[FaceData] = field(default_factory=list)
    gaze: GazeData = field(default_factory=GazeData)
    attention: AttentionData = field(default_factory=AttentionData)
    hardware: HardwareSchedulerState = field(default_factory=HardwareSchedulerState)
    hand_state: Dict[str, Any] = field(default_factory=dict)
    objects: List[ObjectData] = field(default_factory=list)
    held_objects: List[Dict[str, Any]] = field(default_factory=list)
    object_in_hand: bool = False
    hand_object_confidence: float = 0.0
    gesture_enabled: bool = True
    gesture_state: str = "IDLE"
    gesture_suppression_reason: Optional[str] = None
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "camera_active": self.camera_active,
            "camera_fps": round(self.camera_fps, 1),
            "presence_state": self.presence_state,
            "primary_face": self.primary_face.to_dict() if self.primary_face else None,
            "all_faces": [f.to_dict() for f in self.all_faces],
            "face_count": len(self.all_faces),
            "face_detected": len(self.all_faces) > 0,
            "user_visible": self.camera_active and len(self.all_faces) > 0 and self.presence_state in ("User Present", "User Returned", "Multiple People"),
            "visual_input_available": self.camera_active,
            "eye_contact_available": self.camera_active and len(self.all_faces) > 0 and self.gaze.eye_contact_score > 0.0,
            "gaze": self.gaze.to_dict(),
            "attention": self.attention.to_dict(),
            "hardware": self.hardware.to_dict(),
            "hand_state": self.hand_state,
            "objects": [o.to_dict() for o in self.objects],
            "held_objects": self.held_objects,
            "object_in_hand": self.object_in_hand,
            "hand_object_confidence": round(self.hand_object_confidence, 2),
            "gesture_enabled": self.gesture_enabled,
            "gesture_state": self.gesture_state,
            "gesture_suppression_reason": self.gesture_suppression_reason,
            "updated_at": self.updated_at,
        }

    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "camera_active": self.camera_active,
            "face_detected": len(self.all_faces) > 0,
            "user_visible": self.camera_active and len(self.all_faces) > 0 and self.presence_state in ("User Present", "User Returned", "Multiple People"),
            "visual_input_available": self.camera_active,
            "eye_contact_available": self.camera_active and len(self.all_faces) > 0 and self.gaze.eye_contact_score > 0.0,
        }
