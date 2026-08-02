"""
perception/pipeline/execution_scheduler.py
==========================================
Asynchronous execution scheduler for Vivy AI Perception System.
Controls inference frequencies for GPU and CPU workers.
"""

import time
import logging
import asyncio
from typing import Dict, Any, Callable, List

logger = logging.getLogger(__name__)

class ExecutionScheduler:
    """
    Decouples perception tasks from the main camera frame rate.
    Maintains target frequencies for different models to optimize CPU/GPU usage.
    """
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Default target frequencies as requested by architecture
        self.target_fps = {
            "face_detection": float(self.config.get("face_detection_fps", 15.0)),
            "face_tracking": float(self.config.get("face_tracking_fps", 30.0)),
            "face_recognition": float(self.config.get("face_recognition_fps", 2.0)), # Periodic refresh
            "liveness": float(self.config.get("liveness_fps", 5.0)),
            "object_detection": float(self.config.get("object_detection_fps", 10.0)),
            "hand_tracking": float(self.config.get("hand_tracking_fps", 30.0)),
            "gesture_recognition": float(self.config.get("gesture_recognition_fps", 15.0)),
            "pose_estimation": float(self.config.get("pose_estimation_fps", 15.0)),
            "gaze_estimation": float(self.config.get("gaze_estimation_fps", 15.0)),
            "scene_understanding": float(self.config.get("scene_understanding_fps", 1.0)),
            "ocr": float(self.config.get("ocr_fps", 0.0)), # 0 means on-demand or event-driven
            "emotion": float(self.config.get("emotion_fps", 15.0)),
        }
        
        self.last_execution = {k: 0.0 for k in self.target_fps}
        
    def should_execute(self, task_name: str, current_time: float) -> bool:
        """Check if a task should run based on its target frequency."""
        target = self.target_fps.get(task_name, 0.0)
        if target <= 0:
            return False # On demand only
            
        elapsed = current_time - self.last_execution.get(task_name, 0.0)
        if elapsed >= (1.0 / target):
            return True
        return False
        
    def mark_executed(self, task_name: str, current_time: float):
        """Update the last execution timestamp for a task."""
        self.last_execution[task_name] = current_time

    def force_execute(self, task_name: str, current_time: float):
        """Force a task to execute (e.g. for on-demand OCR)."""
        self.last_execution[task_name] = 0.0 # Will trigger next check
