"""
Vivy Hub - Offload Manager
Handles graceful degradation and task offloading when Vital Monitor reports DEGRADED or CRITICAL states.
"""
import threading
from hub.vital_monitor import VitalMonitor, SystemHealth

class OffloadManager:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self._monitor = VitalMonitor.get_instance()
        
    @classmethod
    def get_instance(cls) -> "OffloadManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def should_offload(self, task_priority: int) -> bool:
        """
        Determines if a task should be offloaded based on system health and priority.
        task_priority: 0 (Safety), 1 (Active User), 2 (Realtime Perception), 3-7 (Background/Evolution)
        """
        health = self._monitor.evaluate_health()
        
        if health == SystemHealth.CRITICAL:
            # Under critical pressure, offload everything except P0 and P1
            if task_priority > 1:
                return True
        elif health == SystemHealth.DEGRADED:
            # Under degraded pressure, offload background tasks (P4-P7)
            if task_priority > 3:
                return True
                
        return False
        
    def throttle_system(self):
        """Invoke throttle policies (e.g. pause learning, reduce FPS)"""
        health = self._monitor.evaluate_health()
        if health in (SystemHealth.CRITICAL, SystemHealth.DEGRADED):
            print(f"[OffloadManager] System {health.value}. Throttling noncritical background tasks.")
            # In a full implementation, this would trigger events on the AGI event bus to pause queues
