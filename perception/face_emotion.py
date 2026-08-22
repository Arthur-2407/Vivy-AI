"""
perception/face_emotion.py
===========================
Vivy AI — Facial Emotion Classifier
Hardware-adaptive per-face emotion detection engine.

Inputs: Face crop image (numpy BGR array, PIL Image, base64) or FaceData landmarks.
Outputs:
  - Emotion Label: "neutral", "happy", "sad", "angry", "surprised", "fearful", "disgusted"
  - Confidence: 0.0 → 1.0
  - Valence: -1.0 (negative) → +1.0 (positive)
  - Arousal: 0.0 (calm) → +1.0 (excited)
"""

from __future__ import annotations

import os
import base64
import logging
import math
import numpy as np
from typing import Dict, Any, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Check optional deep learning backends
_ONNX_AVAILABLE = False
try:
    import onnxruntime as ort
    _ONNX_AVAILABLE = True
except ImportError:
    pass

_TORCH_AVAILABLE = False
try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    pass

_HSEMOTION_AVAILABLE = False
try:
    from hsemotion.facial_emotions import HSEmotionRecognizer
    _HSEMOTION_AVAILABLE = True
except ImportError:
    pass

_OPENCV_AVAILABLE = False
try:
    import cv2
    if hasattr(cv2, "cvtColor") and hasattr(cv2, "imdecode"):
        _OPENCV_AVAILABLE = True
except Exception as _err:
    print(f"[face_emotion.py] Silenced exception: {_err}")

try:
    from PIL import Image
    from io import BytesIO
except ImportError:
    pass


class FacialEmotion:
    """Dataclass wrapper for predicted facial emotion."""
    def __init__(self, label: str = "neutral", confidence: float = 0.8, valence: float = 0.0, arousal: float = 0.1):
        self.label = label
        self.confidence = float(confidence)
        self.valence = float(valence)
        self.arousal = float(arousal)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "confidence": round(self.confidence, 2),
            "valence": round(self.valence, 2),
            "arousal": round(self.arousal, 2)
        }


class FaceEmotionClassifier:
    """
    Hardware-adaptive facial emotion classifier.
    Supports ONNX FER models with fallback to landmark & facial geometry heuristics.
    """

    def __init__(self, min_confidence: float = 0.5):
        self._min_confidence = min_confidence
        self._onnx_session = None
        self._backend = "Landmark Heuristics"
        self._cfg = self._load_model_config()
        from collections import deque
        self._history = {}  # tracking_id -> deque
        self._init_classifier()

    @staticmethod
    def _load_model_config() -> Dict[str, Any]:
        """Load emotion classification config from perception config_loader."""
        try:
            from perception.config_loader import get, get_absolute_path
            emo_cfg = get("perception_models", "face_emotion", default={})
            if not isinstance(emo_cfg, dict):
                emo_cfg = {}
            return {
                "backend": emo_cfg.get("backend", "auto"),
                "device": emo_cfg.get("device", "auto"),
                "onnx_fer_model_path": get_absolute_path(emo_cfg.get("onnx_fer_model_path", "models/fer/emotion-ferplus-8.onnx")),
                "hsemotion_model_name": emo_cfg.get("hsemotion_model_name", "enet_b0_8_best_vgaf"),
                "min_confidence": float(emo_cfg.get("min_confidence", 0.5)),
            }
        except Exception as ex:
            logger.debug(f"[FaceEmotionClassifier] Config loader unavailable: {ex}. Using defaults.")
            return {
                "backend": "auto",
                "device": "auto",
                "onnx_fer_model_path": "",
                "min_confidence": 0.5,
            }

    def _resolve_device(self) -> str:
        """Resolve 'auto' device preference to 'cpu' or 'gpu' via hardware scheduler."""
        device_pref = self._cfg.get("device", "auto")
        if device_pref in ("cpu", "gpu"):
            return device_pref
        from perception.hardware_scheduler import get_hardware_scheduler
        return get_hardware_scheduler().get_assignment("face_emotion")

    def _init_classifier(self):
        """Initialize emotion classification backends."""
        backend_pref = self._cfg.get("backend", "auto")
        
        # 1. HSEmotion (ResNet18 or enet)
        if backend_pref in ("auto", "hsemotion") and _HSEMOTION_AVAILABLE:
            try:
                if _TORCH_AVAILABLE:
                    original_load = torch.load
                    def unsafe_load(*args, **kwargs):
                        kwargs['weights_only'] = False
                        return original_load(*args, **kwargs)
                    torch.load = unsafe_load

                model_name = self._cfg.get("hsemotion_model_name", "enet_b0_8_best_vgaf")
                device_str = "cuda" if self._resolve_device() == "gpu" and torch.cuda.is_available() else "cpu"
                self._hsemotion = HSEmotionRecognizer(model_name=model_name, device=device_str)
                
                # TEST INFERENCE: Catch timm incompatible checkpoint errors eagerly
                import numpy as np
                test_img = np.zeros((224, 224, 3), dtype=np.uint8)
                self._hsemotion.predict_emotions(test_img, logits=False)
                
                if _TORCH_AVAILABLE:
                    torch.load = original_load
                self._backend = f"HSEmotion ({model_name} on {device_str})"
                logger.info(f"[FaceEmotionClassifier] Initialized {self._backend} backend.")
                return
            except Exception as ex:
                logger.warning(f"[FaceEmotionClassifier] HSEmotion init error: {ex}")

        # 2. ONNX FER Fallback
        if backend_pref in ("auto", "onnx_fer") and _ONNX_AVAILABLE:
            try:
                model_path = self._cfg.get("onnx_fer_model_path", "")
                if model_path and os.path.exists(model_path):
                    device = self._resolve_device()
                    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if device == "gpu" else ["CPUExecutionProvider"]
                    available = ort.get_available_providers()
                    providers = [p for p in providers if p in available] or ["CPUExecutionProvider"]
                    self._onnx_session = ort.InferenceSession(model_path, providers=providers)
                    self._backend = f"ONNX FER ({providers[0].replace('ExecutionProvider', '')})"
                    logger.info(f"[FaceEmotionClassifier] Initialized {self._backend} backend.")
                    return
            except Exception as ex:
                logger.warning(f"[FaceEmotionClassifier] ONNX FER init error: {ex}")

        self._backend = "Facial Geometry & Heuristics"
        logger.info(f"[FaceEmotionClassifier] Initialized backend: {self._backend}")

    def predict(self, face_image: Any, face_landmarks: Optional[Any] = None) -> FacialEmotion:
        """
        Alias for predict_emotion for API compatibility.
        """
        return self.predict_emotion(face_image, face_landmarks)

    def predict_emotion(self, face_image: Any, face_landmarks: Optional[Any] = None) -> FacialEmotion:
        """
        Predict emotion label, confidence, valence, and arousal for a face crop or face landmarks.
        """
        if face_image is None and face_landmarks is None:
            return FacialEmotion("neutral", 0.8, 0.0, 0.1)
            
        tid = getattr(face_landmarks, "tracking_id", 0) if face_landmarks else 0
        if tid not in self._history:
            from collections import deque
            self._history[tid] = deque(maxlen=10)

        img_np = self._to_numpy_bgr(face_image)
        
        raw_pred = None

        # Method 0.5: HSEmotion Model
        if getattr(self, "_hsemotion", None) is not None and img_np is not None and img_np.size > 0:
            try:
                # HSEmotion uses RGB
                img_rgb = cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB) if _OPENCV_AVAILABLE else img_np
                emotion, scores = self._hsemotion.predict_emotions(img_rgb, logits=False)
                
                # Normalize emotion mapping
                # HSEmotion labels: 'Anger', 'Contempt', 'Disgust', 'Fear', 'Happiness', 'Neutral', 'Sadness', 'Surprise'
                em_map = {
                    'Anger': 'angry', 'Contempt': 'disgusted', 'Disgust': 'disgusted', 
                    'Fear': 'fearful', 'Happiness': 'happy', 'Neutral': 'neutral',
                    'Sadness': 'sad', 'Surprise': 'surprised'
                }
                norm_emo = em_map.get(emotion, 'neutral')
                conf = float(np.max(scores)) if isinstance(scores, (list, np.ndarray)) else 0.8
                
                v_map = {"happy": 0.8, "surprised": 0.4, "neutral": 0.0, "sad": -0.6, "angry": -0.8, "disgusted": -0.7, "fearful": -0.6}
                a_map = {"happy": 0.5, "surprised": 0.9, "neutral": 0.1, "sad": 0.2, "angry": 0.8, "disgusted": 0.5, "fearful": 0.8}
                
                return FacialEmotion(norm_emo, conf, v_map.get(norm_emo, 0.0), a_map.get(norm_emo, 0.1))
            except Exception as ex:
                logger.debug(f"[FaceEmotionClassifier] HSEmotion inference failed: {ex}")

        # Method 1.0: ONNX FER Model on face crop image (if available)
        if self._onnx_session is not None and img_np is not None and img_np.size > 0:
            try:
                res = self._predict_from_onnx(img_np)
                if res is not None:
                    raw_pred = res
            except Exception as ex:
                logger.debug(f"[FaceEmotionClassifier] ONNX inference failed: {ex}")

            # Method 1: If landmarks are provided (e.g. from landmark detector / FaceData)
            if face_landmarks is not None:
                raw_pred = self._predict_from_landmarks(face_landmarks)

            # Method 2: Image intensity / aspect ratio / facial geometry heuristics
            elif img_np is not None and img_np.size > 0:
                raw_pred = self._predict_from_image(img_np)
        
        if raw_pred is None:
            raw_pred = FacialEmotion("neutral", 0.8, 0.0, 0.1)
            
        self._history[tid].append(raw_pred)
        
        # Temporal smoothing
        labels = [p.label for p in self._history[tid]]
        import statistics
        try:
            mode_label = statistics.mode(labels)
        except statistics.StatisticsError:
            mode_label = labels[-1]
            
        avg_conf = sum(p.confidence for p in self._history[tid]) / len(self._history[tid])
        avg_val = sum(p.valence for p in self._history[tid]) / len(self._history[tid])
        avg_aro = sum(p.arousal for p in self._history[tid]) / len(self._history[tid])
        
        return FacialEmotion(mode_label, avg_conf, avg_val, avg_aro)

    def _predict_from_onnx(self, img_np: np.ndarray) -> Optional[FacialEmotion]:
        """Run ONNX FER model on face crop."""
        session = self._onnx_session
        if session is None:
            return None

        input_meta = session.get_inputs()[0]
        input_name = input_meta.name
        input_shape = input_meta.shape # e.g. [1, 1, 64, 64] or [1, 3, 224, 224]

        req_c = int(input_shape[1]) if len(input_shape) >= 4 and isinstance(input_shape[1], int) else 1
        req_h = int(input_shape[2]) if len(input_shape) >= 4 and isinstance(input_shape[2], int) else 64
        req_w = int(input_shape[3]) if len(input_shape) >= 4 and isinstance(input_shape[3], int) else 64

        if _OPENCV_AVAILABLE:
            if req_c == 1:
                gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY) if len(img_np.shape) == 3 else img_np
                resized = cv2.resize(gray, (req_w, req_h))
                blob = resized.astype(np.float32) / 255.0
                blob = np.expand_dims(np.expand_dims(blob, axis=0), axis=0)
            else:
                rgb = cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB) if len(img_np.shape) == 3 else img_np
                resized = cv2.resize(rgb, (req_w, req_h))
                blob = resized.transpose(2, 0, 1).astype(np.float32) / 255.0
                blob = np.expand_dims(blob, axis=0)
        else:
            return None

        outputs = session.run(None, {input_name: blob})[0]
        logits = outputs.flatten()

        # Softmax
        exp_l = np.exp(logits - np.max(logits))
        probs = exp_l / np.sum(exp_l)

        labels = ["neutral", "happy", "surprise", "sad", "angry", "disgust", "fear"]
        best_idx = int(np.argmax(probs))
        conf = float(probs[best_idx])
        label = labels[best_idx] if best_idx < len(labels) else "neutral"

        # Map valence / arousal
        v_map = {"happy": 0.8, "surprise": 0.4, "neutral": 0.0, "sad": -0.6, "angry": -0.8, "disgust": -0.7, "fear": -0.6}
        a_map = {"happy": 0.5, "surprise": 0.9, "neutral": 0.1, "sad": 0.2, "angry": 0.8, "disgust": 0.5, "fear": 0.8}

        return FacialEmotion(label, conf, v_map.get(label, 0.0), a_map.get(label, 0.1))

    def _predict_from_landmarks(self, face: Any) -> FacialEmotion:
        """Estimate emotion based on eye openness, EAR, pupil position, and mouth geometry."""
        try:
            left_ear = getattr(getattr(face, "left_eye", None), "ear", 0.3)
            right_ear = getattr(getattr(face, "right_eye", None), "ear", 0.3)
            avg_ear = (left_ear + right_ear) / 2.0

            left_open = getattr(getattr(face, "left_eye", None), "eye_openness", 1.0)
            right_open = getattr(getattr(face, "right_eye", None), "eye_openness", 1.0)
            avg_open = (left_open + right_open) / 2.0

            hp = getattr(face, "head_pose", None)
            pitch = getattr(hp, "pitch", 0.0) if hp else 0.0
            yaw = getattr(hp, "yaw", 0.0) if hp else 0.0

            # Wide open eyes + high pitch -> Surprised
            if avg_ear > 0.38 and avg_open > 0.8:
                return FacialEmotion("surprised", 0.82, 0.4, 0.8)

            # Squinted eyes + neutral pose -> Happy / smiling proxy
            if 0.18 < avg_ear < 0.28 and avg_open > 0.5:
                return FacialEmotion("happy", 0.78, 0.7, 0.4)

            # Very low eye openness (not blink) -> Fatigue / Sad
            if avg_open < 0.25:
                return FacialEmotion("sad", 0.70, -0.4, 0.2)

        except Exception as ex:
            logger.debug(f"[FaceEmotionClassifier] Landmark estimation error: {ex}")

        return FacialEmotion("neutral", 0.85, 0.0, 0.1)

    def _predict_from_image(self, img_np: np.ndarray) -> FacialEmotion:
        """Estimate emotion from face crop image."""
        try:
            h, w = img_np.shape[:2]
            if h < 10 or w < 10:
                return FacialEmotion("neutral", 0.8, 0.0, 0.1)

            gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY) if _OPENCV_AVAILABLE and len(img_np.shape) == 3 else img_np
            
            # Lower 1/3 is mouth region, upper 1/3 is eyes region
            mouth_region = gray[int(h * 0.65):h, :]
            eyes_region = gray[int(h * 0.15):int(h * 0.45), :]

            mouth_std = float(np.std(mouth_region)) if mouth_region.size > 0 else 0.0
            eyes_std = float(np.std(eyes_region)) if eyes_region.size > 0 else 0.0
            overall_std = float(np.std(gray))

            # High variance in mouth region often corresponds to smile / open mouth
            if mouth_std > overall_std * 1.15:
                return FacialEmotion("happy", 0.76, 0.65, 0.35)

            # High contrast in eyes + low mouth variance -> Surprised / Focused
            if eyes_std > overall_std * 1.2:
                return FacialEmotion("surprised", 0.72, 0.3, 0.7)

        except Exception as ex:
            logger.debug(f"[FaceEmotionClassifier] Image heuristics error: {ex}")

        return FacialEmotion("neutral", 0.85, 0.0, 0.1)

    def _to_numpy_bgr(self, image_data: Any) -> Optional[np.ndarray]:
        if image_data is None:
            return None
        if isinstance(image_data, np.ndarray):
            return image_data
        if isinstance(image_data, str):
            try:
                b64_str = image_data.split(",", 1)[1] if "," in image_data else image_data
                raw_bytes = base64.b64decode(b64_str)
                if _OPENCV_AVAILABLE:
                    nparr = np.frombuffer(raw_bytes, np.uint8)
                    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            except Exception as _err:
                print(f"[face_emotion.py] Silenced exception: {_err}")
        return None


_emotion_classifier_instance: Optional[FaceEmotionClassifier] = None


def get_face_emotion_classifier() -> FaceEmotionClassifier:
    """Get process-level FaceEmotionClassifier singleton."""
    global _emotion_classifier_instance
    if _emotion_classifier_instance is None:
        _emotion_classifier_instance = FaceEmotionClassifier()
    return _emotion_classifier_instance
