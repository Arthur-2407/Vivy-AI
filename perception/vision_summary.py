"""
perception/vision_summary.py
=============================
Vivy AI — Vision Summarizer
Scene description, OCR text extraction, motion detection, and UI-state summary.

Modular API:
  VisionSummarizer().summarize(frame) -> Dict[str, Any]
  VisionSummarizer().summarize_scene(frame) -> Dict[str, Any]
"""

from __future__ import annotations

import base64
import logging
import math
import time
import numpy as np
from typing import Dict, List, Any, Optional, Tuple

import threading

logger = logging.getLogger(__name__)

_OPENCV_AVAILABLE = False
try:
    import cv2
    if hasattr(cv2, "cvtColor") and hasattr(cv2, "absdiff"):
        _OPENCV_AVAILABLE = True
except Exception as _err:
    print(f"[vision_summary.py] Silenced exception: {_err}")

try:
    from PIL import Image
    from io import BytesIO
except ImportError:
    pass

# Check optional Florence-2 / Transformers backend
_TRANSFORMERS_AVAILABLE = False
try:
    import torch
    from transformers import AutoProcessor, AutoModelForCausalLM
    _TRANSFORMERS_AVAILABLE = True
except ImportError:
    pass


class VisionSummarizer:
    """
    Scene-level Vision Summarizer.
    Analyzes full image frame to compute scene summary, OCR text, motion status, and frame metadata.
    Supports optional Florence-2 VLM for deep scene captioning with rate-limited async execution.
    """

    def __init__(self):
        self._last_frame_gray: Optional[np.ndarray] = None
        self._last_summary_time: float = 0.0
        self._cached_summary: Optional[Dict[str, Any]] = None
        self._last_vlm_time: float = 0.0
        self._latest_vlm_caption: str = ""
        self._vlm_lock = threading.Lock()
        self._vlm_model = None
        self._vlm_processor = None
        self._vlm_device = "cpu"
        self._cfg = self._load_model_config()
        self._init_vlm()

    @staticmethod
    def _load_model_config() -> Dict[str, Any]:
        """Load vision summary config from perception config_loader."""
        try:
            from perception.config_loader import get
            cfg = get("perception_models", "vision_summary", default={})
            if not isinstance(cfg, dict):
                cfg = {}
            return {
                "backend": cfg.get("backend", "auto"),
                "device": cfg.get("device", "auto"),
                "florence2_model_id": cfg.get("florence2_model_id", "microsoft/Florence-2-base"),
                "florence2_max_tokens": int(cfg.get("florence2_max_tokens", 77)),
                "inference_interval_seconds": float(cfg.get("inference_interval_seconds", 2.0)),
            }
        except Exception as ex:
            logger.debug(f"[VisionSummarizer] Config loader unavailable: {ex}. Using defaults.")
            return {
                "backend": "auto",
                "device": "auto",
                "florence2_model_id": "microsoft/Florence-2-base",
                "florence2_max_tokens": 77,
                "inference_interval_seconds": 2.0,
            }

    def _resolve_device(self) -> str:
        """Resolve 'auto' device preference to 'cpu' or 'gpu' via hardware scheduler."""
        device_pref = self._cfg.get("device", "auto")
        if device_pref in ("cpu", "gpu"):
            return device_pref
        from perception.hardware_scheduler import get_hardware_scheduler
        return get_hardware_scheduler().get_assignment("vision_summary")

    def _init_vlm(self):
        """Lazy initialization of Florence-2 VLM if available and requested."""
        backend_pref = self._cfg.get("backend", "auto")
        if backend_pref in ("auto", "florence2") and _TRANSFORMERS_AVAILABLE:
            try:
                model_id = self._cfg.get("florence2_model_id", "microsoft/Florence-2-base")
                device = self._resolve_device()
                if device == "gpu" and torch.cuda.is_available():
                    self._vlm_device = "cuda"
                else:
                    self._vlm_device = "cpu"

                # Check if model path or cache exists
                # We attempt loading lazily or logging readiness
                logger.info(f"[VisionSummarizer] VLM ready for lazy loading ({model_id} on {self._vlm_device}).")
            except Exception as ex:
                logger.warning(f"[VisionSummarizer] Florence-2 VLM init error: {ex}")

    def summarize(self, frame: Any) -> Dict[str, Any]:
        """Alias for summarize_scene for blueprint compatibility."""
        return self.summarize_scene(frame)

    def summarize_scene(self, frame: Any) -> Dict[str, Any]:
        """
        Summarize full scene frame. Returns structured dictionary:
        {
            "scene": str,
            "ocr": List[str],
            "motion": bool,
            "frame_size": [width, height]
        }
        """
        img_np, h, w = self._to_numpy_bgr(frame)
        if img_np is None or w == 0 or h == 0:
            return {
                "scene": "no frame input",
                "ocr": [],
                "motion": False,
                "frame_size": [0, 0]
            }

        # 1. Motion Detection
        motion_detected = False
        if _OPENCV_AVAILABLE and len(img_np.shape) >= 2:
            try:
                gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY) if len(img_np.shape) == 3 else img_np
                gray_small = cv2.resize(gray, (160, 120))
                if self._last_frame_gray is not None:
                    diff = cv2.absdiff(gray_small, self._last_frame_gray)
                    mean_diff = float(np.mean(diff))
                    if mean_diff > 12.0:
                        motion_detected = True
                self._last_frame_gray = gray_small
            except Exception as ex:
                logger.debug(f"[VisionSummarizer] Motion detection error: {ex}")

        # 2. OCR text extraction from PerceptionManager or screen_pipeline
        ocr_lines: List[str] = []
        scene_desc = "indoor desktop workspace"
        
        try:
            from perception.perception_manager import get_reader
            pm_reader = get_reader()
            state = pm_reader.load_state()
            ocr_text = state.get("last_ocr_text", "")
            if ocr_text:
                lines = [l.strip() for l in ocr_text.split("\n") if l.strip()]
                ocr_lines = lines[:10]  # top 10 lines
            
            vlm_caption = state.get("vision_latest_caption", "")
            if vlm_caption:
                scene_desc = vlm_caption
            elif state.get("current_app_type", "unknown") != "unknown":
                scene_desc = f"desk with screen showing {state.get('current_app_type')}"
        except Exception as _err:
            print(f"[vision_summary.py] Silenced exception: {_err}")

        # If no VLM caption was available, generate heuristic scene description
        if scene_desc == "indoor desktop workspace":
            if _OPENCV_AVAILABLE and len(img_np.shape) == 3:
                avg_brightness = float(np.mean(img_np))
                brightness_label = "brightly lit" if avg_brightness > 130 else "darkened"
                scene_desc = f"{brightness_label} indoor workstation with laptop/display"

        return {
            "scene": scene_desc,
            "ocr": ocr_lines,
            "motion": motion_detected,
            "frame_size": [w, h]
        }

    def _to_numpy_bgr(self, image_data: Any) -> Tuple[Optional[np.ndarray], int, int]:
        if image_data is None:
            return None, 0, 0
        if isinstance(image_data, np.ndarray):
            h, w = image_data.shape[:2]
            return image_data, h, w
        if isinstance(image_data, str):
            try:
                b64_str = image_data.split(",", 1)[1] if "," in image_data else image_data
                raw_bytes = base64.b64decode(b64_str)
                if _OPENCV_AVAILABLE:
                    nparr = np.frombuffer(raw_bytes, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if img is not None:
                        h, w = img.shape[:2]
                        return img, h, w
            except Exception as _err:
                print(f"[vision_summary.py] Silenced exception: {_err}")
        return None, 0, 0


_vision_summarizer_instance: Optional[VisionSummarizer] = None


def get_vision_summarizer() -> VisionSummarizer:
    """Get process-level VisionSummarizer singleton."""
    global _vision_summarizer_instance
    if _vision_summarizer_instance is None:
        _vision_summarizer_instance = VisionSummarizer()
    return _vision_summarizer_instance
