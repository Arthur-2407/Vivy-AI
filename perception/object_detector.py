"""
perception/object_detector.py
==============================
Vivy AI — Hardware-Adaptive Object & Hand Detector
Detects objects and hands in image frames with automatic backend selection:
  1. MediaPipe Hands Tracking & Hand-Held Object Detection
  2. MediaPipe EfficientDet / OpenCV MobileNet-SSD DNN (ONNX / Caffe / TFLite)
  3. OpenCV Region Proposal & Saliency Heuristic (Lightweight CPU fallback)

Outputs Object Data: Object ID, Label, Bounding Box, Confidence, Center Point, Category.
Outputs Hand State: Tracked Hands, Hand Labels (Left/Right), Gestures, Holding Status.
"""

from __future__ import annotations

import base64
import logging
import os
import math
import time
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Any, Dict

from perception.perception_state import BoundingBox, Point3D
from perception.hardware_scheduler import get_hardware_scheduler

logger = logging.getLogger(__name__)

# Check backend availability
_MEDIAPIPE_AVAILABLE = False
_MEDIAPIPE_HANDS_AVAILABLE = False
try:
    import mediapipe as mp
    if hasattr(mp, "solutions") and hasattr(mp.solutions, "hands"):
        _MEDIAPIPE_HANDS_AVAILABLE = True
    try:
        from mediapipe.tasks.python.vision import object_detector as mp_object_detector
        _MEDIAPIPE_AVAILABLE = True
    except Exception as _err:
        logger.debug(f"[ObjectDetector] MediaPipe not available: {_err}")
except Exception as _err:
        logger.debug(f"[ObjectDetector] MediaPipe import error: {_err}")

_OPENCV_AVAILABLE = False
try:
    import cv2
    if hasattr(cv2, "cvtColor") and hasattr(cv2, "imdecode"):
        _OPENCV_AVAILABLE = True
except Exception as _err:
    logger.debug(f"[ObjectDetector] OpenCV not available: {_err}")

try:
    from PIL import Image
    from io import BytesIO
except ImportError:
    pass

# ── YOLOv11 / Ultralytics Backend ────────────────────────────────────────────
_ULTRALYTICS_AVAILABLE = False
try:
    from ultralytics import YOLO as _UltralyticsYOLO
    _ULTRALYTICS_AVAILABLE = True
except ImportError:
    _UltralyticsYOLO = None


from perception.perception_state import BoundingBox, Point3D, HandData, ObjectData
from perception.gesture_engine import GestureEngine


# Standard COCO dataset 20 class labels for MobileNet-SSD / CPU fallback
COCO_CLASSES = [
    "background", "person", "bicycle", "car", "motorcycle", "airplane", "bus",
    "train", "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana",
    "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza",
    "donut", "cake", "chair", "couch", "potted plant", "bed", "dining table",
    "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock",
    "vase", "scissors", "teddy bear", "hair drier", "toothbrush"
]


class ObjectDetector:
    """
    Hardware-adaptive multi-object & MediaPipe Hand detector.

    Backend priority chain (auto mode):
      0. YOLOv11 / Ultralytics (GPU → CPU)  — highest accuracy, 80-class COCO
      1. OpenCV MobileNet-SSD DNN           — lightweight CPU Caffe model
      2. MediaPipe EfficientDet              — TFLite alternative
      3. OpenCV Region Proposal              — heuristic fallback
    """

    def __init__(self, min_detection_confidence: float = 0.4):
        self._confidence_threshold = min_detection_confidence
        self._mp_detector = None
        self._mp_hands = None
        self._dnn_net = None
        self._current_backend = "Unknown"
        self._last_hands: List[HandData] = []
        
        # Dedicated engine per handedness to prevent trajectory scrambling when two hands are detected
        self._gesture_engines = {
            "Left": GestureEngine(),
            "Right": GestureEngine()
        }
        from collections import deque
        self._hand_hold_history = {
            "Left": deque(maxlen=5),
            "Right": deque(maxlen=5)
        }
        self._hand_track_info = {
            "Left": {"id": 1, "missed_frames": 0},
            "Right": {"id": 2, "missed_frames": 0}
        }
        self._next_hand_track_id = 3
        self._was_clapping = False
        self._last_two_hands_dist = 9999.0
        self._last_two_hands_width = 0.0

        # YOLOv11 model instance
        self._yolo_model = None
        self._yolo_device = "cpu"

        # Load config-driven settings
        self._cfg = self._load_model_config()

        self._init_detector()

    @staticmethod
    def _load_model_config() -> Dict[str, Any]:
        """Load object detection config from perception config_loader."""
        try:
            from perception.config_loader import get, get_absolute_path
            obj_cfg = get("perception_models", "object_detection", default={})
            if not isinstance(obj_cfg, dict):
                obj_cfg = {}
            hand_cfg = get("perception_models", "hand_tracking", default={})
            if not isinstance(hand_cfg, dict):
                hand_cfg = {}
            return {
                "backend":            obj_cfg.get("backend", "auto") if isinstance(obj_cfg, dict) else "auto",
                "device":             obj_cfg.get("device", "auto") if isinstance(obj_cfg, dict) else "auto",
                "yolov11_model_path": get("models", "object_detection", default="yolo11n.pt"),
                "yolov11_input_size": int(obj_cfg.get("yolov11_input_size", 640)) if isinstance(obj_cfg, dict) else 640,
                "min_confidence":     float(obj_cfg.get("min_confidence", 0.5)) if isinstance(obj_cfg, dict) else 0.5,
                "max_detections":     int(obj_cfg.get("max_detections", 10)),
                "hand_enabled":       hand_cfg.get("enabled", True),
                "hand_max":           int(hand_cfg.get("max_hands", 2)),
            }
        except Exception as ex:
            logger.debug(f"[ObjectDetector] Config loader unavailable: {ex}. Using defaults.")
            return {
                "backend": "auto",
                "device": "auto",
                "yolov11_model_path": "",
                "yolov11_input_size": 640,
                "max_detections": 10,
                "hand_enabled": True,
                "hand_max": 2,
            }

    def _resolve_device(self) -> str:
        """Resolve 'auto' device to 'cpu' or 'gpu' via hardware scheduler."""
        device_pref = self._cfg.get("device", "auto")
        if device_pref in ("cpu", "gpu"):
            return device_pref
        from perception.hardware_scheduler import get_hardware_scheduler
        return get_hardware_scheduler().get_assignment("object_detection")

    def _init_detector(self):
        """Initialize available object & hand detection models in priority order."""
        # Initialize MediaPipe Hands if available
        if self._cfg.get("hand_enabled", True) and _MEDIAPIPE_HANDS_AVAILABLE:
            try:
                self._mp_hands = mp.solutions.hands.Hands(
                    static_image_mode=False,  # Enables continuous LSTM tracking
                    max_num_hands=self._cfg.get("hand_max", 2),
                    min_detection_confidence=self._confidence_threshold,
                    min_tracking_confidence=self._confidence_threshold
                )
                logger.info("[ObjectDetector] MediaPipe Hands tracking initialized successfully.")
            except Exception as ex:
                logger.warning(f"[ObjectDetector] MediaPipe Hands init error: {ex}")

        backend_pref = self._cfg.get("backend", "auto")

        # 0. Try YOLOv11 / Ultralytics (highest priority)
        if backend_pref in ("auto", "yolov11") and _ULTRALYTICS_AVAILABLE:
            try:
                model_path = self._cfg.get("yolov11_model_path", "")
                is_standard_model = model_path and not os.path.isabs(model_path) and os.path.basename(model_path).startswith("yolo")
                if model_path and (os.path.exists(model_path) or is_standard_model):
                    if not os.path.exists(model_path):
                        logger.info(f"[ObjectDetector] Auto-downloading Ultralytics model: {model_path}")
                    self._yolo_model = _UltralyticsYOLO(model_path)
                    device = self._resolve_device()
                    # Ultralytics accepts device='cpu' or device=0 (first GPU)
                    self._yolo_device = 0 if device == "gpu" else "cpu"
                    suffix = "CUDA" if device == "gpu" else "CPU"
                    self._current_backend = f"YOLOv11 ({suffix})" + (" + MediaPipe Hands" if self._mp_hands else "")
                    logger.info(f"[ObjectDetector] Initialized YOLOv11 backend: {self._current_backend}")
                    return
                else:
                    logger.info(f"[ObjectDetector] YOLOv11 model not found at '{model_path}'. Falling back.")
            except Exception as ex:
                logger.warning(f"[ObjectDetector] YOLOv11 init error: {ex}")

        # 1. Try OpenCV MobileNet-SSD DNN if weights exist locally
        if _OPENCV_AVAILABLE:
            try:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                prototxt = os.path.join(base_dir, "models", "MobileNetSSD_deploy.prototxt")
                caffemodel = os.path.join(base_dir, "models", "MobileNetSSD_deploy.caffemodel")
                if os.path.exists(prototxt) and os.path.exists(caffemodel):
                    self._dnn_net = cv2.dnn.readNetFromCaffe(prototxt, caffemodel)
                    self._current_backend = "OpenCV MobileNet-SSD + MediaPipe Hands" if self._mp_hands else "OpenCV MobileNet-SSD"
                    logger.info(f"[ObjectDetector] Initialized {self._current_backend} backend.")
                    return
            except Exception as ex:
                logger.warning(f"[ObjectDetector] OpenCV DNN init error: {ex}")

        # 2. Try MediaPipe Object Detector if model exists
        if _MEDIAPIPE_AVAILABLE:
            try:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                model_path = os.path.join(base_dir, "models", "efficientdet_lite0.tflite")
                if os.path.exists(model_path):
                    options = mp_object_detector.ObjectDetectorOptions(
                        base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
                        score_threshold=self._confidence_threshold
                    )
                    self._mp_detector = mp_object_detector.ObjectDetector.create_from_options(options)
                    self._current_backend = "MediaPipe EfficientDet + Hands" if self._mp_hands else "MediaPipe EfficientDet"
                    logger.info(f"[ObjectDetector] Initialized {self._current_backend} backend.")
                    return
            except Exception as ex:
                logger.warning(f"[ObjectDetector] MediaPipe Object Detector init error: {ex}")

        # 3. Fallback: OpenCV Contour & Saliency Heuristic Engine (+ MediaPipe Hands if active)
        self._current_backend = "MediaPipe Hands + Region Proposal" if self._mp_hands else "OpenCV Region Proposal"
        logger.info(f"[ObjectDetector] Operating with {self._current_backend} backend.")
    @staticmethod
    def _is_valid_hand_topology(x_norm: List[float], y_norm: List[float]) -> bool:
        """
        Validates whether the MediaPipe landmarks form a geometrically plausible hand.
        Rejects degenerate squashed hands (often hallucinated on faces).
        """
        if len(x_norm) != 21 or len(y_norm) != 21:
            return False
            
        # Calculate intrinsic scale (Wrist to Middle Finger MCP)
        palm_length = math.hypot(x_norm[0] - x_norm[9], y_norm[0] - y_norm[9])
        
        # If palm length is virtually zero, the detection is entirely degenerate
        if palm_length < 0.01:
            return False
            
        # Check if the whole hand is squashed into a tiny dot
        width = max(x_norm) - min(x_norm)
        height = max(y_norm) - min(y_norm)
        
        # Extremely elongated or extremely squashed bounding boxes are usually false positives on edges
        if width < 0.01 and height < 0.01:
            return False
            
        # Optional: check if fingers are impossibly long compared to the palm
        # Middle finger tip (12) to MCP (9)
        middle_length = math.hypot(x_norm[12] - x_norm[9], y_norm[12] - y_norm[9])
        
        # If middle finger is 5x longer than the palm, it's a hallucination (e.g. hair strands, headphone bands)
        if middle_length > palm_length * 5.0:
            return False
            
        return True

    def detect_objects(self, image_data: Any) -> List[ObjectData]:
        """
        Detect objects and hands in frame.
        Accepts: OpenCV BGR numpy array, PIL Image, or base64 JPEG string.
        Returns list of ObjectData objects (including tracked hands and held items).
        """
        img_np, h, w = self._to_numpy_bgr(image_data)
        if img_np is None or w < 20 or h < 20:
            self._last_hands = []
            return []

        # Ensure correct uint8 array layout
        if not isinstance(img_np, np.ndarray) or img_np.dtype != np.uint8 or not img_np.flags['C_CONTIGUOUS']:
            try:
                img_np = np.ascontiguousarray(img_np, dtype=np.uint8)
            except Exception as e:
                logger.debug(f"[ObjectDetector] Array conversion failed: {e}")
                self._last_hands = []
                return []

        objects: List[ObjectData] = []
        tracked_hands: List[HandData] = []
        track_id = 1

        # ── Step A: MediaPipe Hands Tracking ─────────────────────────────────
        if self._mp_hands is not None and _OPENCV_AVAILABLE:
            try:
                rgb_img = cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB)
                results = self._mp_hands.process(rgb_img)

                if results.multi_hand_landmarks and results.multi_handedness:
                    seen_hands = set()
                    
                    # Sort detected hands by confidence to guarantee high-confidence real hands claim labels first
                    sorted_hands = sorted(
                        zip(results.multi_hand_landmarks, results.multi_handedness),
                        key=lambda x: x[1].classification[0].score,
                        reverse=True
                    )
                    
                    for hand_landmarks, handedness in sorted_hands:
                        # MediaPipe Handedness already compensates for selfie-view/mirroring by default.
                        # So raw_label is the correct anatomical handedness. No inversion needed.
                        label = handedness.classification[0].label
                        score = float(handedness.classification[0].score)
                        
                        # Normalized coords (0..1) for gesture classification
                        x_norm = [lm.x for lm in hand_landmarks.landmark]
                        y_norm = [lm.y for lm in hand_landmarks.landmark]
                        
                        # Strict Hand Validity Gate: Reject degenerate/squashed hands (e.g. hallucinated on faces)
                        if not self._is_valid_hand_topology(x_norm, y_norm):
                            logger.debug(f"[ObjectDetector] Suppressed invalid hand topology for {label} hand.")
                            continue
                        
                        bx = int(max(0, min(x_norm) * w))
                        by = int(max(0, min(y_norm) * h))
                        bw = int(min(w - bx, max(0, (max(x_norm) - min(x_norm)) * w)))
                        bh = int(min(h - by, max(0, (max(y_norm) - min(y_norm)) * h)))
                        
                        if bw < 10 or bh < 10:
                            continue

                        # Check for spatial overlap hallucination
                        # If a hand was already accepted that heavily overlaps with this one, skip this lower-confidence one
                        is_hallucination = False
                        for h_data in tracked_hands:
                            ix1 = max(bx, h_data.bbox.x)
                            iy1 = max(by, h_data.bbox.y)
                            ix2 = min(bx + bw, h_data.bbox.x + h_data.bbox.width)
                            iy2 = min(by + bh, h_data.bbox.y + h_data.bbox.height)
                            if ix2 > ix1 and iy2 > iy1:
                                inter_area = (ix2 - ix1) * (iy2 - iy1)
                                area_current = bw * bh
                                if inter_area > area_current * 0.70:
                                    is_hallucination = True
                                    break
                                    
                        if is_hallucination:
                            logger.debug(f"[ObjectDetector] Suppressed spatial hallucination for {label} hand (score: {score:.2f})")
                            continue
                            
                        # Fix trajectory scrambling: Never process the same physical hand twice in a single frame.
                        if label in seen_hands:
                            logger.debug(f"[ObjectDetector] Suppressed duplicate {label} hand hallucination (score: {score:.2f})")
                            continue
                        seen_hands.add(label)

                        # Pixel coords for bounding box only
                        x_coords = [lm.x * w for lm in hand_landmarks.landmark]
                        y_coords = [lm.y * h for lm in hand_landmarks.landmark]

                        min_x, max_x = int(max(0, min(x_coords))), int(min(w, max(x_coords)))
                        min_y, max_y = int(max(0, min(y_coords))), int(min(h, max(y_coords)))

                        bx = min_x
                        by = min_y
                        bw = max(15, max_x - min_x)
                        bh = max(15, max_y - min_y)
                        
                        # Spatial Filter: A real hand close to the camera must take up at least 50x50 pixels.
                        # Tiny detections are background shadows/hallucinations.
                        if bw < 50 or bh < 50:
                            logger.debug(f"[ObjectDetector] Ignored hallucinated hand (size: {bw}x{bh}, score: {score:.2f})")
                            continue

                        cx = round(bx + bw / 2.0, 1)
                        cy = round(by + bh / 2.0, 1)

                        # Check if this hand was holding an item in the previous frame
                        prev_holding = any(h.holding_item for h in self._last_hands if h.hand_label == label)

                        gesture, gesture_phase, gesture_confidence, newly_confirmed = self._gesture_engines[label].process_hand(
                            x_coords=x_norm,
                            y_coords=y_norm,
                            handedness_label=label,
                            timestamp=time.time(),
                            holding_item=prev_holding
                        )
                        
                        gesture_is_grab = (gesture in ["PINCH", "FIST"])

                        # Check for object in hand region (hand ROI expansion)
                        roi_margin = int(max(bw, bh) * 0.4)
                        roi_x1 = max(0, bx - roi_margin)
                        roi_y1 = max(0, by - roi_margin)
                        roi_x2 = min(w, bx + bw + roi_margin)
                        roi_y2 = min(h, by + bh + roi_margin)

                        # HandData will be created after actual_holding_item is determined
                        pass

                        # Create hand ObjectData entry so downstreams see the hand clearly
                        hand_obj = ObjectData(
                            tracking_id=track_id,
                            label=f"{label} hand ({gesture})",
                            confidence=score,
                            bbox=BoundingBox(x=bx, y=by, width=bw, height=bh),
                            center_point=Point3D(x=cx, y=cy, z=1.0),
                            category="hand",
                            validation_state="verified"
                        )
                        objects.append(hand_obj)
                        track_id += 1

                        # If hand gesture is grab, it might be holding something. Actual intersection check done after object detection.
                        actual_holding_item = False
                        if gesture_is_grab:
                            actual_holding_item = True
                                
                        # Hand Tracking ID logic
                        t_info = self._hand_track_info[label]
                        if t_info["missed_frames"] > 5:
                            t_info["id"] = self._next_hand_track_id
                            self._next_hand_track_id += 1
                            # Cause 3 fix: clear stale trajectory when hand re-enters frame.
                            # Without this, old position data (within the 0.4s swipe window)
                            # causes phantom swipes when the hand reappears at a new position.
                            self._gesture_engines[label].trajectory.clear()
                            logger.debug(f"[ObjectDetector] Hand {label} re-entry detected after {t_info['missed_frames']} missed frames. Trajectory cleared.")
                        t_info["missed_frames"] = 0
                        hand_track_id = t_info["id"]

                        hand_data = HandData(
                            tracking_id=hand_track_id,
                            hand_label=label,
                            confidence=score,
                            bbox=BoundingBox(x=bx, y=by, width=bw, height=bh),
                            center_point=Point3D(x=cx, y=cy, z=1.0),
                            holding_item=actual_holding_item,
                            gesture=gesture,
                            gesture_phase=gesture_phase,
                            gesture_confidence=gesture_confidence,
                            gesture_newly_confirmed=newly_confirmed
                        )
                        tracked_hands.append(hand_data)
                    # Increment missed frames for unseen hands
                    for h_lbl in ["Left", "Right"]:
                        if h_lbl not in seen_hands:
                            self._hand_track_info[h_lbl]["missed_frames"] += 1

            except Exception as ex:
                logger.debug(f"[ObjectDetector] MediaPipe Hands error: {ex}")

        self._last_hands = tracked_hands

        # --- Dual Hand Spatial Clap Detection ---
        if len(tracked_hands) == 2:
            h1, h2 = tracked_hands[0], tracked_hands[1]
            if h1.hand_label != h2.hand_label:
                dist = math.hypot(h1.center_point.x - h2.center_point.x, h1.center_point.y - h2.center_point.y)
                avg_width = (h1.bbox.width + h2.bbox.width) / 2.0
                
                # Calculate convergence velocity
                if hasattr(self, '_last_two_hands_dist') and self._last_two_hands_dist != 9999.0:
                    velocity = dist - self._last_two_hands_dist
                else:
                    velocity = 0.0

                # High negative velocity means rapid convergence
                rapid_convergence = velocity < -(avg_width * 0.15)
                
                if dist < (avg_width * 1.2): 
                    if rapid_convergence and not self._was_clapping:
                        self._was_clapping = True
                        logger.info(f"[ObjectDetector] CLAP DETECTED! Hands collided with velocity {velocity:.1f} at dist {dist:.1f}")
                        h1.gesture = "CLAP"
                        h1.gesture_newly_confirmed = True
                        h1.gesture_confidence = 1.0
                    elif self._was_clapping:
                        # Hold clap state to prevent spurious static gestures
                        h1.gesture = "CLAP_HOLD"
                        h1.gesture_newly_confirmed = False
                else:
                    self._was_clapping = False
                    
                self._last_two_hands_dist = dist
                self._last_two_hands_width = avg_width
            else:
                self._last_two_hands_dist = 9999.0
                self._was_clapping = False
        elif len(tracked_hands) == 1:
            # Merged Hand Clap Detection: If we lost a hand, but they were converging rapidly in the previous frame
            if hasattr(self, '_last_two_hands_dist') and self._last_two_hands_dist < (self._last_two_hands_width * 2.5):
                if self._was_clapping:
                    logger.debug("[ObjectDetector] CLAP HOLD via hand merge!")
                    tracked_hands[0].gesture = "CLAP_HOLD"
                    tracked_hands[0].gesture_newly_confirmed = False
                elif self._last_two_hands_dist < self._last_two_hands_width * 1.5:
                     self._was_clapping = True
                     logger.info("[ObjectDetector] CLAP DETECTED via rapid hand merge!")
                     tracked_hands[0].gesture = "CLAP"
                     tracked_hands[0].gesture_newly_confirmed = True
                     tracked_hands[0].gesture_confidence = 1.0
            
            # Reset dist so we don't continuously fire clap if the user keeps their hands merged
            self._last_two_hands_dist = 9999.0
        else:
            self._was_clapping = False
            self._last_two_hands_dist = 9999.0
            self._last_two_hands_dist = 9999.0

        # ── Step B-0: YOLOv11 / Ultralytics Detection ────────────────────────
        if self._yolo_model is not None:
            try:
                results = self._yolo_model.predict(
                    img_np,
                    device=self._yolo_device,
                    imgsz=self._cfg.get("yolov11_input_size", 640),
                    conf=self._confidence_threshold,
                    verbose=False
                )
                if results and len(results) > 0:
                    result = results[0]
                    if result.boxes is not None:
                        for box in result.boxes:
                            confidence = float(box.conf[0])
                            cls_id = int(box.cls[0])
                            label = result.names.get(cls_id, f"object_{cls_id}") if hasattr(result, 'names') else f"object_{cls_id}"

                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                            bx, by = int(max(0, x1)), int(max(0, y1))
                            bw, bh = int(min(w, x2) - bx), int(min(h, y2) - by)

                            if bw >= 15 and bh >= 15:
                                cx = round(bx + bw / 2.0, 1)
                                cy = round(by + bh / 2.0, 1)
                                obj = ObjectData(
                                    tracking_id=track_id,
                                    label=label,
                                    confidence=confidence,
                                    bbox=BoundingBox(x=bx, y=by, width=bw, height=bh),
                                    center_point=Point3D(x=cx, y=cy, z=1.0),
                                    category="electronic" if label in ["laptop", "tv", "cell phone", "keyboard", "mouse"] else "general",
                                    validation_state="verified"
                                )
                                objects.append(obj)
                                track_id += 1
            except Exception as ex:
                logger.debug(f"[ObjectDetector] YOLOv11 detection error: {ex}")

        # ── Step B: OpenCV DNN (MobileNet-SSD) — only if no YOLO results ────
        if self._dnn_net is not None and _OPENCV_AVAILABLE and len([o for o in objects if o.category != "hand"]) == 0:
            try:
                blob = cv2.dnn.blobFromImage(cv2.resize(img_np, (300, 300)), 0.007843, (300, 300), 127.5)
                self._dnn_net.setInput(blob)
                detections = self._dnn_net.forward()
                for i in range(detections.shape[2]):
                    confidence = float(detections[0, 0, i, 2])
                    if confidence >= self._confidence_threshold:
                        idx = int(detections[0, 0, i, 1])
                        label = COCO_CLASSES[idx] if idx < len(COCO_CLASSES) else f"object_{idx}"
                        box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                        bx, by, bw, bh = int(box[0]), int(box[1]), int(box[2] - box[0]), int(box[3] - box[1])
                        if bw >= 15 and bh >= 15:
                            cx = round(bx + bw / 2.0, 1)
                            cy = round(by + bh / 2.0, 1)
                            obj = ObjectData(
                                tracking_id=track_id,
                                label=label,
                                confidence=confidence,
                                bbox=BoundingBox(x=max(0, bx), y=max(0, by), width=min(w - bx, bw), height=min(h - by, bh)),
                                center_point=Point3D(x=cx, y=cy, z=1.0),
                                category="electronic" if label in ["laptop", "tv", "cell phone", "keyboard", "mouse"] else "general",
                                validation_state="verified"
                            )
                            objects.append(obj)
                            track_id += 1
            except Exception as ex:
                logger.debug(f"[ObjectDetector] OpenCV DNN detection error: {ex}")

        # ── Step C: Region Proposal Heuristic (Foreground object proposal) ──────
        # Run region proposal if no non-person, non-hand objects were detected. 
        # This allows detecting non-COCO objects (like hats or headphones) when only a "person" was found by YOLO.
        non_person_objects = [o for o in objects if o.category not in ("hand", "held_item") and o.label != "person"]
        if len(non_person_objects) == 0 and _OPENCV_AVAILABLE:
            try:
                gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (5, 5), 0)
                edged = cv2.Canny(blur, 20, 100) # Lowered thresholds to catch softer edges
                contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                for c in contours:
                    area = cv2.contourArea(c)
                    if (w * h * 0.005) < area < (w * h * 0.25):  # Max area 25% to prevent claiming full face/head
                        bx, by, bw, bh = cv2.boundingRect(c)
                        if bw >= 25 and bh >= 25:
                            # Skip bounding box if it heavily overlaps an already tracked hand box
                            # This prevents the hand's own edges/motion from being classified as a held object
                            is_hand_contour = False
                            for hand in tracked_hands:
                                ix1 = max(bx, hand.bbox.x)
                                iy1 = max(by, hand.bbox.y)
                                ix2 = min(bx + bw, hand.bbox.x + hand.bbox.width)
                                iy2 = min(by + bh, hand.bbox.y + hand.bbox.height)
                                if ix2 > ix1 and iy2 > iy1:
                                    inter_area = (ix2 - ix1) * (iy2 - iy1)
                                    # If the contour is mostly inside the hand, it's just the hand's own edges
                                    if inter_area > (bw * bh) * 0.7:
                                        is_hand_contour = True
                                        break
                            if is_hand_contour:
                                continue
                            cx = round(bx + bw / 2.0, 1)
                            cy = round(by + bh / 2.0, 1)

                            aspect = bw / float(bh)
                            if aspect > 1.4:
                                if by < h * 0.4:
                                    continue # Ignore wide contours at the top of the screen (e.g. headphones, ceiling lights)
                                category_label = "display/screen/keyboard"
                            elif aspect < 0.7:
                                category_label = "phone/bottle/cup/book"
                            else:
                                if by < h * 0.4:
                                    continue # Ignore squarish contours at top of screen
                                category_label = "desktop item/object"

                            obj = ObjectData(
                                tracking_id=track_id,
                                label=category_label,
                                confidence=0.50,
                                bbox=BoundingBox(x=bx, y=by, width=bw, height=bh),
                                center_point=Point3D(x=cx, y=cy, z=1.2),
                                category="foreground_object",
                                validation_state="heuristic"
                            )
                            objects.append(obj)
                            track_id += 1
                            if len(objects) >= 6:
                                break
            except Exception as ex:
                logger.debug(f"[ObjectDetector] Region proposal error: {ex}")

        # ── Step D: Validate Holding Items via Bounding Box Intersection ──────
        current_holding = {"Left": False, "Right": False}
        valid_objects = []
        for obj in objects:
            if obj.category in ("hand", "held_item") or obj.label == "person":
                valid_objects.append(obj)
                continue
                
            is_hallucination = False
            is_held = False
            holding_hand = None
            
            for hand in tracked_hands:
                ix1 = max(hand.bbox.x, obj.bbox.x)
                iy1 = max(hand.bbox.y, obj.bbox.y)
                ix2 = min(hand.bbox.x + hand.bbox.width, obj.bbox.x + obj.bbox.width)
                iy2 = min(hand.bbox.y + hand.bbox.height, obj.bbox.y + obj.bbox.height)
                
                if ix2 > ix1 and iy2 > iy1:
                    inter_area = (ix2 - ix1) * (iy2 - iy1)
                    hand_area = hand.bbox.width * hand.bbox.height
                    obj_area = obj.bbox.width * obj.bbox.height
                    
                    # If object is >80% inside hand box, it's likely a misclassified finger/palm (hallucination)
                    if inter_area > obj_area * 0.80:
                        is_hallucination = True
                        break
                    
                    # If intersection is at least 15% of the hand OR 25% of the object, it's a held item
                    if inter_area > hand_area * 0.15 or inter_area > obj_area * 0.25:
                        is_held = True
                        holding_hand = hand.hand_label
            
            if not is_hallucination:
                if is_held:
                    current_holding[holding_hand] = True
                    obj.validation_state = "hand_held"
                    obj.category = "held_item"
                valid_objects.append(obj)
        objects = valid_objects
        
        for hand in tracked_hands:
            # Static Object Inference (Association Layer)
            if not current_holding[hand.hand_label] and hand.gesture in ["PINCH", "FIST", "OPEN_PALM"]:
                # In Region Proposal mode, static objects are invisible. If hand is closed,
                # use Canny edge density to infer if it's grasping a rigid object.
                if "Region Proposal" in self._current_backend and _OPENCV_AVAILABLE:
                    try:
                        # Extract Hand ROI
                        hx, hy = hand.bbox.x, hand.bbox.y
                        hw, hh = hand.bbox.width, hand.bbox.height
                        roi = img_np[max(0, hy):min(h, hy+hh), max(0, hx):min(w, hx+hw)]
                        if roi.size > 0:
                            gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                            edges = cv2.Canny(gray_roi, 50, 150)
                            edge_density = np.sum(edges > 0) / (hw * hh + 1e-5)
                            # If significant edges exist (not just skin), infer object
                            if edge_density > 0.08:
                                current_holding[hand.hand_label] = True
                                syn_obj = ObjectData(
                                    tracking_id=track_id,
                                    label="inferred_held_item",
                                    confidence=0.60,
                                    bbox=BoundingBox(x=hx, y=hy, width=hw, height=hh),
                                    center_point=Point3D(x=hand.center_point.x, y=hand.center_point.y, z=hand.center_point.z),
                                    category="held_item",
                                    validation_state="inferred"
                                )
                                objects.append(syn_obj)
                                track_id += 1
                    except Exception as ex:
                        logger.debug(f"[ObjectDetector] Static Object Inference error: {ex}")
                        
            # Apply temporal persistence
            self._hand_hold_history[hand.hand_label].append(current_holding[hand.hand_label])
            history = self._hand_hold_history[hand.hand_label]
            # Must be holding in at least 3 of the last 5 frames
            if sum(history) >= 3:
                hand.holding_item = True
            else:
                hand.holding_item = False

        # Deduplicate & Sort by confidence / area
        max_det = self._cfg.get("max_detections", 10)
        objects.sort(key=lambda o: (o.confidence, o.bbox.width * o.bbox.height), reverse=True)
        return objects[:max_det]

    def get_tracked_hands(self) -> List[HandData]:
        """Return list of tracked HandData from the latest frame."""
        return list(self._last_hands)

    def get_hand_state(self) -> Dict[str, Any]:
        """Return structured summary of hand tracking & holding state."""
        hands = self._last_hands
        holding = any(h.holding_item for h in hands)
        return {
            "hands_tracked": len(hands),
            "hands": [h.to_dict() for h in hands],
            "holding_detected": holding,
            "holding_summary": ("holding an item" if holding else "hands empty") if hands else "no hands in frame"
        }

    def get_backend_name(self) -> str:
        return self._current_backend

    def _to_numpy_bgr(self, image_data: Any) -> Tuple[Optional[np.ndarray], int, int]:
        if image_data is None:
            return None, 0, 0
        if isinstance(image_data, np.ndarray):
            if image_data.size == 0 or len(image_data.shape) < 2:
                return None, 0, 0
            h, w = image_data.shape[:2]
            return image_data, h, w
        if isinstance(image_data, str):
            try:
                clean_b64 = image_data.split(",", 1)[1] if "," in image_data else image_data
                clean_b64 = clean_b64.strip()
                if not clean_b64:
                    return None, 0, 0
                raw_bytes = base64.b64decode(clean_b64)
                if _OPENCV_AVAILABLE:
                    nparr = np.frombuffer(raw_bytes, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if img is not None:
                        h, w = img.shape[:2]
                        return img, h, w
                elif 'Image' in globals():
                    pil_img = Image.open(BytesIO(raw_bytes)).convert("RGB")
                    img_np = np.array(pil_img)[:, :, ::-1]
                    h, w = img_np.shape[:2]
                    return img_np, h, w
            except Exception as _err:
                print(f"[object_detector.py] Silenced exception: {_err}")
        return None, 0, 0
