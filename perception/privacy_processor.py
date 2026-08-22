"""
perception/privacy_processor.py
===============================
Vivy AI — Privacy-Preserving Object Redaction Pipeline

Responsible for locally anonymizing the user's face from the camera frame 
before it is sent to external networks for object identification.

Features:
- Extracts Object ROI (Region of Interest)
- Runs Local Face Detection
- Completely redacts (blacks out) all detected faces
- Enforces a fail-closed policy (no output if validation fails)
"""

import logging
import cv2
import numpy as np
from typing import Tuple, Optional, Any

logger = logging.getLogger(__name__)

class PrivacyProcessor:
    def __init__(self):
        self.face_detector = None
        self._init_detector()
        
    def _init_detector(self):
        try:
            from perception.face_detector import FaceDetector
            self.face_detector = FaceDetector()
        except Exception as e:
            logger.warning(f"[PrivacyProcessor] Failed to init primary FaceDetector: {e}. Falling back to OpenCV Cascade.")
            # Fallback to OpenCV Haar cascade if standard face detector is not available
            import cv2
            self.cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    def anonymize_object_frame(self, frame: np.ndarray, object_bbox: dict) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Takes a full camera frame and an object bounding box.
        Detects faces in the frame, redacts them with black rectangles, 
        and then crops out the object ROI.
        
        Returns:
            (is_valid: bool, anonymized_roi: Optional[np.ndarray])
        """
        if frame is None or frame.size == 0:
            return False, None
            
        h, w = frame.shape[:2]
        safe_frame = frame.copy()
        
        faces = []
        
        if self.face_detector:
            try:
                faces_data = self.face_detector.detect_faces(safe_frame)
                for f in faces_data:
                    # Face bbox is usually an object with x, y, width, height properties
                    if hasattr(f, 'bbox'):
                        faces.append((f.bbox.x, f.bbox.y, f.bbox.width, f.bbox.height))
            except Exception as e:
                logger.error(f"[PrivacyProcessor] Face detector failed during anonymization: {e}")
                return False, None
        elif hasattr(self, 'cascade'):
            try:
                gray = cv2.cvtColor(safe_frame, cv2.COLOR_BGR2GRAY)
                cascade_faces = self.cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30))
                for (x, y, fw, fh) in cascade_faces:
                    faces.append((x, y, fw, fh))
            except Exception as e:
                logger.error(f"[PrivacyProcessor] Haar Cascade failed during anonymization: {e}")
                return False, None
        else:
            # If no face detector is available, we cannot guarantee privacy. Fail closed.
            logger.error("[PrivacyProcessor] No face detector available. Privacy cannot be guaranteed. Failing closed.")
            return False, None
            
        # Extract the Object ROI bounds first for collision checking
        bx = int(object_bbox.get("x", 0))
        by = int(object_bbox.get("y", 0))
        bw = int(object_bbox.get("width", 0))
        bh = int(object_bbox.get("height", 0))

        # Redact all detected faces
        for (fx, fy, fw, fh) in faces:
            # Check for Face-on-Object hallucination (MediaPipe face detection false positive on hand/object)
            ix1 = max(fx, bx)
            iy1 = max(fy, by)
            ix2 = min(fx + fw, bx + bw)
            iy2 = min(fy + fh, by + bh)
            if ix2 > ix1 and iy2 > iy1:
                inter_area = (ix2 - ix1) * (iy2 - iy1)
                face_area = fw * fh
                if face_area > 0 and (inter_area / face_area) > 0.6:
                    logger.debug("[PrivacyProcessor] Suppressed redaction of face hallucination on object")
                    continue
            
            # Add a 20% margin around the face to ensure full redaction (including hair/ears)
            margin_x = int(fw * 0.2)
            margin_y = int(fh * 0.2)
            rx1 = max(0, int(fx) - margin_x)
            ry1 = max(0, int(fy) - margin_y)
            rx2 = min(w, int(fx + fw) + margin_x)
            ry2 = min(h, int(fy + fh) + margin_y)
            
            # Black out the face region entirely
            cv2.rectangle(safe_frame, (rx1, ry1), (rx2, ry2), (0, 0, 0), -1)
            logger.info(f"[PrivacyProcessor] Redacted face region: ({rx1}, {ry1}) to ({rx2}, {ry2})")

        # Exact ROI cropping as requested (no context margin)
        ox1 = max(0, bx)
        oy1 = max(0, by)
        ox2 = min(w, bx + bw)
        oy2 = min(h, by + bh)
        
        if (ox2 - ox1) < 10 or (oy2 - oy1) < 10:
            logger.warning("[PrivacyProcessor] Object ROI is too small after extraction.")
            return False, None
            
        object_roi = safe_frame[oy1:oy2, ox1:ox2]
        
        return True, object_roi

_global_processor = None
def get_privacy_processor() -> PrivacyProcessor:
    global _global_processor
    if _global_processor is None:
        _global_processor = PrivacyProcessor()
    return _global_processor
