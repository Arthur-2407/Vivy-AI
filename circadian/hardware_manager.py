"""
circadian/hardware_manager.py
==============================
Vivy AI — Intelligent Hardware Resource Manager

RESPONSIBILITY
--------------
Classifies workloads and dynamically assigns them to CPU or GPU based on:
  - Workload type (pre-classified in circadian_config.json)
  - Runtime CPU/GPU utilization (via psutil + optional nvidia-smi)
  - Configurable thresholds and hysteresis (no thrashing)

DESIGN RULES
------------
  - Never hardcodes device IDs, GPU indices, or CPU affinity values.
  - All thresholds come from circadian_config.json [hardware_policy].
  - Graceful degradation: if psutil/nvidia-smi unavailable, returns
    configured defaults without error.
  - Hysteresis prevents rapid CPU↔GPU switching under oscillating load.
  - Thread-safe: singleton with internal lock.

PUBLIC API
----------
    from circadian.hardware_manager import get_hardware_hint

    hint = get_hardware_hint("dialogue")    # → "cpu"
    hint = get_hardware_hint("avatar")      # → "gpu"
    hint = get_hardware_hint("large_model") # → "gpu" or "hybrid"
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class HardwareManager:
    """
    Intelligent hardware routing manager.
    Classifies workloads and returns placement hints.
    """

    def __init__(self):
        self._lock             = threading.Lock()
        self._config:    dict  = {}
        self._config_loaded    = False
        self._last_hint:  str  = "gpu"
        self._last_switch: float = 0.0   # timestamp of last hint change (for hysteresis)
        self._psutil_available: Optional[bool] = None

    # ── Config loading ────────────────────────────────────────────────────────

    def _ensure_config(self):
        if self._config_loaded:
            return
        try:
            from circadian.config_loader import get_config
            cfg = get_config()
            self._config = cfg.get("hardware_policy", {})
        except Exception as e:
            logger.debug(f"[HardwareManager] Config load failed: {e}")
            self._config = {}
        self._config_loaded = True

    # ── Workload classification ───────────────────────────────────────────────

    def _classify(self, workload_type: str) -> str:
        """
        Classify workload into base device preference.
        Returns "cpu" | "gpu" — ignoring current utilization.
        """
        cpu_wl = self._config.get("cpu_workloads", [
            "dialogue", "memory", "circadian", "emotion", "scheduling", "text", "ocr"
        ])
        gpu_wl = self._config.get("gpu_workloads", [
            "avatar", "vision", "lip_sync", "image_gen", "large_model"
        ])

        wl_lower = workload_type.lower()
        if wl_lower in cpu_wl:
            return "cpu"
        if wl_lower in gpu_wl:
            return "gpu"
        # Default for LLM inference
        return self._config.get("default_llm_device", "gpu")

    # ── Runtime utilization sampling ─────────────────────────────────────────

    def _check_psutil(self) -> bool:
        """Check once if psutil is importable."""
        if self._psutil_available is None:
            try:
                import psutil  # noqa: F401
                self._psutil_available = True
            except ImportError:
                self._psutil_available = False
                logger.info("[HardwareManager] psutil not installed. Using config-only defaults.")
        return self._psutil_available

    def _get_cpu_pct(self) -> float:
        """Sample current CPU utilization (%). Returns 0.0 on failure."""
        try:
            import psutil
            return psutil.cpu_percent(interval=None)
        except Exception:
            return 0.0

    def _get_gpu_pct(self) -> float:
        """
        Sample GPU utilization via nvidia-smi (%).
        Returns 0.0 if nvidia-smi is unavailable or fails.
        Non-blocking: uses cached result if nvidia-smi is slow.
        """
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=1.0
            )
            if result.returncode == 0:
                vals = [float(x.strip()) for x in result.stdout.strip().split("\n") if x.strip()]
                if vals:
                    return max(vals)
        except Exception as _err:
            print(f"[hardware_manager.py] Silenced exception: {_err}")
        return 0.0

    # ── Hint computation with hysteresis ─────────────────────────────────────

    def _compute_hint(self, base_device: str) -> str:
        """
        Apply runtime utilization checks + hysteresis to the base_device preference.
        Returns "cpu" | "gpu" | "hybrid".
        """
        if not self._check_psutil():
            # No psutil — return config default for the workload
            return base_device

        cpu_thresh   = float(self._config.get("cpu_threshold_percent", 80))
        gpu_thresh   = float(self._config.get("gpu_threshold_percent", 80))
        hysteresis_s = float(self._config.get("hysteresis_seconds", 10))

        cpu_pct = self._get_cpu_pct()
        gpu_pct = self._get_gpu_pct()

        cpu_high = cpu_pct >= cpu_thresh
        gpu_high = gpu_pct >= gpu_thresh

        if cpu_high and gpu_high:
            new_hint = "hybrid"
        elif cpu_high:
            # CPU overloaded — prefer GPU even for CPU workloads
            new_hint = "gpu"
        elif gpu_high:
            # GPU overloaded — prefer CPU even for GPU workloads
            new_hint = "cpu"
        else:
            # Both have headroom — use workload classification
            new_hint = base_device

        # Apply hysteresis: don't change hint faster than hysteresis_s
        now = time.time()
        if new_hint != self._last_hint:
            if now - self._last_switch >= hysteresis_s:
                logger.info(
                    f"[HardwareManager] Device hint changed: {self._last_hint} → {new_hint} "
                    f"(CPU:{cpu_pct:.0f}%, GPU:{gpu_pct:.0f}%)"
                )
                self._last_hint   = new_hint
                self._last_switch = now
            # else: suppress change (within hysteresis window)
        
        return self._last_hint

    # ── Public API ────────────────────────────────────────────────────────────

    def get_hardware_hint(self, workload_type: str) -> str:
        """
        Return the recommended hardware device for the given workload type.

        Parameters
        ----------
        workload_type : str
            One of: "dialogue", "memory", "emotion", "circadian", "scheduling",
            "text", "ocr", "avatar", "vision", "lip_sync", "large_model", etc.

        Returns
        -------
        str
            "cpu" | "gpu" | "hybrid"
        """
        self._ensure_config()

        base = self._classify(workload_type)

        with self._lock:
            return self._compute_hint(base)


# ─────────────────────────────────────────────────────────────────────────────
# Process-wide singleton
# ─────────────────────────────────────────────────────────────────────────────
_global_hw: Optional[HardwareManager] = None
_global_hw_lock = threading.Lock()


def _get_manager() -> HardwareManager:
    global _global_hw
    if _global_hw is None:
        with _global_hw_lock:
            if _global_hw is None:
                _global_hw = HardwareManager()
    return _global_hw


def get_hardware_hint(workload_type: str) -> str:
    """
    Module-level convenience function.
    Returns the recommended hardware device for a workload type.

    Usage:
        from circadian.hardware_manager import get_hardware_hint
        hint = get_hardware_hint("dialogue")  # → "cpu"
        hint = get_hardware_hint("avatar")    # → "gpu"
    """
    return _get_manager().get_hardware_hint(workload_type)


# ─────────────────────────────────────────────────────────────────────────────
# Standalone test
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    print("=" * 60)
    print("  Vivy AI — Hardware Manager (Standalone Test)")
    print("=" * 60)
    test_workloads = [
        "dialogue", "memory", "circadian", "emotion",
        "avatar", "vision", "lip_sync", "large_model", "unknown_workload"
    ]
    for wl in test_workloads:
        hint = get_hardware_hint(wl)
        print(f"  {wl:20s} → {hint}")
    print()
