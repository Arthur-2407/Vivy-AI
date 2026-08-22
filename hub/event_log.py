"""
Vivy Hub - Event Log
Defines standard ecosystem events for cross-device synchronization (CRDT/Event-Sourcing style).
"""
import uuid
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List

@dataclass
class SyncEvent:
    event_id: str
    session_id: str
    device_id: str
    sequence: int
    timestamp: float
    type: str  # e.g., "conversation.message", "perception.object", "avatar.emotion"
    payload: Dict[str, Any] = field(default_factory=dict)
    
class EventLog:
    _instance = None

    def __init__(self):
        self._events: List[SyncEvent] = []
        self._sequence_counter = 0
        
    @classmethod
    def get_instance(cls) -> "EventLog":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def append_event(self, session_id: str, device_id: str, event_type: str, payload: Dict[str, Any]) -> SyncEvent:
        self._sequence_counter += 1
        event = SyncEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            device_id=device_id,
            sequence=self._sequence_counter,
            timestamp=time.time(),
            type=event_type,
            payload=payload
        )
        self._events.append(event)
        print(f"[EventLog] Appended event: {event.type} (Seq: {event.sequence})")
        return event
        
    def get_events_since(self, sequence: int) -> List[SyncEvent]:
        return [e for e in self._events if e.sequence > sequence]
