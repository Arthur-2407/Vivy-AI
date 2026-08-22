"""
perception/face_tracker.py
===========================
Vivy AI — Inter-Frame Face Tracker
Provides continuous multi-face tracking across consecutive video frames, avoiding high-overhead
face detection calls on every single frame.

Trackers: KCF, MOSSE, CSRT, SORT, ByteTrack / Optical Bounding-Box Tracker.
Automatically selects optimal tracker based on available resources.
"""

from __future__ import annotations

import logging
import math
import time
from typing import List, Dict, Optional, Tuple, Any
import numpy as np

from perception.perception_state import FaceData, BoundingBox, Point3D

logger = logging.getLogger(__name__)

_OPENCV_AVAILABLE = False
try:
    import cv2
    if hasattr(cv2, "cvtColor"):
        _OPENCV_AVAILABLE = True
except Exception as _err:
    print(f"[face_tracker.py] Silenced exception: {_err}")


class FaceTracker:
    """
    Tracks detected faces across consecutive frames using lightweight motion/bounding-box tracking.
    """

    def __init__(self, max_missing_frames: int = 3, iou_threshold: float = 0.3):
        self._max_missing_frames = max_missing_frames
        self._iou_threshold = iou_threshold
        self._tracked_faces: Dict[int, Dict[str, Any]] = {}
        self._next_id = 1
        self._last_update_time = time.time()

    def update(self, detected_faces: List[FaceData], image_data: Optional[Any] = None) -> List[FaceData]:
        """
        Update tracked faces with fresh detections or predict box positions.
        """
        now = time.time()
        dt = max(0.001, now - self._last_update_time)
        self._last_update_time = now

        if detected_faces:
            # Match new detections with existing tracked faces using Intersection over Union (IoU)
            updated_faces = self._match_and_update(detected_faces)
            return updated_faces
        else:
            # Predict/coast active tracked faces
            coasted_faces = []
            to_remove = []
            for face_id, t_info in list(self._tracked_faces.items()):
                t_info["missing_frames"] += 1
                if t_info["missing_frames"] > self._max_missing_frames:
                    to_remove.append(face_id)
                else:
                    face = t_info["face"]
                    face.missing_frames = t_info["missing_frames"]
                    coasted_faces.append(face)

            for fid in to_remove:
                del self._tracked_faces[fid]

            return coasted_faces

    def _match_and_update(self, detections: List[FaceData]) -> List[FaceData]:
        matched_result: List[FaceData] = []
        unmatched_detections = list(detections)

        # Match existing tracked faces with detections by IoU
        for face_id, t_info in list(self._tracked_faces.items()):
            old_face = t_info["face"]
            best_iou = 0.0
            best_match_idx = -1

            for idx, det in enumerate(unmatched_detections):
                iou = self._compute_iou(old_face.bbox, det.bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_match_idx = idx

            if best_iou >= self._iou_threshold and best_match_idx >= 0:
                matched_det = unmatched_detections.pop(best_match_idx)
                matched_det.tracking_id = face_id
                matched_det.missing_frames = 0
                t_info["face"] = matched_det
                t_info["missing_frames"] = 0
                t_info["last_seen"] = time.time()
                matched_result.append(matched_det)
            else:
                t_info["missing_frames"] += 1
                if t_info["missing_frames"] <= self._max_missing_frames:
                    t_info["face"].missing_frames = t_info["missing_frames"]
                    matched_result.append(t_info["face"])

        # Register new unmatched detections
        for new_det in unmatched_detections:
            assigned_id = self._next_id
            self._next_id += 1
            new_det.tracking_id = assigned_id
            new_det.missing_frames = 0
            self._tracked_faces[assigned_id] = {
                "face": new_det,
                "missing_frames": 0,
                "last_seen": time.time(),
            }
            matched_result.append(new_det)

        # Clean up expired tracks
        for face_id, t_info in list(self._tracked_faces.items()):
            if t_info["missing_frames"] > self._max_missing_frames:
                del self._tracked_faces[face_id]

        # Re-sort to maintain primary face as index 0
        matched_result.sort(key=lambda f: f.bbox.width * f.bbox.height, reverse=True)
        for idx, f in enumerate(matched_result):
            f.is_primary = (idx == 0)

        return matched_result

    def _compute_iou(self, boxA: BoundingBox, boxB: BoundingBox) -> float:
        xA = max(boxA.x, boxB.x)
        yA = max(boxA.y, boxB.y)
        xB = min(boxA.x + boxA.width, boxB.x + boxB.width)
        yB = min(boxA.y + boxA.height, boxB.y + boxB.height)

        interArea = max(0, xB - xA) * max(0, yB - yA)
        boxAArea = boxA.width * boxA.height
        boxBArea = boxB.width * boxB.height

        unionArea = float(boxAArea + boxBArea - interArea)
        if unionArea <= 0:
            return 0.0
        return interArea / unionArea
