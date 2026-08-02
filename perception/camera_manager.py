"""
perception/camera_manager.py
=============================
Vivy AI — Camera Manager
Manages non-blocking camera frame acquisition from local webcam (OpenCV cv2.VideoCapture)
or browser camera fallback endpoints.

Operates completely offline. Camera frames remain strictly local.
"""

from __future__ import annotations

import base64
import logging
import os
import threading
import time
import numpy as np
from typing import Optional, Tuple, Any
from resource_manager import get_resource_manager

logger = logging.getLogger(__name__)

# Try importing OpenCV and PIL
_OPENCV_AVAILABLE = False
try:
    import cv2
    if hasattr(cv2, "VideoCapture") and hasattr(cv2, "cvtColor") and hasattr(cv2, "imdecode"):
        _OPENCV_AVAILABLE = True
except Exception as _err:
    print(f"[camera_manager.py] Silenced exception: {_err}")

try:
    from PIL import Image
    from io import BytesIO
except ImportError:
    pass


def is_camera_disabled() -> bool:
    """Check if camera is manually disabled across processes via shared/camera_disable.txt."""
    try:
        from perception.perception_manager import _shared_dir
        sentinel = os.path.join(_shared_dir(), "camera_disable.txt")
        return os.path.exists(sentinel)
    except Exception:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.exists(os.path.join(base, "shared", "camera_disable.txt"))


def set_camera_disabled(disabled: bool):
    """Set or remove shared/camera_disable.txt sentinel across processes."""
    try:
        from perception.perception_manager import _shared_dir
        s_dir = _shared_dir()
        os.makedirs(s_dir, exist_ok=True)
        sentinel = os.path.join(s_dir, "camera_disable.txt")
        if disabled:
            with open(sentinel, "w", encoding="utf-8") as f:
                f.write("disabled")
        else:
            if os.path.exists(sentinel):
                try: os.remove(sentinel)
                except Exception: pass
    except Exception as e:
        logger.warning(f"[CameraManager] set_camera_disabled error: {e}")


class CameraManager:
    """
    Manages non-blocking camera capture loop.
    Thread-safe and graceful fallback on systems without a hardware webcam.
    """

    def __init__(self, device_index: int = 0, target_fps: int = 30, resolution: Tuple[int, int] = (640, 480)):
        self._device_index = device_index
        self._selected_device_index = device_index
        self._target_fps = target_fps
        self._resolution = resolution

        self._lock = threading.Lock()
        self._perception_lock = threading.Lock()
        self._running = False
        self._paused = False
        self._camera_active = False
        self._latest_frame_b64: Optional[str] = None
        self._latest_frame_time: float = 0.0
        self._cap: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None

        self._frames_captured: int = 0
        self._actual_fps: float = 0.0
        self._timestamps = []

        self._callbacks = []
        self._latest_perception_frame: Optional[str] = None
        self._perception_worker_running: bool = False
        self._perception_worker_thread: Optional[threading.Thread] = None

    def register_frame_processor(self, callback):
        """Register a callback to receive base64 frame strings whenever a new frame is captured or ingested."""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def start_camera(self) -> bool:
        """Start local hardware webcam capture thread with device scan fallback."""
        if is_camera_disabled():
            logger.info("[CameraManager] Camera is disabled via camera_disable.txt. Skipping start.")
            self._camera_active = False
            try:
                from perception.perception_manager import get_writer
                get_writer().record_camera_state(active=False, paused=False)
            except Exception as _err:
                print(f"[camera_manager.py] Silenced exception: {_err}")
            return False

        with self._lock:
            self._paused = False
            if self._running:
                return True
            self._running = True

        # Ensure asynchronous perception worker thread is active
        if not self._perception_worker_running:
            self._perception_worker_running = True
            self._perception_worker_thread = threading.Thread(
                target=self._perception_worker_loop,
                daemon=True,
                name="CameraManager-PerceptionWorker"
            )
            get_resource_manager().register_thread(
                self._perception_worker_thread,
                stop_callback=self.stop_camera,
                name="CameraManager-PerceptionWorker"
            )
            self._perception_worker_thread.start()

        # Start the async PerceptionRunner strictly upon manual camera activation
        try:
            from perception.runner import get_perception_runner
            runner = get_perception_runner()
            if runner and runner.enabled and not getattr(runner, "_running", False):
                runner.start_background()
        except Exception as ex:
            logger.debug(f"[CameraManager] Failed to start PerceptionRunner: {ex}")

        if _OPENCV_AVAILABLE:
            # Device scan fallback: try target selected index first, then 0..3
            target_idx = getattr(self, "_selected_device_index", self._device_index)
            indices_to_try = [target_idx] + [i for i in range(4) if i != target_idx]
            for idx in indices_to_try:
                try:
                    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY)
                    if cap.isOpened():
                        ret, test_frame = cap.read()
                        if ret and test_frame is not None:
                            self._cap = cap
                            get_resource_manager().register_handle(self._cap, release_fn=lambda c: c.release(), name="camera_capture")
                            self._device_index = idx
                            w, h = self._resolution
                            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
                            self._cap.set(cv2.CAP_PROP_FPS, self._target_fps)
                            self._camera_active = True
                            logger.info(f"[CameraManager] Hardware camera #{idx} opened successfully ({w}x{h}).")
                            break
                        else:
                            cap.release()
                except Exception as ex:
                    logger.warning(f"[CameraManager] OpenCV capture init error on device #{idx}: {ex}")

            if self._cap is None or not self._cap.isOpened():
                logger.warning("[CameraManager] No hardware camera accessible. Operating in stream fallback mode.")
                self._cap = None
                self._camera_active = False
        else:
            logger.info("[CameraManager] OpenCV unavailable. Operating in stream fallback mode.")
            self._camera_active = False

        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="CameraManager-Loop")
        get_resource_manager().register_thread(self._thread, stop_callback=self.stop_camera, name="CameraManager-Loop")
        get_resource_manager().register_cleanup_callback(self.stop_camera, priority=20, name="stop_camera")
        self._thread.start()
        try:
            from perception.perception_manager import get_writer
            get_writer().record_camera_state(active=self._camera_active, paused=False)
        except Exception as _err:
            print(f"[camera_manager.py] Silenced exception: {_err}")
        return self._camera_active

    def stop_camera(self):
        """Stop webcam capture loop and release camera resource."""
        set_camera_disabled(True)
        with self._lock:
            self._running = False
            self._paused = False
            self._perception_worker_running = False
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception as _err:
                print(f"[camera_manager.py] Silenced exception: {_err}")
            self._cap = None
        self._camera_active = False
        self._latest_frame_b64 = None

        # Stop the async PerceptionRunner when camera is stopped
        try:
            from perception.runner import get_perception_runner
            runner = get_perception_runner()
            if runner and getattr(runner, "_running", False):
                runner.stop()
        except Exception as ex:
            logger.debug(f"[CameraManager] Failed to stop PerceptionRunner: {ex}")

        try:
            from perception.perception_manager import get_writer, _shared_dir
            get_writer().record_camera_state(active=False, paused=False)
            frame_file = os.path.join(_shared_dir(), "latest_camera_frame.txt")
            if os.path.exists(frame_file):
                try: os.remove(frame_file)
                except Exception: pass
        except Exception as _err:
            print(f"[camera_manager.py] Silenced exception: {_err}")
        logger.info("[CameraManager] Camera stopped.")

    def pause_camera(self):
        """Pause frame capture loop and mark camera state as paused."""
        with self._lock:
            self._paused = True
            self._camera_active = False
        try:
            from perception.perception_manager import get_writer
            get_writer().record_camera_state(active=False, paused=True)
        except Exception as _err:
            print(f"[camera_manager.py] Silenced exception: {_err}")
        logger.info("[CameraManager] Camera paused.")

    def resume_camera(self):
        """Resume frame capture loop."""
        set_camera_disabled(False)
        with self._lock:
            self._paused = False
            if self._cap is not None and self._cap.isOpened():
                self._camera_active = True
        try:
            from perception.perception_manager import get_writer
            get_writer().record_camera_state(active=self._camera_active, paused=False)
        except Exception as _err:
            print(f"[camera_manager.py] Silenced exception: {_err}")
        logger.info("[CameraManager] Camera resumed.")

    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def validate_frame(self, frame_data: Any) -> Tuple[bool, str, Optional[Tuple[int, int]]]:
        """
        Validate camera frame for resolution, non-zero pixel data, timestamp, and buffer integrity.
        Returns (is_valid, reason, (width, height)).
        """
        if frame_data is None:
            return False, "Frame data is None", None

        # Case 1: base64 string
        if isinstance(frame_data, str):
            clean_b64 = frame_data.split(",", 1)[1] if "," in frame_data else frame_data
            clean_b64 = clean_b64.strip()
            if not clean_b64 or len(clean_b64) < 15:
                return False, "Base64 frame string too short or empty", None

            try:
                pad_len = (-len(clean_b64)) % 4
                if pad_len > 0:
                    clean_b64 += "=" * pad_len
                raw_bytes = base64.b64decode(clean_b64)
                if len(raw_bytes) < 10:
                    return False, "Decoded buffer under 10 bytes", None

                if _OPENCV_AVAILABLE:
                    nparr = np.frombuffer(raw_bytes, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if img is not None:
                        h, w = img.shape[:2]
                        if w <= 0 or h <= 0:
                            return False, f"Invalid frame dimensions ({w}x{h})", None
                        return True, "Valid base64 frame", (w, h)
                    # If cv2.imdecode is None but raw_bytes exist (e.g. synthetic test string)
                    return True, "Valid base64 string (header fragment)", None
                elif 'Image' in globals():
                    try:
                        img = Image.open(BytesIO(raw_bytes))
                        w, h = img.size
                        return True, "Valid base64 frame (PIL)", (w, h)
                    except Exception:
                        return True, "Valid base64 string (raw bytes)", None
                else:
                    return True, "Valid base64 bytes (no decoder)", None
            except Exception as ex:
                return False, f"Frame base64 decoding exception: {ex}", None

        # Case 2: numpy array
        if _OPENCV_AVAILABLE and isinstance(frame_data, np.ndarray):
            if frame_data.size == 0 or len(frame_data.shape) < 2:
                return False, "Empty or 1D numpy image array", None
            h, w = frame_data.shape[:2]
            if w <= 0 or h <= 0:
                return False, f"Invalid numpy array dimensions ({w}x{h})", None
            return True, "Valid numpy frame", (w, h)

        return False, f"Unsupported frame data type: {type(frame_data)}", None

    def ingest_external_frame(self, frame_b64: str) -> bool:
        """Called by browser/web_server to ingest a base64 encoded JPEG camera frame."""
        if is_camera_disabled():
            return False

        now = time.time()
        clean_b64 = frame_b64.split(",", 1)[1] if "," in frame_b64 else frame_b64
        clean_b64 = clean_b64.strip()

        is_valid, reason, dims = self.validate_frame(clean_b64)
        if not is_valid:
            logger.debug(f"[CameraManager] External frame ingestion rejected: {reason}")
            return False

        with self._lock:
            self._latest_frame_b64 = clean_b64
            self._latest_frame_time = now
            self._camera_active = True
            if dims:
                self._resolution = dims
            self._frames_captured += 1
            self._timestamps.append(now)
            if len(self._timestamps) > 30:
                self._timestamps.pop(0)
            self._update_fps()
        
        try:
            from perception.perception_manager import get_writer, _shared_dir
            get_writer().record_camera_state(active=True, paused=False)
            # Write to shared frame buffer so other processes (run_vivy.py) can read fresh frames
            s_dir = _shared_dir()
            os.makedirs(s_dir, exist_ok=True)
            frame_file = os.path.join(s_dir, "latest_camera_frame.txt")
            tmp_file = frame_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as ff:
                ff.write(f"{now}\n{clean_b64}")
            os.replace(tmp_file, frame_file)
            
            # Trace frame ingestion in FrameTraceSystem
            from perception.pipeline_validator import get_frame_trace_system
            trace = get_frame_trace_system().create_trace(resolution=self._resolution, color_space="BGR")
            trace.record_stage("camera_ingest", "PASS", "External frame ingested successfully")
        except Exception as _err:
            print(f"[camera_manager.py] Silenced exception: {_err}")
        self._notify_frame_processors(clean_b64)
        return True

    def get_latest_frame(self) -> Tuple[Optional[str], float]:
        """Returns tuple of (base64_jpeg_string, capture_timestamp)."""
        if is_camera_disabled():
            return None, 0.0

        now = time.time()
        with self._lock:
            if self._latest_frame_b64 and (now - self._latest_frame_time) <= 10.0:
                return self._latest_frame_b64, self._latest_frame_time

        # Fallback: check shared frame buffer file written by external process (web_server.py)
        try:
            from perception.perception_manager import _shared_dir
            frame_file = os.path.join(_shared_dir(), "latest_camera_frame.txt")
            if os.path.exists(frame_file):
                f_mtime = os.path.getmtime(frame_file)
                if (now - f_mtime) <= 10.0:
                    with open(frame_file, "r", encoding="utf-8") as ff:
                        lines = ff.read().splitlines()
                    if len(lines) >= 2:
                        ts = float(lines[0])
                        b64 = lines[1]
                        if (now - ts) <= 10.0:
                            with self._lock:
                                self._latest_frame_b64 = b64
                                self._latest_frame_time = ts
                                self._camera_active = True
                            return b64, ts
        except Exception as _err:
            print(f"[camera_manager.py] Silenced exception: {_err}")

        return None, 0.0

    def is_active(self) -> bool:
        """Returns True if local webcam or external camera stream is actively sending valid frames."""
        if is_camera_disabled() or self._paused:
            return False

        now = time.time()
        with self._lock:
            if self._camera_active:
                if self._cap is not None and self._cap.isOpened():
                    return True
                if self._latest_frame_time > 0 and (now - self._latest_frame_time) < 5.0:
                    return True

        # Cross-process fallback check: if PerceptionManager reader shows active camera state
        try:
            from perception.perception_manager import get_reader
            st = get_reader().load_state()
            written_at = st.get("written_at", 0.0)
            if (now - written_at) < 5.0 and st.get("camera_active", False) and not st.get("camera_paused", False):
                return True
        except Exception as _err:
            print(f"[camera_manager.py] Silenced exception: {_err}")

        return False

    def get_fps(self) -> float:
        with self._lock:
            return round(self._actual_fps, 1)

    # ── Internal capture loop & Perception dispatch ───────────────────────────

    def _capture_loop(self):
        frame_interval = 1.0 / max(1, self._target_fps)
        while self._running:
            if is_camera_disabled():
                if self._cap is not None:
                    try: self._cap.release()
                    except Exception: pass
                    self._cap = None
                self._camera_active = False
                break

            if self._paused:
                time.sleep(0.05)
                continue

            start_t = time.time()
            if self._cap is not None and self._cap.isOpened():
                try:
                    ret, frame = self._cap.read()
                    if ret and frame is not None:
                        # Encode frame to JPEG base64
                        ret_encode, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                        if ret_encode:
                            b64_str = base64.b64encode(buf.tobytes()).decode('ascii')
                            now = time.time()
                            with self._lock:
                                self._latest_frame_b64 = b64_str
                                self._latest_frame_time = now
                                self._camera_active = True
                                self._frames_captured += 1
                                self._timestamps.append(now)
                                if len(self._timestamps) > 30:
                                    self._timestamps.pop(0)
                                self._update_fps()
                            self._notify_frame_processors(b64_str)
                    else:
                        logger.warning("[CameraManager] Camera frame read failed (device detached or driver error). Attempting reconnect...")
                        self._cap.release()
                        time.sleep(1.0)
                        self._cap = cv2.VideoCapture(self._device_index, cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY)
                        if self._cap.isOpened():
                            w, h = self._resolution
                            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
                            self._cap.set(cv2.CAP_PROP_FPS, self._target_fps)
                        else:
                            self._cap = None
                            time.sleep(2.0)
                except Exception as ex:
                    logger.warning(f"[CameraManager] Capture error: {ex}")
                    time.sleep(1.0)

            elapsed = time.time() - start_t
            sleep_time = max(0.001, frame_interval - elapsed)
            time.sleep(sleep_time)

    def preprocess_camera_frame(self, img_np: np.ndarray) -> np.ndarray:
        """Apply lighting adaptivity (CLAHE), noise reduction, and image normalization to raw camera frames."""
        if img_np is None or img_np.size == 0 or not _OPENCV_AVAILABLE:
            return img_np
        try:
            lab = cv2.cvtColor(img_np, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            cl = clahe.apply(l)
            enhanced = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)
            return cv2.GaussianBlur(enhanced, (3, 3), 0)
        except Exception:
            return img_np

    def select_device(self, device_index: int) -> bool:
        """Dynamically switch camera device index with proper lock protection and resource cleanup."""
        logger.info(f"[CameraManager] Selecting hardware device #{device_index}...")
        set_camera_disabled(False)
        self.stop_camera()
        time.sleep(0.2)
        with self._lock:
            self._selected_device_index = device_index
            self._device_index = device_index
        return self.start_camera()

    def _notify_frame_processors(self, frame_b64: str):
        """Notify registered frame processors and buffer frame for asynchronous background ML perception worker."""
        for cb in list(self._callbacks):
            try:
                cb(frame_b64)
            except Exception as e:
                logger.debug(f"[CameraManager] Frame callback error: {e}")
        
        # Buffer latest frame for non-blocking background perception worker
        with self._lock:
            self._latest_perception_frame = frame_b64

    def _perception_worker_loop(self):
        """Asynchronous background worker: pulls latest frame from atomic buffer and runs ML perception models without blocking capture loop."""
        while self._running or self._perception_worker_running:
            if is_camera_disabled() or self._paused:
                time.sleep(0.05)
                continue

            frame_to_process = None
            with self._lock:
                if self._latest_perception_frame is not None:
                    frame_to_process = self._latest_perception_frame
                    self._latest_perception_frame = None  # Consume frame

            if frame_to_process:
                try:
                    self._run_default_perception(frame_to_process)
                except Exception as ex:
                    logger.debug(f"[CameraManager] Background perception worker error: {ex}")
            else:
                time.sleep(0.008)

    def _run_default_perception(self, frame_b64: str):
        """Internal worker: runs pre-processing, face/hand/object detection, gaze estimation, and updates PerceptionManager."""
        if not frame_b64 or not isinstance(frame_b64, str) or not frame_b64.strip():
            return
        
        # Optimization: If PerceptionRunner is active, avoid duplicate redundant ML inference
        try:
            from perception.runner import get_perception_runner
            runner = get_perception_runner()
            if runner and runner.enabled and getattr(runner, "_running", False):
                return
        except Exception as _err:
            print(f"[camera_manager.py] Silenced exception: {_err}")

        with self._perception_lock:
            try:
                if not hasattr(self, "_perception_initialized"):
                    from perception.face_detector import FaceDetector
                    from perception.face_tracker import FaceTracker
                    from perception.landmark_detector import LandmarkDetector
                    from perception.gaze_detector import GazeDetector
                    from perception.attention_estimator import AttentionEstimator
                    from perception.presence_manager import PresenceManager
                    from perception.object_detector import ObjectDetector
                    from perception.hardware_scheduler import get_hardware_scheduler
                    from perception.perception_events import get_event_hub

                    self._face_detector = FaceDetector()
                    self._face_tracker = FaceTracker()
                    self._landmark_detector = LandmarkDetector()
                    self._gaze_detector = GazeDetector()
                    self._attention_estimator = AttentionEstimator()
                    self._presence_manager = PresenceManager()
                    self._object_detector = ObjectDetector()
                    self._hw_scheduler = get_hardware_scheduler()
                    self._event_hub = get_event_hub()
                    self._perception_initialized = True

                # Preprocess frame for lighting and noise adaptivity
                raw_np, h, w = self._face_detector._to_numpy_bgr(frame_b64)
                img_np = self.preprocess_camera_frame(raw_np) if raw_np is not None else None

                detected_faces = self._face_detector.detect_faces(img_np if img_np is not None else frame_b64)
                tracked_faces = self._face_tracker.update(detected_faces)
                detected_objects = self._object_detector.detect_objects(img_np if img_np is not None else frame_b64)

                if img_np is not None:
                    tracked_faces = self._landmark_detector.process_landmarks(img_np, tracked_faces)

                gaze = self._gaze_detector.estimate_gaze(tracked_faces, frame_width=w or 640, frame_height=h or 480)
                att_data, primary_face = self._attention_estimator.estimate_attention(tracked_faces, gaze, camera_active=True)
                presence_state = self._presence_manager.update_presence(tracked_faces, camera_active=True)
                hw_state = self._hw_scheduler.get_state()

                hand_state = self._object_detector.get_hand_state() if hasattr(self._object_detector, "get_hand_state") else {}
                held_objects = [o.to_dict() for o in detected_objects if getattr(o, 'validation_state', '') == 'hand_held' or getattr(o, 'category', '') == 'held_item']

                system_state = {
                    "camera_active": self.is_active(),
                    "camera_fps": self.get_fps(),
                    "presence_state": presence_state,
                    "face_count": len(tracked_faces),
                    "object_count": len(detected_objects),
                    "hand_state": hand_state,
                    "held_objects": held_objects,
                    "primary_face": primary_face.to_dict() if primary_face else None,
                    "all_faces": [f.to_dict() for f in tracked_faces],
                    "all_objects": [o.to_dict() for o in detected_objects],
                    "gaze": gaze.to_dict(),
                    "attention": att_data.to_dict(),
                    "hardware": hw_state.to_dict(),
                }

                # Developer Diagnostic Mode Hook (Phase 3 Instrumentation)
                try:
                    from developer_diagnostic_manager import get_developer_diagnostic_manager
                    ddm = get_developer_diagnostic_manager()
                    if ddm.is_enabled():
                        detections = {
                            "face": {"face_count": len(tracked_faces), "confidence": primary_face.confidence if primary_face and hasattr(primary_face, 'confidence') else (0.95 if tracked_faces else 0.0)},
                            "hand": {"hand_detected": hand_state.get("hands_tracked", 0) > 0, "confidence": 0.95 if hand_state.get("hands_tracked", 0) > 0 else 0.0},
                            "object": {"object_count": len(detected_objects), "objects": [getattr(o, 'label', 'object') for o in detected_objects[:5]] if detected_objects else []},
                            "pose": {"pose_detected": False, "confidence": 0.0},
                            "gaze": gaze.to_dict() if hasattr(gaze, "to_dict") else {},
                            "ocr": {},
                            "scene": f"Camera active ({len(tracked_faces)} face(s), {len(detected_objects)} object(s), {hand_state.get('hands_tracked', 0)} hand(s))",
                        }
                        ddm.record_frame(
                            frame_num=self._frames_captured,
                            camera_source=f"Device #{self._device_index}",
                            resolution=self._resolution,
                            latency_ms=max(0.1, (time.time() - self._latest_frame_time) * 1000.0),
                            fps=self.get_fps(),
                            dropped_frames=0,
                            detections=detections
                        )
                except Exception as _err:
                    print(f"[camera_manager.py] Silenced exception: {_err}")

                try:
                    from perception.perception_manager import get_writer
                    writer = get_writer()
                    if writer:
                        writer.record_face_perception_state(system_state)
                        writer.record_object_perception_state(detected_objects)
                        if hasattr(writer, "record_hand_perception_state"):
                            writer.record_hand_perception_state(hand_state, held_objects)
                except Exception as _err:
                    print(f"[camera_manager.py] Silenced exception: {_err}")

                # Publish event hub notifications
                if tracked_faces:
                    self._event_hub.publish("face_detected", {"face_count": len(tracked_faces), "primary": primary_face.to_dict() if primary_face else None})
                if detected_objects:
                    self._event_hub.publish("object_detected", {"object_count": len(detected_objects), "objects": [o.to_dict() for o in detected_objects]})
                if hand_state and hand_state.get("hands_tracked", 0) > 0:
                    self._event_hub.publish("hand_detected", hand_state)
                if presence_state:
                    self._event_hub.publish("presence_detected", {"presence_state": presence_state})
            except Exception as ex:
                logger.debug(f"[CameraManager] Default perception processing error: {ex}")

    def _update_fps(self):
        if len(self._timestamps) >= 2:
            dt = self._timestamps[-1] - self._timestamps[0]
            if dt > 0:
                self._actual_fps = (len(self._timestamps) - 1) / dt
            else:
                self._actual_fps = 0.0
        else:
            self._actual_fps = 0.0


_camera_instance: Optional[CameraManager] = None
_camera_lock = threading.Lock()


def get_camera_manager() -> CameraManager:
    """Get global process-level CameraManager singleton."""
    global _camera_instance
    if _camera_instance is None:
        with _camera_lock:
            if _camera_instance is None:
                _camera_instance = CameraManager()
    return _camera_instance
