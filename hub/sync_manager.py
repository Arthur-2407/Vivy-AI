"""
Vivy Hub - Sync Manager
Orchestrates event synchronization between the primary host and connected nodes.
Implements: event cursors, deduplication, conflict resolution (last-write-wins for
state events, ordered sequence for conversation turns), reconnect replay, and
conversation identity synchronization.
Fault class: Recoverable.
"""
import threading
import time
from hub.event_log import EventLog, SyncEvent
from typing import List, Dict, Optional


class SyncManager:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self._event_log = EventLog.get_instance()
        # Per-device cursor: last acknowledged sequence number
        self._device_cursors: Dict[str, int] = {}
        # Per-device last-acknowledged conversation_id
        self._device_conversations: Dict[str, str] = {}

    @classmethod
    def get_instance(cls) -> "SyncManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def register_device(self, device_id: str, starting_sequence: int = 0, conversation_id: str = "default"):
        """Register a device (or re-register on reconnect) with its starting cursor."""
        with self._lock:
            if device_id not in self._device_cursors:
                self._device_cursors[device_id] = starting_sequence
                self._device_conversations[device_id] = conversation_id
                print(f"[SyncManager] Registered device {device_id} at seq={starting_sequence}")
            else:
                print(f"[SyncManager] Re-registered device {device_id} (reconnect replay)")

    def sync_to_device(self, device_id: str) -> List[SyncEvent]:
        """
        Fetch all events a device needs to catch up since its last cursor.
        Filters out restricted events the device is not authorized to see.
        Called on reconnect to replay missed events.
        """
        with self._lock:
            cursor = self._device_cursors.get(device_id, 0)
            events = self._event_log.get_events_since(cursor)
            # Filter private events: exclude events from other devices with privacy_class=private
            accessible = []
            for ev in events:
                if ev.privacy_class == "restricted":
                    continue  # Never broadcast restricted events
                if ev.privacy_class == "private" and ev.device_id != device_id:
                    continue
                accessible.append(ev)
            if accessible:
                self._device_cursors[device_id] = accessible[-1].sequence
                print(f"[SyncManager] Replaying {len(accessible)} events to {device_id}")
            return accessible

    def acknowledge(self, device_id: str, sequence: int):
        """Called when a device confirms receipt of events up to `sequence`."""
        with self._lock:
            current = self._device_cursors.get(device_id, 0)
            if sequence > current:
                self._device_cursors[device_id] = sequence

    def receive_from_device(self, events: List[SyncEvent], device_id: str = "unknown"):
        """
        Merge a batch of events from a remote device.
        Deduplicates by event_id. Conflict resolution:
          - conversation.message events: ordered by sequence (no overwrite)
          - state events (emotion, affection, etc.): last-write-wins by timestamp
        """
        with self._lock:
            merged_count = 0
            for ev in events:
                # Deduplication guard
                if self._event_log.has_event(ev.event_id):
                    continue
                # For state update events, check last-write-wins
                if ev.type.startswith("state."):
                    existing_state = [
                        e for e in self._event_log._events
                        if e.type == ev.type and e.conversation_id == ev.conversation_id
                    ]
                    if existing_state:
                        latest = max(existing_state, key=lambda e: e.timestamp)
                        if ev.timestamp <= latest.timestamp:
                            continue  # Stale — discard
                # Append the event
                self._event_log._events.append(ev)
                self._event_log._event_id_set.add(ev.event_id)
                merged_count += 1

            if merged_count > 0:
                # Re-sort conversation events by sequence to maintain order
                self._event_log._events.sort(key=lambda x: (x.conversation_id, x.sequence))
                print(f"[SyncManager] Merged {merged_count} events from {device_id}")

    def get_conversation_sync_state(self, device_id: str) -> dict:
        """Return the current conversation identity state for a device's session."""
        with self._lock:
            return {
                "device_id": device_id,
                "cursor": self._device_cursors.get(device_id, 0),
                "conversation_id": self._device_conversations.get(device_id, "default"),
                "timestamp": time.time(),
            }

    def update_device_telemetry(self, device_id: str, telemetry: dict):
        """
        Update a device's runtime resource state in the DeviceRegistry.
        Called by heartbeat messages from nodes.
        """
        try:
            from hub.device_registry import DeviceRegistry
            registry = DeviceRegistry.get_instance()
            device = registry.get_device(device_id)
            if device:
                device.current_cpu_pct = float(telemetry.get("cpu_pct", device.current_cpu_pct))
                device.current_gpu_pct = float(telemetry.get("gpu_pct", device.current_gpu_pct))
                device.current_ram_pct = float(telemetry.get("ram_pct", device.current_ram_pct))
                device.battery_pct = float(telemetry.get("battery_pct", device.battery_pct))
                device.thermal_state = telemetry.get("thermal", device.thermal_state)
                device.last_seen = time.time()
        except Exception as e:
            print(f"[SyncManager] Telemetry update error for {device_id}: {e}")

    def unregister_device(self, device_id: str):
        """Remove device cursor on disconnect."""
        with self._lock:
            self._device_cursors.pop(device_id, None)
            self._device_conversations.pop(device_id, None)
