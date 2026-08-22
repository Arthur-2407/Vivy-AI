"""
Vivy Hub - Vital Monitor
Monitors system resources and predicts overload to drive graceful degradation and task offloading.
"""
import time
import threading
from enum import Enum
from typing import Dict, Any

class SystemHealth(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    FAILING = "FAILING"

class VitalMonitor:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        # Gracefully bind to existing telemetry manager
        try:
            from telemetry_manager import get_telemetry_manager
            self._telemetry = get_telemetry_manager()
        except ImportError:
            self._telemetry = None
            
        self.current_health = SystemHealth.HEALTHY
        self._history = []
        
    @classmethod
    def get_instance(cls) -> "VitalMonitor":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def evaluate_health(self) -> SystemHealth:
        """Evaluate the overall health based on VRAM, CPU, queue depth, etc."""
        with self._lock:
            if not self._telemetry:
                return SystemHealth.HEALTHY
                
            metrics = self._telemetry.get_health_status()
            subsystems = metrics.get("subsystems", {})
            
            # Simple heuristic using existing Vivy backend telemetry
            gpu_metrics = subsystems.get("GPU", {}).get("metrics", {})
            cpu_usage = subsystems.get("Backend", {}).get("metrics", {}).get("cpu_percent", 0)
            
            vram_pressure = 0
            if gpu_metrics.get("physical_vram_total", 0) > 0:
                used = gpu_metrics.get("physical_vram_used", 0)
                total = gpu_metrics.get("physical_vram_total", 1)
                vram_pressure = used / total
                
            if vram_pressure > 0.9 or cpu_usage > 90:
                self.current_health = SystemHealth.CRITICAL
            elif vram_pressure > 0.75 or cpu_usage > 75:
                self.current_health = SystemHealth.DEGRADED
            else:
                self.current_health = SystemHealth.HEALTHY
                
            return self.current_health
