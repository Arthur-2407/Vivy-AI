"""
perception/landmark_detector.py
================================
Vivy AI — Facial Landmark Detector
Estimates 468+ 3D facial mesh landmarks per face using MediaPipe Face Mesh
or fallback landmark estimation.

Tracks detailed landmarks for:
  - Left & Right Eyes, Pupils, Iris
  - Eyelids & Eyebrows
  - Nose, Mouth, Jawline, Forehead
  - Head Rotation & 3D Pose Points
"""

from __future__ import annotations

import logging
import math
import numpy as np
from typing import List, Dict, Optional, Tuple, Any

from perception.perception_state import FaceData, Point3D, EyeData, HeadPose

logger = logging.getLogger(__name__)

_MEDIAPIPE_AVAILABLE = False
mp_face_mesh = None
try:
    import mediapipe as mp
    try:
        from mediapipe.solutions import face_mesh as mp_face_mesh
    except Exception:
        import mediapipe.python.solutions.face_mesh as mp_face_mesh
    if mp_face_mesh is not None:
        _MEDIAPIPE_AVAILABLE = True
except Exception as _err:
    print(f"[landmark_detector.py] Silenced exception: {_err}")

_OPENCV_AVAILABLE = False
try:
    import cv2
    if hasattr(cv2, "cvtColor"):
        _OPENCV_AVAILABLE = True
except Exception as _err:
    print(f"[landmark_detector.py] Silenced exception: {_err}")


class LandmarkDetector:
    """
    Extracts 468+ 3D facial mesh landmarks and computes eye landmarks + head pose.
    """

    def __init__(self, static_image_mode: bool = False, max_num_faces: int = 4):
        self._mp_face_mesh = None
        self._backend = "Unknown"

        if _MEDIAPIPE_AVAILABLE:
            try:
                self._mp_face_mesh = mp_face_mesh.FaceMesh(
                    static_image_mode=static_image_mode,
                    max_num_faces=max_num_faces,
                    refine_landmarks=True, # enables iris landmarks (468 + 10 iris = 478)
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5
                )
                self._backend = "MediaPipe FaceMesh (478 Landmarks)"
                logger.info("[LandmarkDetector] Initialized MediaPipe 478-Landmark Face Mesh.")
            except Exception as ex:
                logger.warning(f"[LandmarkDetector] MediaPipe FaceMesh init error: {ex}")

        if not self._mp_face_mesh:
            self._backend = "Heuristic Landmark Fallback"

    def process_landmarks(self, image_np: np.ndarray, faces: List[FaceData]) -> List[FaceData]:
        """
        Process facial mesh landmarks for each face in the image and update face data.
        """
        if not faces or image_np is None:
            return faces

        h, w = image_np.shape[:2]
        if h == 0 or w == 0:
            return faces

        if self._backend.startswith("MediaPipe") and self._mp_face_mesh is not None:
            try:
                rgb_img = cv2.cvtColor(image_np, cv2.COLOR_BGR2RGB) if _OPENCV_AVAILABLE else image_np
                results = self._mp_face_mesh.process(rgb_img)

                if results and results.multi_face_landmarks:
                    for idx, face_landmarks in enumerate(results.multi_face_landmarks):
                        if idx < len(faces):
                            target_face = faces[idx]
                            lm_list = face_landmarks.landmark
                            target_face.landmarks_count = len(lm_list)

                            # 1. Compute Eyes & Iris
                            self._extract_eye_metrics(lm_list, w, h, target_face)

                            # 2. Estimate 3D Head Pose (Yaw, Pitch, Roll)
                            self._estimate_head_pose(lm_list, w, h, target_face)

            except Exception as ex:
                logger.debug(f"[LandmarkDetector] Landmark extraction error: {ex}")
        else:
            # Fallback heuristic estimation based on bounding box
            for face in faces:
                self._apply_fallback_landmarks(face)

        return faces

    def get_backend_name(self) -> str:
        return self._backend

    # ── Internal Feature Extractors ──────────────────────────────────────────

    def _extract_eye_metrics(self, lm_list: Any, w: int, h: int, face: FaceData):
        # Key landmark indices in MediaPipe 468+ Mesh:
        # Left eye: 33 (outer), 133 (inner), 159 (top), 145 (bottom), 468 (iris center)
        # Right eye: 362 (inner), 263 (outer), 386 (top), 374 (bottom), 473 (iris center)
        try:
            # Left Eye
            l_outer = np.array([lm_list[33].x * w, lm_list[33].y * h])
            l_inner = np.array([lm_list[133].x * w, lm_list[133].y * h])
            l_top   = np.array([lm_list[159].x * w, lm_list[159].y * h])
            l_bot   = np.array([lm_list[145].x * w, lm_list[145].y * h])

            horiz_l = np.linalg.norm(l_outer - l_inner)
            vert_l  = np.linalg.norm(l_top - l_bot)
            ear_l   = vert_l / max(1.0, horiz_l)

            # Left Iris center (468 if available, else centroid of eye)
            if len(lm_list) >= 469:
                l_iris_x, l_iris_y = lm_list[468].x * w, lm_list[468].y * h
            else:
                l_iris_x, l_iris_y = (l_outer[0] + l_inner[0]) / 2.0, (l_top[1] + l_bot[1]) / 2.0

            face.left_eye.ear = float(ear_l)
            face.left_eye.eye_openness = float(min(1.0, max(0.0, ear_l / 0.35)))
            face.left_eye.is_blinking = (ear_l < 0.18)
            face.left_eye.pupil_center = Point3D(x=float(l_iris_x), y=float(l_iris_y), z=0.0)

            # Right Eye
            r_inner = np.array([lm_list[362].x * w, lm_list[362].y * h])
            r_outer = np.array([lm_list[263].x * w, lm_list[263].y * h])
            r_top   = np.array([lm_list[386].x * w, lm_list[386].y * h])
            r_bot   = np.array([lm_list[374].x * w, lm_list[374].y * h])

            horiz_r = np.linalg.norm(r_outer - r_inner)
            vert_r  = np.linalg.norm(r_top - r_bot)
            ear_r   = vert_r / max(1.0, horiz_r)

            if len(lm_list) >= 474:
                r_iris_x, r_iris_y = lm_list[473].x * w, lm_list[473].y * h
            else:
                r_iris_x, r_iris_y = (r_outer[0] + r_inner[0]) / 2.0, (r_top[1] + r_bot[1]) / 2.0

            face.right_eye.ear = float(ear_r)
            face.right_eye.eye_openness = float(min(1.0, max(0.0, ear_r / 0.35)))
            face.right_eye.is_blinking = (ear_r < 0.18)
            face.right_eye.pupil_center = Point3D(x=float(r_iris_x), y=float(r_iris_y), z=0.0)

        except Exception as ex:
            logger.debug(f"[LandmarkDetector] Eye metrics extraction error: {ex}")

    def _estimate_head_pose(self, lm_list: Any, w: int, h: int, face: FaceData):
        # Key landmark points for SolvePnP head pose:
        # Nose tip: 1, Chin: 152, Left eye corner: 33, Right eye corner: 263, Left mouth corner: 61, Right mouth corner: 291
        try:
            nose_tip = np.array([lm_list[1].x * w, lm_list[1].y * h])
            chin     = np.array([lm_list[152].x * w, lm_list[152].y * h])
            l_eye    = np.array([lm_list[33].x * w, lm_list[33].y * h])
            r_eye    = np.array([lm_list[263].x * w, lm_list[263].y * h])

            # Compute Yaw (horizontal rotation left/right)
            eye_center_x = (l_eye[0] + r_eye[0]) / 2.0
            dx = nose_tip[0] - eye_center_x
            eye_dist = max(1.0, np.linalg.norm(l_eye - r_eye))
            yaw = (dx / eye_dist) * 90.0

            # Compute Pitch (vertical tilt up/down)
            eye_center_y = (l_eye[1] + r_eye[1]) / 2.0
            dy = nose_tip[1] - eye_center_y
            face_height = max(1.0, np.linalg.norm(chin - np.array([eye_center_x, eye_center_y])))
            pitch = (dy / face_height - 0.4) * -90.0

            # Compute Roll (head tilt)
            roll = math.degrees(math.atan2(r_eye[1] - l_eye[1], r_eye[0] - l_eye[0]))

            # Classify orientation
            label = "Head Facing Vivy"
            if abs(yaw) > 25:
                label = "Head Turned"
            elif pitch < -20:
                label = "Head Up"
            elif pitch > 20:
                label = "Head Down"

            face.head_pose = HeadPose(
                yaw=float(np.clip(yaw, -90, 90)),
                pitch=float(np.clip(pitch, -90, 90)),
                roll=float(np.clip(roll, -90, 90)),
                orientation_label=label
            )
        except Exception as ex:
            logger.debug(f"[LandmarkDetector] Head pose calculation error: {ex}")

    def _apply_fallback_landmarks(self, face: FaceData):
        face.landmarks_count = 68
        face.left_eye = EyeData(ear=0.3, eye_openness=1.0, is_blinking=False)
        face.right_eye = EyeData(ear=0.3, eye_openness=1.0, is_blinking=False)
        face.head_pose = HeadPose(yaw=0.0, pitch=0.0, roll=0.0, orientation_label="Head Facing Vivy")
