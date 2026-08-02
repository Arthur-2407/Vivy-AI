"""
perception/frame_scheduler.py
==============================
Vivy AI — Perception Frame Scheduler
Asynchronous, adaptive frame scheduler that routes camera frames through the vision, face,
gaze, landmark, and presence analysis pipeline without blocking conversation, TTS, or LLM response loops.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Optional, Dict, Any

logger = logging.getLogger(__name__)


class FrameScheduler:
    """
    Adaptive frame processing scheduler with back-pressure handling and dynamic frame skipping.
    Target frame rate: 15–60 FPS (adaptive under load).
    """

    def __init__(self, max_queue_size: int = 30):
        self._queue = queue.Queue(maxsize=max_queue_size)
        self._lock = threading.Lock()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._processor_callback: Optional[Callable[[str, float], None]] = None

        self._frames_queued: int = 0
        self._frames_processed: int = 0
        self._frames_dropped: int = 0
        self._target_fps: float = 30.0
        self._current_fps: float = 0.0
        self._last_process_time: float = 0.0
        self._timestamps = []

    def register_processor(self, callback: Callable[[str, float], None]):
        """Register the downstream perception pipeline processing callback."""
        with self._lock:
            self._processor_callback = callback

    def start(self):
        """Start the background processing worker thread."""
        with self._lock:
            if self._running:
                return
            self._running = True

        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="FrameScheduler-Worker"
        )
        self._worker_thread.start()
        logger.info("[FrameScheduler] Started asynchronous frame scheduler worker.")

    def stop(self):
        """Stop background worker thread."""
        with self._lock:
            self._running = False
        logger.info("[FrameScheduler] Stopped.")

    def submit_frame(self, frame_b64: str, timestamp: float = 0.0) -> bool:
        """
        Submit a base64 JPEG frame for asynchronous processing.
        Drops frame if queue is saturated to maintain sub-50ms perception latency.
        """
        if not self._running:
            self.start()

        ts = timestamp or time.time()
        with self._lock:
            self._frames_queued += 1

        try:
            # Non-blocking put with automatic queue trim on overflow
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                    with self._lock:
                        self._frames_dropped += 1
                except queue.Empty:
                    pass

            self._queue.put_nowait((frame_b64, ts))
            return True
        except queue.Full:
            with self._lock:
                self._frames_dropped += 1
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Return scheduler telemetry metrics."""
        with self._lock:
            return {
                "frames_queued": self._frames_queued,
                "frames_processed": self._frames_processed,
                "frames_dropped": self._frames_dropped,
                "current_fps": round(self._current_fps, 1),
                "queue_depth": self._queue.qsize(),
            }

    # ── Internal worker loop ──────────────────────────────────────────────────

    def _worker_loop(self):
        while self._running:
            try:
                item = self._queue.get(timeout=0.5)
                frame_b64, ts = item
                try:
                    start_t = time.time()
                    callback = None
                    with self._lock:
                        callback = self._processor_callback

                    if callback is not None:
                        callback(frame_b64, ts)

                    now = time.time()
                    with self._lock:
                        self._frames_processed += 1
                        self._last_process_time = now - start_t
                        self._timestamps.append(now)
                        if len(self._timestamps) > 30:
                            self._timestamps.pop(0)
                        self._update_fps()
                except Exception as ex:
                    logger.error(f"[FrameScheduler] Processing error: {ex}")
                finally:
                    self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"[FrameScheduler] Worker loop error: {e}")

    def _update_fps(self):
        if len(self._timestamps) >= 2:
            dt = self._timestamps[-1] - self._timestamps[0]
            if dt > 0:
                self._current_fps = (len(self._timestamps) - 1) / dt
            else:
                self._current_fps = 0.0
        else:
            self._current_fps = 0.0


_scheduler_instance: Optional[FrameScheduler] = None
_scheduler_lock = threading.Lock()


def get_frame_scheduler() -> FrameScheduler:
    """Get global process-level FrameScheduler singleton."""
    global _scheduler_instance
    if _scheduler_instance is None:
        with _scheduler_lock:
            if _scheduler_instance is None:
                _scheduler_instance = FrameScheduler()
                _scheduler_instance.start()
    return _scheduler_instance
