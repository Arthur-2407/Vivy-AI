"""
Vivy Hub - Sync Manager
Orchestrates event synchronization between the primary host and connected nodes.
"""
import threading
from hub.event_log import EventLog, SyncEvent
from typing import List, Dict

class SyncManager:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self._event_log = EventLog.get_instance()
        # Track last sequence acknowledged by each device
        self._device_cursors: Dict[str, int] = {}
        
    @classmethod
    def get_instance(cls) -> "SyncManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def register_device(self, device_id: str, starting_sequence: int = 0):
        with self._lock:
            if device_id not in self._device_cursors:
                self._device_cursors[device_id] = starting_sequence

    def sync_to_device(self, device_id: str) -> List[SyncEvent]:
        """Fetch all events a device needs to catch up."""
        with self._lock:
            cursor = self._device_cursors.get(device_id, 0)
            events = self._event_log.get_events_since(cursor)
            if events:
                # Assuming successful delivery for this mock
                self._device_cursors[device_id] = events[-1].sequence
                print(f"[SyncManager] Synced {len(events)} events to {device_id}")
            return events
            
    def receive_from_device(self, events: List[SyncEvent]):
        """Receive a batch of events from a remote device, handle conflicts if needed."""
        with self._lock:
            for ev in events:
                # Basic idempotency: check if event_id already exists
                existing = [e for e in self._event_log._events if e.event_id == ev.event_id]
                if not existing:
                    # Append it. Real implementation needs conflict resolution based on timestamp/sequence
                    self._event_log._events.append(ev)
            self._event_log._events.sort(key=lambda x: x.timestamp)
            if events:
                print(f"[SyncManager] Merged {len(events)} remote events into the EventLog")
