"""
perception/face_detector.py
============================
Vivy AI — Hardware-Adaptive Face Detector
Detects visible faces in image frames with automatic model selection according to hardware capability:
  1. MediaPipe Face Detection (Fast CPU/GPU neural detector)
  2. OpenCV YuNet DNN Face Detector (ONNX runtime)
  3. OpenCV Haar Cascade (Lightweight CPU fallback)

Outputs Face Data: Face ID, Bounding Box, Confidence, Center Point, Distance Estimate, Head Pose.
"""

from __future__ import annotations

import base64
import logging
import os
import math
import time
import numpy as np
from typing import List, Optional, Tuple, Any, Dict

from perception.perception_state import FaceData, BoundingBox, Point3D, HeadPose
from perception.hardware_scheduler import get_hardware_scheduler

logger = logging.getLogger(__name__)

# ── Confidence policy constants ──────────────────────────────────────────────
# Downstream code may gate on this: only trust faces above this threshold
# for making visual claims (gaze direction, eye contact, etc.)
HEURISTIC_CONFIDENCE_THRESHOLD = 0.50  # Below this = heuristic only, do not make strong claims

# Check backend availability
_MEDIAPIPE_AVAILABLE = False
mp_face_detection = None
try:
    import mediapipe as mp
    try:
        from mediapipe.solutions import face_detection as mp_face_detection
    except Exception:
        import mediapipe.python.solutions.face_detection as mp_face_detection
    if mp_face_detection is not None:
        _MEDIAPIPE_AVAILABLE = True
except Exception as _err:
    print(f"[face_detector.py] Silenced exception: {_err}")

_OPENCV_AVAILABLE = False
try:
    import cv2
    if hasattr(cv2, "cvtColor") and hasattr(cv2, "imdecode"):
        _OPENCV_AVAILABLE = True
except Exception as _err:
    print(f"[face_detector.py] Silenced exception: {_err}")

try:
    from PIL import Image
    from io import BytesIO
except ImportError:
    pass

# ── RetinaFace ONNX Backend ──────────────────────────────────────────────────
_ONNXRUNTIME_AVAILABLE = False
_ort = None
try:
    import onnxruntime as _ort
    _ONNXRUNTIME_AVAILABLE = True
except ImportError:
    pass

# ── InsightFace Embedding Backend ────────────────────────────────────────────
_INSIGHTFACE_AVAILABLE = False
try:
    import insightface
    _INSIGHTFACE_AVAILABLE = True
except ImportError:
    pass


class FaceDetector:
    """
    Hardware-adaptive multi-face detector.

    Backend priority chain (auto mode):
      1. RetinaFace ONNX (GPU → CPU)  — highest accuracy, production-grade
      2. MediaPipe Face Detection     — fast CPU/GPU neural detector
      3. OpenCV Haar Cascade          — lightweight CPU fallback
      4. Pixel-variance heuristic     — last-resort presence hint

    InsightFace embedding runs as a post-detection enrichment step when
    the model weights are available (optional, does not gate detection).
    """

    def __init__(self, min_detection_confidence: float = 0.5):
        self._confidence_threshold = min_detection_confidence
        self._mp_face_detection = None
        self._haar_cascade = None
        self._yunet_net = None
        self._current_backend = "Unknown"

        # RetinaFace ONNX session
        self._retinaface_session = None
        self._retinaface_input_size = (640, 640)

        # InsightFace embedding model
        self._insightface_session = None
        self._insightface_embedding_dim = 512

        # Load config-driven settings
        self._cfg = self._load_model_config()

        self._init_detector()

    @staticmethod
    def _load_model_config() -> Dict[str, Any]:
        """Load face detection config from perception config_loader."""
        try:
            from perception.config_loader import get, get_absolute_path
            return {
                "backend":               get("perception_models", "face_detection", default={}).get("backend", "auto") if isinstance(get("perception_models", "face_detection", default={}), dict) else "auto",
                "device":                get("perception_models", "face_detection", default={}).get("device", "auto") if isinstance(get("perception_models", "face_detection", default={}), dict) else "auto",
                "retinaface_model_path": get_absolute_path(
                    get("perception_models", "face_detection", default={}).get("retinaface_model_path", "models/retinaface/det_10g.onnx") if isinstance(get("perception_models", "face_detection", default={}), dict) else "models/retinaface/det_10g.onnx"
                ),
                "retinaface_input_size": get("perception_models", "face_detection", default={}).get("retinaface_input_size", [640, 640]) if isinstance(get("perception_models", "face_detection", default={}), dict) else [640, 640],
                "embedding_enabled":     get("perception_models", "face_embedding", default={}).get("enabled", True) if isinstance(get("perception_models", "face_embedding", default={}), dict) else True,
                "insightface_model_path": get_absolute_path(
                    get("perception_models", "face_embedding", default={}).get("insightface_model_path", "models/insightface/buffalo_l.onnx") if isinstance(get("perception_models", "face_embedding", default={}), dict) else "models/insightface/buffalo_l.onnx"
                ),
            }
        except Exception as ex:
            logger.debug(f"[FaceDetector] Config loader unavailable: {ex}. Using defaults.")
            return {
                "backend": "auto",
                "device": "auto",
                "retinaface_model_path": "",
                "retinaface_input_size": [640, 640],
                "embedding_enabled": True,
                "insightface_model_path": "",
            }

    def _resolve_device(self) -> str:
        """Resolve 'auto' device preference to 'cpu' or 'gpu' via hardware scheduler."""
        device_pref = self._cfg.get("device", "auto")
        if device_pref in ("cpu", "gpu"):
            return device_pref
        # Auto: ask the hardware scheduler
        hw_scheduler = get_hardware_scheduler()
        return hw_scheduler.get_assignment("face_detection")

    def _init_detector(self):
        """Initialize available detection models in priority order."""
        initialized_any = False
        backend_pref = self._cfg.get("backend", "auto")

        # 0. Try RetinaFace ONNX (highest priority when backend=auto or retinaface)
        if backend_pref in ("auto", "retinaface") and _ONNXRUNTIME_AVAILABLE:
            try:
                model_path = self._cfg.get("retinaface_model_path", "")
                if model_path and os.path.exists(model_path):
                    device = self._resolve_device()
                    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if device == "gpu" else ["CPUExecutionProvider"]
                    # Filter to only available providers
                    available_providers = _ort.get_available_providers()
                    providers = [p for p in providers if p in available_providers] or ["CPUExecutionProvider"]
                    self._retinaface_session = _ort.InferenceSession(model_path, providers=providers)
                    input_size_cfg = self._cfg.get("retinaface_input_size", [640, 640])
                    self._retinaface_input_size = (int(input_size_cfg[0]), int(input_size_cfg[1]))
                    self._current_backend = f"RetinaFace ONNX ({providers[0].replace('ExecutionProvider', '')})"
                    initialized_any = True
                    logger.info(f"[FaceDetector] Initialized RetinaFace ONNX backend: {self._current_backend}")
                else:
                    logger.info(f"[FaceDetector] RetinaFace model not found at '{model_path}'. Falling back.")
            except Exception as ex:
                logger.warning(f"[FaceDetector] Failed to init RetinaFace ONNX: {ex}")

        # 1. Try MediaPipe Face Detection
        if (not initialized_any or backend_pref == "auto") and _MEDIAPIPE_AVAILABLE and backend_pref in ("auto", "mediapipe"):
            try:
                self._mp_face_detection = mp_face_detection.FaceDetection(
                    min_detection_confidence=self._confidence_threshold,
                    model_selection=0 # 0 for short range (<2m)
                )
                if not initialized_any:
                    self._current_backend = "MediaPipe"
                initialized_any = True
                logger.info("[FaceDetector] Initialized MediaPipe Face Detection backend.")
            except Exception as ex:
                logger.warning(f"[FaceDetector] Failed to init MediaPipe Face Detection: {ex}")

        # 2. Try OpenCV Haar Cascade (always loaded as secondary fallback)
        if _OPENCV_AVAILABLE:
            try:
                cascade_path = ""
                if hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
                    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                if cascade_path and os.path.exists(cascade_path):
                    self._haar_cascade = cv2.CascadeClassifier(cascade_path)
                    if not initialized_any:
                        self._current_backend = "OpenCV Haar"
                    initialized_any = True
                    logger.info("[FaceDetector] Initialized OpenCV Haar Cascade backend.")
            except Exception as ex:
                logger.warning(f"[FaceDetector] Failed to init OpenCV Haar Cascade: {ex}")

        # 3. Try InsightFace embedding model (post-detection enrichment, not a detector)
        if self._cfg.get("embedding_enabled", True) and _ONNXRUNTIME_AVAILABLE:
            try:
                emb_path = self._cfg.get("insightface_model_path", "")
                if emb_path and os.path.exists(emb_path):
                    device = self._resolve_device()
                    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if device == "gpu" else ["CPUExecutionProvider"]
                    available_providers = _ort.get_available_providers()
                    providers = [p for p in providers if p in available_providers] or ["CPUExecutionProvider"]
                    self._insightface_session = _ort.InferenceSession(emb_path, providers=providers)
                    logger.info(f"[FaceDetector] InsightFace embedding model loaded ({providers[0]}).")
                else:
                    logger.info(f"[FaceDetector] InsightFace model not found at '{emb_path}'. Identity embedding disabled.")
            except Exception as ex:
                logger.warning(f"[FaceDetector] Failed to init InsightFace embedding: {ex}")

        if not initialized_any:
            self._current_backend = "Fallback Heuristic"
            logger.info("[FaceDetector] Operating with fallback heuristic backend.")

    def detect_faces(self, image_data: Any) -> List[FaceData]:
        """
        Detect faces in image frame.
        Accepts: OpenCV BGR numpy array, PIL Image, or base64 JPEG string.
        Returns list of FaceData objects sorted by face size (largest first).
        """
        img_np, h, w = self._to_numpy_bgr(image_data)
        if img_np is None or w < 10 or h < 10:
            return []

        # Ensure correct C-contiguous uint8 array layout
        if not isinstance(img_np, np.ndarray) or img_np.dtype != np.uint8 or not img_np.flags['C_CONTIGUOUS']:
            try:
                img_np = np.ascontiguousarray(img_np, dtype=np.uint8)
            except Exception as e:
                logger.debug(f"[FaceDetector] Array conversion failed: {e}")
                return []

        hw_scheduler = get_hardware_scheduler()
        device_target = hw_scheduler.get_assignment("face_detection")

        faces: List[FaceData] = []
        start_t = time.time()

        # Backend 0: RetinaFace ONNX Primary Pass
        if self._current_backend.startswith("RetinaFace ONNX") and self._retinaface_session is not None:
            try:
                faces = self._detect_retinaface(img_np, h, w)
            except Exception as ex:
                logger.debug(f"[FaceDetector] RetinaFace ONNX detection error: {ex}")

        # Backend 1: MediaPipe Primary & Adaptive Pass
        if (not faces or self._current_backend == "MediaPipe") and self._mp_face_detection is not None:
            try:
                rgb_img = cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB) if _OPENCV_AVAILABLE else img_np
                rgb_img = np.ascontiguousarray(rgb_img, dtype=np.uint8)
                results = self._mp_face_detection.process(rgb_img)
                if results and results.detections:
                    for idx, det in enumerate(results.detections):
                        score = det.score[0] if det.score else self._confidence_threshold
                        if score < self._confidence_threshold:
                            continue

                        bbox_relative = det.location_data.relative_bounding_box
                        bx = int(max(0, bbox_relative.xmin * w))
                        by = int(max(0, bbox_relative.ymin * h))
                        bw = int(min(w - bx, max(0, bbox_relative.width * w)))
                        bh = int(min(h - by, max(0, bbox_relative.height * h)))

                        # Filter out invalid or microscopic bounding boxes (< 15px)
                        if bw < 15 or bh < 15:
                            continue
                        
                        cx = bx + bw / 2.0
                        cy = by + bh / 2.0
                        
                        # Distance estimation heuristic based on face size ratio relative to frame width
                        face_ratio = bw / float(w) if w > 0 else 0.2
                        dist_m = max(0.3, min(3.0, 0.4 / max(0.05, face_ratio)))
                        
                        # Extract keypoints for yaw/pitch heuristic
                        yaw = 0.0
                        pitch = 0.0
                        if hasattr(det.location_data, 'relative_keypoints') and len(det.location_data.relative_keypoints) >= 3:
                            kps = det.location_data.relative_keypoints
                            # kps[0] = right eye, kps[1] = left eye, kps[2] = nose tip
                            eyes_mid_x = (kps[0].x + kps[1].x) / 2.0
                            nose_x = kps[2].x
                            
                            eyes_mid_y = (kps[0].y + kps[1].y) / 2.0
                            nose_y = kps[2].y
                            
                            dx = nose_x - eyes_mid_x
                            dy = nose_y - eyes_mid_y
                            
                            if bbox_relative.width > 0:
                                yaw = (dx / bbox_relative.width) * 100.0  # Approx scaling
                            if bbox_relative.height > 0:
                                # Normal face has nose ~25% down from eyes
                                pitch = -((dy / bbox_relative.height) - 0.25) * 100.0
                                
                        orientation = "Head Facing Vivy"
                        if yaw < -20: orientation = "Head Turned Left"
                        elif yaw > 20: orientation = "Head Turned Right"
                        elif pitch > 20: orientation = "Head Turned Up"
                        elif pitch < -20: orientation = "Head Turned Down"
                        
                        face = FaceData(
                            tracking_id=idx + 1,
                            bbox=BoundingBox(x=bx, y=by, width=bw, height=bh),
                            confidence=float(score),
                            center_point=Point3D(x=round(cx, 1), y=round(cy, 1), z=round(dist_m, 2)),
                            distance_estimate=round(dist_m, 2),
                            head_pose=HeadPose(yaw=round(yaw, 2), pitch=round(pitch, 2), roll=0.0, orientation_label=orientation),
                            identity="User",
                            is_primary=(idx == 0)
                        )
                        faces.append(face)
            except Exception as ex:
                logger.debug(f"[FaceDetector] MediaPipe detection error: {ex}")

        # Backend 2: OpenCV Haar Cascade with CLAHE Low-Light & Multi-Scale Fallback
        # DISABLED: This fallback causes severe "Ghost Face" hallucinations on textured walls (CRITICAL BUG).
        if False and not faces and _OPENCV_AVAILABLE and self._haar_cascade is not None:
            try:
                gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY) if len(img_np.shape) == 3 else img_np
                haar_faces = self._haar_cascade.detectMultiScale(
                    gray, scaleFactor=1.06, minNeighbors=3, minSize=(60, 60)
                )
                # Low-light / contrast CLAHE fallback if 0 faces found
                if len(haar_faces) == 0:
                    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                    eq_gray = clahe.apply(gray)
                    haar_faces = self._haar_cascade.detectMultiScale(
                        eq_gray, scaleFactor=1.05, minNeighbors=2, minSize=(60, 60)
                    )

                for idx, (bx, by, bw, bh) in enumerate(haar_faces):
                    bx, by, bw, bh = int(bx), int(by), int(bw), int(bh)
                    if bw < 60 or bh < 60:
                        continue

                    cx = bx + bw / 2.0
                    cy = by + bh / 2.0
                    face_ratio = bw / float(w) if w > 0 else 0.2
                    dist_m = max(0.3, min(3.0, 0.4 / max(0.05, face_ratio)))

                    face = FaceData(
                        tracking_id=idx + 1,
                        bbox=BoundingBox(x=bx, y=by, width=bw, height=bh),
                        confidence=0.85,
                        center_point=Point3D(x=round(cx, 1), y=round(cy, 1), z=round(dist_m, 2)),
                        distance_estimate=round(dist_m, 2),
                        head_pose=HeadPose(yaw=0.0, pitch=0.0, roll=0.0, orientation_label="Head Facing Vivy"),
                        identity="User",
                        is_primary=(idx == 0)
                    )
                    faces.append(face)
            except Exception as ex:
                logger.debug(f"[FaceDetector] Haar detection error: {ex}")

        # Backend 3: Active Camera Feed Heuristic Candidate (Skin-Tone / Luminance Feature Detection)
        # IMPORTANT: This is a HEURISTIC, not a real face detection.
        # It only signals that the camera frame has visual variation (a person *may* be present).
        # confidence=0.40 and validation_state="heuristic" prevent downstream fabrication.
        if not faces and img_np is not None:
            try:
                fh, fw = img_np.shape[:2]
                if fh >= 40 and fw >= 40:
                    ymin, ymax = int(fh * 0.15), int(fh * 0.75)
                    xmin, xmax = int(fw * 0.20), int(fw * 0.80)
                    roi = img_np[ymin:ymax, xmin:xmax]
                    if roi.size > 0:
                        mean_bgr = np.mean(roi, axis=(0, 1))
                        std_bgr = np.std(roi, axis=(0, 1))
                        # Active camera feed check: std > 12 means frame contains feature variations
                        if float(np.sum(std_bgr)) > 12.0 and float(np.mean(mean_bgr)) > 15.0:
                            bw = int(fw * 0.35)
                            bh = int(fh * 0.45)
                            bx = int((fw - bw) / 2.0)
                            by = int(fh * 0.20)
                            cx = bx + bw / 2.0
                            cy = by + bh / 2.0
                            face = FaceData(
                                tracking_id=1,
                                bbox=BoundingBox(x=bx, y=by, width=bw, height=bh),
                                confidence=0.40,   # Low confidence: pixel-variance heuristic only
                                center_point=Point3D(x=round(cx, 1), y=round(cy, 1), z=0.5),
                                distance_estimate=0.5,
                                head_pose=HeadPose(yaw=0.0, pitch=0.0, roll=0.0, orientation_label="Head Facing Vivy"),
                                identity="Unknown",  # Never claim identity from a heuristic
                                is_primary=True,
                                validation_state="heuristic"  # Gate flag for downstream
                            )
                            # DO NOT append this fake face to downstream pipeline. It causes ghost boxes.
                            logger.debug("[FaceDetector] Heuristic candidate produced and suppressed from UI (telemetry only)")
            except Exception as ex_f:
                logger.debug(f"[FaceDetector] Fallback heuristic error: {ex_f}")

        # Sort faces by area (largest face first = primary user)
        faces.sort(key=lambda f: f.bbox.width * f.bbox.height, reverse=True)
        for idx, f in enumerate(faces):
            f.is_primary = (idx == 0)
            f.tracking_id = idx + 1

        # Post-detection enrichment: InsightFace identity embedding
        if self._insightface_session is not None and faces and img_np is not None:
            try:
                self._enrich_with_embeddings(faces, img_np, h, w)
            except Exception as ex:
                logger.debug(f"[FaceDetector] InsightFace embedding error: {ex}")

        # Log metrics to VisionHealthMonitor
        try:
            from perception.pipeline_validator import get_vision_health_monitor
            elapsed_ms = (time.time() - start_t) * 1000.0
            get_vision_health_monitor().record_frame(latency_ms=elapsed_ms, detected_faces=len(faces))
        except Exception as _err:
            print(f"[face_detector.py] Silenced exception: {_err}")

        return faces

    def get_backend_name(self) -> str:
        return self._current_backend

    # ── RetinaFace ONNX Detection ────────────────────────────────────────────

    def _detect_retinaface(self, img_np: np.ndarray, h: int, w: int) -> List[FaceData]:
        """
        Run RetinaFace ONNX inference on a BGR image.
        Returns list of FaceData with high-confidence bounding boxes.
        """
        faces: List[FaceData] = []
        session = self._retinaface_session
        if session is None:
            return faces

        input_name = session.get_inputs()[0].name
        input_shape = session.get_inputs()[0].shape  # e.g. [1, 3, 640, 640]

        # Determine expected spatial dimensions from model input shape
        target_h = int(input_shape[2]) if len(input_shape) >= 4 else self._retinaface_input_size[1]
        target_w = int(input_shape[3]) if len(input_shape) >= 4 else self._retinaface_input_size[0]

        # Letterbox resize: scale preserving aspect ratio, pad with grey
        scale = min(target_w / w, target_h / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        resized = cv2.resize(img_np, (new_w, new_h)) if _OPENCV_AVAILABLE else img_np

        padded = np.full((target_h, target_w, 3), 128, dtype=np.uint8)
        pad_x = (target_w - new_w) // 2
        pad_y = (target_h - new_h) // 2
        padded[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized

        # HWC→CHW, BGR→RGB, normalize to [0,1], add batch dim
        blob = padded[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
        blob = np.expand_dims(blob, axis=0)

        outputs = session.run(None, {input_name: blob})

        # Parse outputs — RetinaFace models typically output:
        #   scores [N], bboxes [N, 4], landmarks [N, 10]
        # Output order varies by model export; we handle common layouts.
        if len(outputs) >= 2:
            # Attempt to identify scores and bboxes from output shapes
            scores_arr = None
            bboxes_arr = None
            for out in outputs:
                arr = np.squeeze(out)
                if arr.ndim == 1 or (arr.ndim == 2 and arr.shape[1] == 1):
                    scores_arr = arr.flatten()
                elif arr.ndim == 2 and arr.shape[1] == 4:
                    bboxes_arr = arr

            if scores_arr is not None and bboxes_arr is not None:
                for idx in range(len(scores_arr)):
                    score = float(scores_arr[idx])
                    if score < self._confidence_threshold:
                        continue

                    x1, y1, x2, y2 = bboxes_arr[idx]
                    # Unscale from padded/resized coordinates back to original frame
                    x1 = (float(x1) - pad_x) / scale
                    y1 = (float(y1) - pad_y) / scale
                    x2 = (float(x2) - pad_x) / scale
                    y2 = (float(y2) - pad_y) / scale

                    bx = int(max(0, x1))
                    by = int(max(0, y1))
                    bw = int(min(w, x2) - bx)
                    bh = int(min(h, y2) - by)

                    if bw < 15 or bh < 15:
                        continue

                    cx = bx + bw / 2.0
                    cy = by + bh / 2.0
                    face_ratio = bw / float(w) if w > 0 else 0.2
                    dist_m = max(0.3, min(3.0, 0.4 / max(0.05, face_ratio)))

                    face = FaceData(
                        tracking_id=idx + 1,
                        bbox=BoundingBox(x=bx, y=by, width=bw, height=bh),
                        confidence=float(score),
                        center_point=Point3D(x=round(cx, 1), y=round(cy, 1), z=round(dist_m, 2)),
                        distance_estimate=round(dist_m, 2),
                        head_pose=HeadPose(yaw=0.0, pitch=0.0, roll=0.0, orientation_label="Head Facing Vivy"),
                        identity="User",
                        is_primary=(idx == 0)
                    )
                    faces.append(face)

        return faces

    # ── InsightFace Identity Embedding Enrichment ────────────────────────────

    def _enrich_with_embeddings(self, faces: List[FaceData], img_np: np.ndarray, h: int, w: int):
        """
        Run InsightFace recognition model on detected face crops to compute
        identity embedding vectors. Attaches embedding to face.identity field
        as a hash for downstream tracking.
        """
        session = self._insightface_session
        if session is None:
            return

        input_name = session.get_inputs()[0].name
        input_shape = session.get_inputs()[0].shape
        target_size = (int(input_shape[3]) if len(input_shape) >= 4 else 112,
                       int(input_shape[2]) if len(input_shape) >= 4 else 112)

        for face in faces:
            try:
                bx, by, bw, bh = face.bbox.x, face.bbox.y, face.bbox.width, face.bbox.height
                # Pad crop by 10% for better embedding quality
                margin = int(max(bw, bh) * 0.1)
                cx1 = max(0, bx - margin)
                cy1 = max(0, by - margin)
                cx2 = min(w, bx + bw + margin)
                cy2 = min(h, by + bh + margin)
                crop = img_np[cy1:cy2, cx1:cx2]

                if crop.size == 0:
                    continue

                # Resize to model input, normalize
                if _OPENCV_AVAILABLE:
                    crop_resized = cv2.resize(crop, target_size)
                else:
                    continue

                blob = crop_resized[:, :, ::-1].transpose(2, 0, 1).astype(np.float32)
                # Standard ArcFace normalization
                blob = (blob - 127.5) / 127.5
                blob = np.expand_dims(blob, axis=0)

                embedding = session.run(None, {input_name: blob})[0]
                emb_flat = embedding.flatten()

                # Normalize embedding to unit vector
                norm = np.linalg.norm(emb_flat)
                if norm > 0:
                    emb_flat = emb_flat / norm

                # Store a short hash as identity label (full vector available for matching)
                import hashlib
                emb_hash = hashlib.md5(emb_flat.tobytes()).hexdigest()[:8]
                face.identity = f"User_{emb_hash}"

            except Exception as ex:
                logger.debug(f"[FaceDetector] Embedding enrichment failed for face {face.tracking_id}: {ex}")

    # ── Helper to convert inputs to OpenCV BGR format ────────────────────────

    def _to_numpy_bgr(self, image_data: Any) -> Tuple[Optional[np.ndarray], int, int]:
        if image_data is None:
            return None, 0, 0

        # Case 1: numpy array
        if isinstance(image_data, np.ndarray):
            if image_data.size == 0 or len(image_data.shape) < 2:
                return None, 0, 0
            h, w = image_data.shape[:2]
            return image_data, h, w

        # Case 2: base64 string
        if isinstance(image_data, str):
            try:
                clean_b64 = image_data.split(",", 1)[1] if "," in image_data else image_data
                clean_b64 = clean_b64.strip()
                if not clean_b64:
                    return None, 0, 0
                # Fix base64 padding if truncated
                pad_len = (-len(clean_b64)) % 4
                if pad_len > 0:
                    clean_b64 += "=" * pad_len
                raw_bytes = base64.b64decode(clean_b64)
                if _OPENCV_AVAILABLE:
                    nparr = np.frombuffer(raw_bytes, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if img is not None:
                        h, w = img.shape[:2]
                        return img, h, w
                try:
                    from PIL import Image as _PIL_Image
                    from io import BytesIO
                    pil_img = _PIL_Image.open(BytesIO(raw_bytes)).convert("RGB")
                    img_np = np.array(pil_img)[:, :, ::-1] # RGB to BGR
                    h, w = img_np.shape[:2]
                    return img_np, h, w
                except Exception as _err:
                    print(f"[face_detector.py] Silenced exception: {_err}")
            except Exception as ex:
                logger.debug(f"[FaceDetector] _to_numpy_bgr string decode error: {ex}")

        # Case 3: PIL Image object directly
        try:
            from PIL import Image as _PIL_Image
            if isinstance(image_data, _PIL_Image.Image):
                pil_img = image_data.convert("RGB")
                img_np = np.array(pil_img)[:, :, ::-1]
                h, w = img_np.shape[:2]
                return img_np, h, w
        except Exception as ex:
            logger.debug(f"[FaceDetector] PIL object conversion error: {ex}")

        return None, 0, 0
