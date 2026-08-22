"""
perception/runner.py
====================
Vivy AI — Perception Runner
Orchestrates live perception services (Face Detection, Gaze Detection, Facial Emotion Detection, Vision Summary).
Streams structured events into Vivy Core in real-time.
(Upgraded for Phase 4: Async modular architecture with hardware pooling)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from typing import Optional, Dict, Any, List

from perception.connectors.perception_connector import PerceptionConnector
from perception.perception_manager import get_writer, get_reader
from perception.camera_manager import get_camera_manager

# Import new async scheduler and workers
from perception.pipeline.execution_scheduler import ExecutionScheduler
from perception.pipeline.gpu_workers import GPUWorkerPool
from perception.pipeline.cpu_workers import CPUWorkerPool

logger = logging.getLogger(__name__)

_OPENCV_AVAILABLE = False
try:
    import cv2
    if hasattr(cv2, "cvtColor") and hasattr(cv2, "imdecode"):
        _OPENCV_AVAILABLE = True
except Exception as _err:
    print(f"[runner.py] Silenced exception: {_err}")


class PerceptionRunner:
    """
    Live Perception Runner service.
    """

    def __init__(self, source: Any = 0, fps: int = 5, uri: str = "ws://127.0.0.1:8765/perception", enabled: bool = True):
        self.source = source
        self.fps = fps
        self.interval = 1.0 / max(1, fps)
        self.enabled = enabled

        self.scheduler = ExecutionScheduler()
        self.gpu_pool = GPUWorkerPool(max_workers=2)
        self.cpu_pool = CPUWorkerPool(max_workers=4)

        self.connector = PerceptionConnector(uri=uri)
        self.camera_manager = get_camera_manager()

        self.frame_id = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # State tracking for reaction rules
        self._consecutive_eye_contact_count = 0
        self._last_primary_emotion = "neutral"
        self._consent_store_visual_memory = False # Memory policy: short-term context by default
        
        # State tracking for async pipeline (allows output fusion at varying frequencies)
        self._last_known_faces = []
        self._last_known_objects = []
        self._last_known_scene = {"scene": "initializing", "ocr": [], "motion": False, "frame_size": [0, 0]}
        
        class FallbackGaze:
            eye_contact_score = 0.0
            gaze_direction = "Unknown"
            eye_contact_strength = "None"
            def to_dict(self): return {"eye_contact_score": 0.0, "gaze_direction": "Unknown", "eye_contact_strength": "None"}
        self._last_known_gaze = FallbackGaze()
        self._last_known_hands = {}

    def start_background(self):
        """Start the perception runner in a background daemon thread."""
        if not self.enabled:
            logger.info("[PerceptionRunner] Disabled via flag. Skipping startup.")
            return

        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_thread_loop, daemon=True, name="PerceptionRunner-Thread")
        self._thread.start()
        logger.info(f"[PerceptionRunner] Started background perception runner loop at {self.fps} FPS.")

    def stop(self):
        """Stop perception runner loop."""
        self._running = False
        # Do NOT shutdown pools here, so we can restart the runner without reloading heavy ML models.
        # self.gpu_pool.shutdown()
        # self.cpu_pool.shutdown()
        logger.info("[PerceptionRunner] Stopped perception runner.")

    async def run(self):
        """Async runner loop for direct asyncio execution."""
        if not self.enabled:
            logger.info("[PerceptionRunner] Perception runner disabled.")
            return

        self._running = True
        await self.connector.connect()
        logger.info(f"[PerceptionRunner] Async runner active at {self.fps} FPS.")

        while self._running:
            start_t = time.time()
            try:
                await self._process_single_frame_async()
            except Exception as ex:
                logger.debug(f"[PerceptionRunner] Async step error: {ex}")

            elapsed = time.time() - start_t
            await asyncio.sleep(max(0.01, self.interval - elapsed))

    def _run_thread_loop(self):
        """Thread worker loop creating its own event loop for async scheduling."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self.connector.connect())
        
        while self._running:
            start_t = time.time()
            try:
                self._loop.run_until_complete(self._process_single_frame_async())
            except Exception as ex:
                logger.debug(f"[PerceptionRunner] Thread step error: {ex}")

            elapsed = time.time() - start_t
            sleep_time = max(0.01, self.interval - elapsed)
            time.sleep(sleep_time)

    def _process_single_frame_sync(self):
        """Legacy synchronous single frame processing step (forwarded to async)."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._process_single_frame_async(), self._loop).result()
        else:
            asyncio.run(self._process_single_frame_async())

    async def _process_single_frame_async(self):
        """Asynchronous single frame processing step with scheduler."""
        frame_b64, frame_time = self.camera_manager.get_latest_frame()
        now = time.time()
        
        # Fast path conversion
        img_np, h, w = (None, 0, 0)
        
        # Zero-copy AI memory path
        if hasattr(self.camera_manager, "get_latest_raw_frame"):
            raw_np, _ = self.camera_manager.get_latest_raw_frame()
            if raw_np is not None:
                img_np = raw_np
                h, w = img_np.shape[:2]

        if img_np is None and self.gpu_pool.face_detector and frame_b64:
            img_np, h, w = self.gpu_pool.face_detector._to_numpy_bgr(frame_b64)

        status_flag = "active"
        if img_np is None:
            # Degraded / Standby mode when camera frame is not arriving or is stale
            status_flag = "degraded"
            event = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "frame_id": self.frame_id,
                "faces": [],
                "vision_summary": {"scene": "no camera frame available", "ocr": [], "motion": False, "frame_size": [0, 0]},
                "vision_status": status_flag
            }
            self.connector.publish_event(event)
            self.frame_id += 1

            # Check if an external process recently recorded active camera or face detection
            reader = get_reader()
            if reader:
                current_state = reader.load_state()
                # If file read failed due to locks, current_state might be {}. We should preserve the active state 
                # if we have no clear proof it's stale.
                if not current_state:
                    return
                    
                written_at = current_state.get("written_at", 0.0)
                if (now - written_at) < 15.0 and (current_state.get("camera_active", False) or current_state.get("face_count", 0) > 0):
                    return

            # Notify PerceptionManagerWriter of missing frame state
            writer = get_writer()
            if writer:
                cam_active = self.camera_manager.is_active()
                writer.record_face_perception_state({
                    "camera_active": cam_active,
                    "presence_state": "Camera OFF" if not cam_active else "User Missing",
                    "face_count": 0,
                    "primary_face": None,
                    "gaze": {"gaze_direction": "Unknown", "eye_contact_score": 0.0, "eye_contact_strength": "None"},
                    "attention": {"attention_score": 0.0, "engagement_score": 0.0, "presence_score": 0.0},
                    "hardware": {
                        "backend": self.gpu_pool.face_detector.get_backend_name() if self.gpu_pool.face_detector else "CPU",
                        "mode": "Standby Mode"
                    }
                })
            return

        # ── 1. Dispatch independent GPU vision models ──
        tasks = {}
        
        if self.scheduler.should_execute("face_detection", now):
            tasks["faces"] = asyncio.create_task(self.gpu_pool.detect_faces_async(img_np))
            self.scheduler.mark_executed("face_detection", now)
            
        if self.scheduler.should_execute("object_detection", now):
            tasks["objects"] = asyncio.create_task(self.gpu_pool.detect_objects_async(img_np))
            self.scheduler.mark_executed("object_detection", now)
            
        if self.scheduler.should_execute("scene_understanding", now):
            tasks["scene"] = asyncio.create_task(self.gpu_pool.summarize_scene_async(img_np))
            self.scheduler.mark_executed("scene_understanding", now)

        if tasks:
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for i, key in enumerate(tasks.keys()):
                res = results[i]
                if not isinstance(res, Exception):
                    if key == "faces": self._last_known_faces = res
                    elif key == "objects": self._last_known_objects = res
                    elif key == "scene": self._last_known_scene = res
                else:
                    logger.debug(f"[PerceptionRunner] {key} task failed: {res}")

        faces = self._last_known_faces
        objects = self._last_known_objects
        scene_summary = self._last_known_scene

        # ── 2. Dispatch dependent tracking/CPU tasks ──
        tracking_tasks = {}
        
        if self.scheduler.should_execute("gaze_estimation", now) and faces:
            tracking_tasks["gaze"] = asyncio.create_task(self.cpu_pool.estimate_gaze_async(faces, w, h))
            self.scheduler.mark_executed("gaze_estimation", now)
            
        if self.scheduler.should_execute("hand_tracking", now):
            tracking_tasks["hands"] = asyncio.create_task(self.cpu_pool.track_hands_async(img_np))
            self.scheduler.mark_executed("hand_tracking", now)
            
        if self.scheduler.should_execute("emotion", now) and faces:
            async def get_emotions():
                emos = []
                for f in faces:
                    if img_np is not None and len(img_np.shape) >= 2 and f.bbox.width > 0 and f.bbox.height > 0:
                        bx, by, bw, bh = f.bbox.x, f.bbox.y, f.bbox.width, f.bbox.height
                        face_img = img_np[max(0, by):min(h, by + bh), max(0, bx):min(w, bx + bw)]
                        if face_img is not None and face_img.size > 0:
                            emo = await self.gpu_pool.predict_emotion_async(face_img, f)
                            emos.append(emo)
                        else:
                            class FallbackEmo:
                                label = "neutral"
                                confidence = 0.5
                                valence = 0.0
                                arousal = 0.0
                                def to_dict(self): return {"label": self.label, "confidence": self.confidence}
                            emos.append(FallbackEmo())
                    else:
                        class FallbackEmo:
                            label = "neutral"
                            confidence = 0.5
                            valence = 0.0
                            arousal = 0.0
                            def to_dict(self): return {"label": self.label, "confidence": self.confidence}
                        emos.append(FallbackEmo())
                return emos
            tracking_tasks["emotion"] = asyncio.create_task(get_emotions())
            self.scheduler.mark_executed("emotion", now)

        emotions = []
        if tracking_tasks:
            results = await asyncio.gather(*tracking_tasks.values(), return_exceptions=True)
            for i, key in enumerate(tracking_tasks.keys()):
                res = results[i]
                if not isinstance(res, Exception):
                    if key == "gaze": self._last_known_gaze = res
                    elif key == "hands": self._last_known_hands = res
                    elif key == "emotion": emotions = res
                else:
                    logger.debug(f"[PerceptionRunner] {key} task failed: {res}")
                    
        gaze_data = self._last_known_gaze
        hand_state = self._last_known_hands

        # ── 3. Fused Event Construction ──
        face_events: List[Dict[str, Any]] = []
        primary_emo_label = "neutral"
        primary_emo_conf = 0.8

        for idx, f in enumerate(faces):
            emo = emotions[idx] if idx < len(emotions) else None
            
            if emo:
                f.emotion_label = emo.label
                f.emotion_confidence = emo.confidence
                f.valence = emo.valence
                f.arousal = emo.arousal
                if f.is_primary:
                    primary_emo_label = emo.label
                    primary_emo_conf = emo.confidence
            
            face_events.append({
                "id": f"face_{f.tracking_id:03d}",
                "bbox": [f.bbox.x, f.bbox.y, f.bbox.width, f.bbox.height],
                "confidence": float(f.confidence),
                "gaze": {
                    "vector": [f.center_point.x, f.center_point.y, f.center_point.z],
                    "eye_contact_prob": float(gaze_data.eye_contact_score),
                    "gaze_direction": gaze_data.gaze_direction
                },
                "emotion": emo.to_dict() if emo else {"label": "neutral", "confidence": 0.5}
            })

        object_events = [o.to_dict() for o in objects]

        event = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "frame_id": self.frame_id,
            "faces": face_events,
            "objects": object_events,
            "vision_summary": scene_summary,
            "vision_status": status_flag
        }

        # 4. Publish event via PerceptionConnector
        self.connector.publish_event(event)
        self.frame_id += 1

        # 5. Core Reaction Rules & Vivy State Updates
        self._apply_reaction_rules(faces, gaze_data, primary_emo_label, primary_emo_conf, scene_summary, objects, hand_state)

    def _apply_reaction_rules(self, faces: List[Any], gaze_data: Any, primary_emo_label: str, primary_emo_conf: float, scene_summary: Dict[str, Any], objects: List[Any] = None, hand_state: Dict[str, Any] = None):
        """
        Apply core Vivy reaction rules based on asynchronous output.
        """
        writer = get_writer()

        # Rule 1: Presence & Eye Contact Tracking
        has_faces = bool(faces)
        eye_contact_prob = gaze_data.eye_contact_score if has_faces else 0.0

        if eye_contact_prob >= 0.7:
            self._consecutive_eye_contact_count += 1
        else:
            self._consecutive_eye_contact_count = 0

        sustained_eye_contact = (self._consecutive_eye_contact_count >= 2)

        # Trigger Avatar Gaze Target & Animation when eye contact sustained
        if sustained_eye_contact:
            self._trigger_avatar_animation("head_turn_to_user")

        # Rule 3: Micro-expression trigger on emotion label change
        if primary_emo_label != self._last_primary_emotion and primary_emo_conf >= 0.7:
            self._last_primary_emotion = primary_emo_label
            if primary_emo_label == "happy":
                self._trigger_avatar_animation("smile")
            elif primary_emo_label == "surprised":
                self._trigger_avatar_animation("surprised_gasp")
            elif primary_emo_label in ("sad", "angry"):
                self._trigger_avatar_animation("empathy_nod")

        # Update PerceptionManagerWriter
        if writer:
            reader = get_reader()
            if reader and not has_faces:
                current_state = reader.load_state()
                if not current_state:
                    return
                    
                now = time.time()
                written_at = current_state.get("written_at", 0.0)
                if (now - written_at) < 15.0 and current_state.get("camera_active", False) and (
                    current_state.get("face_count", 0) > 0 or current_state.get("presence_state") in ("User Present", "User Returned", "Multiple People")
                ):
                    return

            from perception.perception_state import PerceptionSystemState, HardwareSchedulerState, AttentionData
            
            p_state = PerceptionSystemState(
                camera_active=True,
                presence_state="User Present" if has_faces else "User Missing",
                primary_face=faces[0] if faces else None,
                all_faces=faces,
                gaze=gaze_data,
                attention=AttentionData(
                    attention_score=100.0 if sustained_eye_contact else (75.0 if has_faces else 0.0),
                    engagement_score=90.0 if sustained_eye_contact else 50.0,
                    presence_score=100.0 if has_faces else 0.0,
                ),
                hardware=HardwareSchedulerState(
                    backend=self.gpu_pool.face_detector.get_backend_name() if self.gpu_pool.face_detector else "CPU",
                    mode="Live Perception Active" if has_faces else "Standby Mode"
                )
            )
            state_update = p_state.to_dict()
            writer.record_face_perception_state(state_update)
            if objects is not None:
                writer.record_object_perception_state(objects)
            if hand_state:
                writer.record_hand_perception_state(hand_state)
            if scene_summary and isinstance(scene_summary, dict) and "scene" in scene_summary:
                writer.record_camera_vlm_caption(scene_summary["scene"])

    def _trigger_avatar_animation(self, trigger_name: str):
        """Send animation trigger via sentinel file to isolate main venv from avatar bridge."""
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            trigger_file = os.path.join(base_dir, "shared", "animation_trigger.txt")
            os.makedirs(os.path.join(base_dir, "shared"), exist_ok=True)
            with open(trigger_file, "w", encoding="utf-8") as f:
                f.write(trigger_name)
        except Exception as _err:
            print(f"[runner.py] Silenced exception: {_err}")


_runner_instance: Optional[PerceptionRunner] = None


def get_perception_runner(enabled: bool = True) -> PerceptionRunner:
    """Get global process-level PerceptionRunner singleton."""
    global _runner_instance
    if _runner_instance is None:
        _runner_instance = PerceptionRunner(enabled=enabled)
    return _runner_instance
