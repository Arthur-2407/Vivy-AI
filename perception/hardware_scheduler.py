"""
perception/hardware_scheduler.py
=================================
Vivy AI — CPU / GPU Adaptive Scheduler
Dynamically distributes workloads across CPU and GPU based on real-time system utilization,
active Vivy modules (Avatar ON/OFF), latency targets, and thermal/power state.

Modes:
  1. Avatar OFF Mode: Perception runs on CPU using lightweight optimized inference (OpenCV,
     MediaPipe CPU, ONNX CPU), reserving GPU for LLM inference.
  2. Avatar ON Mode: Avatar rendering and blendshapes run on GPU; perception leverages GPU
     (CUDA, DirectML, Vulkan) where beneficial.
  3. Balanced Hybrid Mode: Splits perception tasks across CPU and GPU under heavy load.

Features live dynamic migration without requiring process restarts.
"""

from __future__ import annotations

import os
import sys
import logging
import threading
import time
from typing import Dict, Any, Optional

from perception.perception_state import HardwareSchedulerState

logger = logging.getLogger(__name__)

# Preferred Hardware Preference Settings
PREF_AUTO = "Auto"
PREF_CPU  = "CPU"
PREF_GPU  = "GPU"


class HardwareScheduler:
    """
    Adaptive Hardware Scheduler for Vivy's perception and compute modules.
    Thread-safe and non-blocking.
    """

    def __init__(self, check_interval_seconds: float = 2.0):
        self._lock = threading.Lock()
        self._running = False
        self._check_interval = check_interval_seconds
        self._thread: Optional[threading.Thread] = None

        # User preference overrides ("Auto", "CPU", "GPU")
        self._preference = PREF_AUTO

        # Telemetry metrics
        self._cpu_utilization: float = 0.0
        self._gpu_utilization: float = 0.0
        self._vram_used_mb: float    = 0.0
        self._vram_total_mb: float   = 0.0
        self._ram_used_mb: float     = 0.0

        # State flags
        self._avatar_active: bool      = False
        self._llm_active: bool         = False
        self._tts_active: bool         = False
        self._current_backend: str     = "CPU"
        self._current_mode: str        = "Avatar OFF Mode"
        self._migration_count: int     = 0
        self._last_perception_fps: float = 30.0
        self._last_latency_ms: float   = 15.0

        # Detect available hardware backends
        self._available_backends = self._detect_backends()

    def _detect_backends(self) -> Dict[str, bool]:
        """Probe available execution backends on startup."""
        backends = {
            "CPU": True,
            "CUDA": False,
            "DirectML": False,
            "Vulkan": False,
            "ONNX_CPU": True,
            "ONNX_GPU": False,
        }

        # Probe CUDA via torch if available
        try:
            import torch
            if torch.cuda.is_available():
                backends["CUDA"] = True
                backends["ONNX_GPU"] = True
                logger.info(f"[HardwareScheduler] NVIDIA CUDA detected: {torch.cuda.get_device_name(0)}")
        except Exception as _err:
            print(f"[hardware_scheduler.py] Silenced exception: {_err}")

        # Probe DirectML / Vulkan support on Windows
        if os.name == 'nt':
            try:
                import torch_directml
                backends["DirectML"] = True
                logger.info("[HardwareScheduler] DirectML hardware acceleration available.")
            except Exception as _err:
                print(f"[hardware_scheduler.py] Silenced exception: {_err}")

        return backends

    def start(self):
        """Start the background telemetry and adaptive migration loop."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._telemetry_loop,
                daemon=True,
                name="HardwareScheduler-Loop"
            )
            self._thread.start()
            logger.info("[HardwareScheduler] Started adaptive hardware telemetry loop.")

    def stop(self):
        """Stop background telemetry loop."""
        with self._lock:
            self._running = False
        logger.info("[HardwareScheduler] Stopped.")

    def set_user_preference(self, pref: str):
        """Set user preference: Auto, CPU, or GPU."""
        if pref in (PREF_AUTO, PREF_CPU, PREF_GPU):
            with self._lock:
                self._preference = pref
            self._evaluate_policy()

    def update_avatar_state(self, is_active: bool):
        """Notify scheduler of avatar rendering state changes (Avatar ON / OFF)."""
        with self._lock:
            changed = (self._avatar_active != is_active)
            self._avatar_active = is_active
        if changed:
            logger.info(f"[HardwareScheduler] Avatar state updated: ON={is_active}")
            self._evaluate_policy()

    def update_llm_state(self, is_active: bool):
        """Notify scheduler when LLM inference starts or completes."""
        with self._lock:
            self._llm_active = is_active
        self._evaluate_policy()

    def update_telemetry(self, fps: float = 30.0, latency_ms: float = 15.0):
        """Record current perception frame rate and latency."""
        with self._lock:
            self._last_perception_fps = fps
            self._last_latency_ms = latency_ms

    def get_assignment(self, task_name: str) -> str:
        """
        Query recommended device assignment for a specific perception task.
        Tasks: 'face_detection', 'face_embedding', 'object_detection',
               'face_emotion', 'vision_summary', 'hand_tracking',
               'gaze_estimation', 'attention_scoring', 'avatar_anim'
        Returns: 'cpu' or 'gpu'
        """
        with self._lock:
            mode = self._current_mode
            backend = self._current_backend
            pref = self._preference
            has_cuda = self._available_backends.get("CUDA", False)

        if pref == PREF_CPU:
            return "cpu"
        if pref == PREF_GPU and has_cuda:
            return "gpu"

        # Tasks that benefit significantly from GPU acceleration
        gpu_heavy_tasks = ("face_detection", "face_embedding", "object_detection", "vision_summary")
        cpu_light_tasks = ("hand_tracking", "gaze_estimation", "attention_scoring", "presence_management")

        if task_name in cpu_light_tasks:
            return "cpu"

        if not has_cuda:
            return "cpu"

        # Adaptive policy based on Mode for GPU-heavy tasks
        if mode == "Avatar OFF Mode":
            # GPU available — allow ONNX / TensorRT / CUDA acceleration for key vision tasks
            # while leaving ample VRAM for LLM inference
            if task_name in ("face_detection", "object_detection"):
                return "gpu"
            return "cpu"

        elif mode == "Avatar ON Mode":
            # Avatar + Vision both active — run neural vision models on GPU
            if task_name in gpu_heavy_tasks or task_name == "avatar_anim":
                return "gpu"
            return "cpu"

        else: # Balanced Hybrid Mode
            # Split tasks: face & object detection on GPU, auxiliary on CPU
            if task_name in ("face_detection", "object_detection", "landmark_mesh"):
                return "gpu"
            return "cpu"

    def get_state(self) -> HardwareSchedulerState:
        """Get current telemetry state snapshot."""
        with self._lock:
            return HardwareSchedulerState(
                backend=self._current_backend,
                mode=self._current_mode,
                cpu_utilization=self._cpu_utilization,
                gpu_utilization=self._gpu_utilization,
                vram_used_mb=self._vram_used_mb,
                vram_total_mb=self._vram_total_mb,
                fps=self._last_perception_fps,
                perception_latency_ms=self._last_latency_ms,
                migration_count=self._migration_count,
            )

    # ── Internal telemetry and policy evaluation ──────────────────────────────

    def _telemetry_loop(self):
        while self._running:
            try:
                self._sample_hardware_metrics()
                self._evaluate_policy()
            except Exception as ex:
                logger.debug(f"[HardwareScheduler] Telemetry error: {ex}")
            time.sleep(self._check_interval)

    def _sample_hardware_metrics(self):
        # Sample CPU utilization via psutil if available
        try:
            import psutil
            cpu_pct = psutil.cpu_percent(interval=None)
            with self._lock:
                self._cpu_utilization = float(cpu_pct)
        except Exception as _err:
            print(f"[hardware_scheduler.py] Silenced exception: {_err}")

        # Sample GPU utilization & VRAM via torch if available
        try:
            import torch
            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated(0) / (1024 * 1024)
                total = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)
                with self._lock:
                    self._vram_used_mb = float(allocated)
                    self._vram_total_mb = float(total)
                    # Simple heuristic proxy for GPU utilization based on VRAM/activity
                    if self._llm_active or self._avatar_active:
                        self._gpu_utilization = min(95.0, max(20.0, (allocated / total) * 100.0 + 30.0))
                    else:
                        self._gpu_utilization = max(0.0, (allocated / total) * 100.0)
        except Exception as _err:
            print(f"[hardware_scheduler.py] Silenced exception: {_err}")

    def _evaluate_policy(self):
        """Evaluate adaptive scheduling policy and execute dynamic migration if needed."""
        with self._lock:
            pref = self._preference
            avatar_on = self._avatar_active
            llm_active = self._llm_active
            cpu_load = self._cpu_utilization
            gpu_load = self._gpu_utilization
            has_cuda = self._available_backends.get("CUDA", False)
            has_dml = self._available_backends.get("DirectML", False)

        new_mode = "Avatar OFF Mode"
        new_backend = "CPU"

        if pref == PREF_CPU:
            new_mode = "CPU Only Mode"
            new_backend = "CPU"
        elif pref == PREF_GPU and (has_cuda or has_dml):
            new_mode = "GPU Only Mode"
            new_backend = "CUDA" if has_cuda else "DirectML"
        else:
            # Auto policy evaluation
            if not avatar_on:
                # Avatar OFF Mode: CPU preferred
                new_mode = "Avatar OFF Mode"
                new_backend = "CPU"
            elif avatar_on and not llm_active:
                # Avatar ON Mode (GPU available for avatar + perception)
                new_mode = "Avatar ON Mode"
                new_backend = "CUDA" if has_cuda else ("DirectML" if has_dml else "CPU")
            else:
                # Both Avatar ON and LLM active (Heavy load) -> Hybrid Mode
                if cpu_load > 80.0 and has_cuda:
                    new_mode = "Balanced Hybrid Mode"
                    new_backend = "CUDA"
                else:
                    new_mode = "Balanced Hybrid Mode"
                    new_backend = "CPU"

        with self._lock:
            mode_changed = (self._current_mode != new_mode)
            backend_changed = (self._current_backend != new_backend)

            if mode_changed or backend_changed:
                self._migration_count += 1
                self._current_mode = new_mode
                self._current_backend = new_backend
                logger.info(
                    f"[HardwareScheduler] Dynamic workload migration #{self._migration_count}: "
                    f"Mode='{new_mode}', Backend='{new_backend}' (CPU={cpu_load:.1f}%, GPU={gpu_load:.1f}%)"
                )


_scheduler_instance: Optional[HardwareScheduler] = None
_scheduler_lock = threading.Lock()


def get_hardware_scheduler() -> HardwareScheduler:
    """Get process-level HardwareScheduler singleton."""
    global _scheduler_instance
    if _scheduler_instance is None:
        with _scheduler_lock:
            if _scheduler_instance is None:
                _scheduler_instance = HardwareScheduler()
                _scheduler_instance.start()
    return _scheduler_instance
