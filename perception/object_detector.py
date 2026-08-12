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


@dataclass
class HandData:
    """Dataclass representing a tracked hand."""
    hand_label: str  # "Left", "Right"
    confidence: float
    bbox: BoundingBox
    center_point: Point3D
    holding_item: bool = False
    gesture: str = "Open Palm"  # "Open Palm", "Closed Fist", "Pinch/Holding", "Pointing"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hand_label": self.hand_label,
            "confidence": round(float(self.confidence), 2),
            "bbox": self.bbox.to_dict(),
            "center_point": self.center_point.to_dict(),
            "holding_item": self.holding_item,
            "gesture": self.gesture,
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
                "yolov11_model_path": get_absolute_path(get("models", "face_detection", default="models/yolov11/yolo11n-face.pt")),
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
                    static_image_mode=False,
                    max_num_hands=self._cfg.get("hand_max", 2),
                    min_detection_confidence=self._confidence_threshold,
                    min_tracking_confidence=0.5
                )
                logger.info("[ObjectDetector] MediaPipe Hands tracking initialized successfully.")
            except Exception as ex:
                logger.warning(f"[ObjectDetector] MediaPipe Hands init error: {ex}")

        backend_pref = self._cfg.get("backend", "auto")

        # 0. Try YOLOv11 / Ultralytics (highest priority)
        if backend_pref in ("auto", "yolov11") and _ULTRALYTICS_AVAILABLE:
            try:
                model_path = self._cfg.get("yolov11_model_path", "")
                if model_path and os.path.exists(model_path):
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
        if not isinstance(img_np, np.ndarray) or img_np.dtype != np.uint8:
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
                    for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                        label = handedness.classification[0].label  # "Left" or "Right"
                        score = float(handedness.classification[0].score)

                        # Extract normalized pixel coordinates of landmarks
                        x_coords = [lm.x * w for lm in hand_landmarks.landmark]
                        y_coords = [lm.y * h for lm in hand_landmarks.landmark]

                        min_x, max_x = int(max(0, min(x_coords))), int(min(w, max(x_coords)))
                        min_y, max_y = int(max(0, min(y_coords))), int(min(h, max(y_coords)))

                        bx = min_x
                        by = min_y
                        bw = max(15, max_x - min_x)
                        bh = max(15, max_y - min_y)

                        cx = round(bx + bw / 2.0, 1)
                        cy = round(by + bh / 2.0, 1)

                        # Gesture analysis: Check finger curl (compare fingertip to MCP joint)
                        # Landmarks: 4 (thumb tip), 8 (index tip), 12 (middle tip), 16 (ring tip), 20 (pinky tip)
                        # MCP joints: 2, 5, 9, 13, 17
                        tips = [8, 12, 16, 20]
                        mcps = [5, 9, 13, 17]
                        extended_fingers = 0
                        for tip, mcp in zip(tips, mcps):
                            if y_coords[tip] < y_coords[mcp]:  # Fingertip higher than MCP in frame coordinates
                                extended_fingers += 1

                        if extended_fingers >= 3:
                            gesture = "Open Palm"
                            holding_item = False
                        elif extended_fingers == 1 and y_coords[8] < y_coords[5]:
                            gesture = "Pointing"
                            holding_item = False
                        else:
                            gesture = "Closed Fist / Holding"
                            holding_item = True

                        # Check for object in hand region (hand ROI expansion)
                        roi_margin = int(max(bw, bh) * 0.4)
                        roi_x1 = max(0, bx - roi_margin)
                        roi_y1 = max(0, by - roi_margin)
                        roi_x2 = min(w, bx + bw + roi_margin)
                        roi_y2 = min(h, by + bh + roi_margin)

                        hand_data = HandData(
                            hand_label=label,
                            confidence=score,
                            bbox=BoundingBox(x=bx, y=by, width=bw, height=bh),
                            center_point=Point3D(x=cx, y=cy, z=1.0),
                            holding_item=holding_item,
                            gesture=gesture
                        )
                        tracked_hands.append(hand_data)

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

                        # If hand is holding something, perform foreground ROI blob extraction around fingers
                        if holding_item or (roi_x2 - roi_x1 > 30 and roi_y2 - roi_y1 > 30):
                            try:
                                roi = img_np[roi_y1:roi_y2, roi_x1:roi_x2]
                                gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                                roi_blur = cv2.GaussianBlur(gray_roi, (5, 5), 0)
                                roi_edges = cv2.Canny(roi_blur, 40, 120)
                                contours, _ = cv2.findContours(roi_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                                best_contour = None
                                best_area = 0
                                for c in contours:
                                    area = cv2.contourArea(c)
                                    if area > (bw * bh * 0.15) and area > best_area:
                                        best_area = area
                                        best_contour = c

                                if best_contour is not None:
                                    rx, ry, rw, rh = cv2.boundingRect(best_contour)
                                    item_x = roi_x1 + rx
                                    item_y = roi_y1 + ry
                                    if rw >= 15 and rh >= 15:
                                        item_cx = round(item_x + rw / 2.0, 1)
                                        item_cy = round(item_y + rh / 2.0, 1)
                                        held_obj = ObjectData(
                                            tracking_id=track_id,
                                            label=f"item held in {label.lower()} hand",
                                            confidence=round(score * 0.85, 2),
                                            bbox=BoundingBox(x=item_x, y=item_y, width=rw, height=rh),
                                            center_point=Point3D(x=item_cx, y=item_cy, z=0.9),
                                            category="held_item",
                                            validation_state="hand_held"
                                        )
                                        objects.append(held_obj)
                                        track_id += 1
                            except Exception as roi_ex:
                                logger.debug(f"[ObjectDetector] Hand ROI object analysis error: {roi_ex}")
            except Exception as ex:
                logger.debug(f"[ObjectDetector] MediaPipe Hands error: {ex}")

        self._last_hands = tracked_hands

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
        if len([o for o in objects if o.category not in ("hand", "held_item")]) == 0 and _OPENCV_AVAILABLE:
            try:
                gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (5, 5), 0)
                edged = cv2.Canny(blur, 40, 140)
                contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                for c in contours:
                    area = cv2.contourArea(c)
                    if (w * h * 0.015) < area < (w * h * 0.75):  # Between 1.5% and 75% frame area
                        bx, by, bw, bh = cv2.boundingRect(c)
                        if bw >= 25 and bh >= 25:
                            # Skip bounding box if it severely overlaps an already tracked hand box
                            is_hand_overlap = False
                            for h_data in tracked_hands:
                                hbx = h_data.bbox.x
                                hby = h_data.bbox.y
                                hbw = h_data.bbox.width
                                hbh = h_data.bbox.height
                                if (abs(bx - hbx) < hbw * 0.6) and (abs(by - hby) < hbh * 0.6):
                                    is_hand_overlap = True
                                    break
                            if is_hand_overlap:
                                continue

                            cx = round(bx + bw / 2.0, 1)
                            cy = round(by + bh / 2.0, 1)

                            aspect = bw / float(bh)
                            if aspect > 1.4:
                                category_label = "display/screen/keyboard"
                            elif aspect < 0.7:
                                category_label = "phone/bottle/cup/book"
                            else:
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
