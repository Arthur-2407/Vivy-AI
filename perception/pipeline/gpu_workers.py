"""
perception/pipeline/gpu_workers.py
==================================
Dedicated GPU worker thread pool handling neural inference.
Wraps YOLOv11, RetinaFace, InsightFace, MiniFASNet, and Florence-2.
"""

import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional
import numpy as np
import time

logger = logging.getLogger(__name__)

class GPUWorkerPool:
    """
    Manages GPU-intensive perception tasks.
    Executes tasks in a dedicated thread pool to prevent blocking the main orchestration loop.
    """
    def __init__(self, max_workers: int = 2):
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="GPUWorker")
        self._init_models()

    def _init_models(self):
        """Initialize models, substituting equivalents if requested models are unavailable."""
        try:
            from perception.face_detector import FaceDetector
            self.face_detector = FaceDetector() # Handles RetinaFace/InsightFace internally with fallbacks
        except Exception as e:
            logger.warning(f"[GPUWorker] Failed to init FaceDetector: {e}")
            self.face_detector = None

        try:
            from perception.object_detector import ObjectDetector
            self.object_detector = ObjectDetector() # Target: YOLOv11s (fallback to existing YOLO/MobileNet)
        except Exception as e:
            logger.warning(f"[GPUWorker] Failed to init ObjectDetector: {e}")
            self.object_detector = None

        try:
            from perception.face_emotion import get_face_emotion_classifier
            self.emotion_classifier = get_face_emotion_classifier()
        except Exception as e:
            logger.warning(f"[GPUWorker] Failed to init Emotion Classifier: {e}")
            self.emotion_classifier = None

        try:
            from perception.vision_summary import get_vision_summarizer
            self.scene_summarizer = get_vision_summarizer() # Target: Florence-2 Base
        except Exception as e:
            logger.warning(f"[GPUWorker] Failed to init Vision Summarizer: {e}")
            self.scene_summarizer = None
            
        # Target: MiniFASNet (Liveness) - Placeholder for integration
        self.liveness_detector = None 

    async def detect_faces_async(self, img_np: np.ndarray) -> List[Any]:
        """Run face detection asynchronously."""
        if not self.face_detector:
            return []
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self.face_detector.detect_faces, img_np)

    async def detect_objects_async(self, img_np: np.ndarray) -> List[Any]:
        """Run object detection asynchronously."""
        if not self.object_detector:
            return []
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self.object_detector.detect_objects, img_np)

    async def predict_emotion_async(self, face_img: np.ndarray, face_landmarks: Any = None) -> Any:
        """Run emotion classification asynchronously."""
        if not self.emotion_classifier or face_img is None:
            # Return neutral fallback
            class FallbackEmo:
                label = "neutral"
                confidence = 0.5
                valence = 0.0
                arousal = 0.0
                def to_dict(self): return {"label": self.label, "confidence": self.confidence}
            return FallbackEmo()
            
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self.emotion_classifier.predict_emotion, face_img, face_landmarks)

    async def summarize_scene_async(self, img_np: np.ndarray) -> Dict[str, Any]:
        """Run scene summarization asynchronously."""
        if not self.scene_summarizer:
            return {"scene": "unavailable", "ocr": [], "motion": False, "frame_size": [0,0]}
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self.scene_summarizer.summarize_scene, img_np)
        
    def shutdown(self):
        self.executor.shutdown(wait=False)
