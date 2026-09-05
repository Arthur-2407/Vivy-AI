"""
Vivy Hub - Event Log
Defines standard ecosystem events for cross-device synchronization.
Events are ordered by sequence, deduplicated by event_id, and prunable.
Fault class: Recoverable.
"""
import uuid
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

@dataclass
class SyncEvent:
    event_id: str
    session_id: str
    conversation_id: str          # for cross-device conversation continuity
    device_id: str
    sequence: int
    timestamp: float
    type: str                     # e.g., "conversation.message", "perception.object"
    payload: Dict[str, Any] = field(default_factory=dict)
    causal_parent: Optional[str] = None   # event_id of the event that caused this one
    privacy_class: str = "standard"       # public | standard | private | restricted
    schema_version: str = "1.0"


class EventLog:
    _instance = None
    MAX_EVENTS = 10000  # prune oldest events when log exceeds this size

    def __init__(self):
        self._events: List[SyncEvent] = []
        self._sequence_counter = 0
        self._event_id_set: set = set()

    @classmethod
    def get_instance(cls) -> "EventLog":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def append_event(
        self,
        session_id: str,
        device_id: str,
        event_type: str,
        payload: Dict[str, Any],
        conversation_id: str = "default",
        causal_parent: Optional[str] = None,
        privacy_class: str = "standard",
    ) -> SyncEvent:
        self._sequence_counter += 1
        event = SyncEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            conversation_id=conversation_id,
            device_id=device_id,
            sequence=self._sequence_counter,
            timestamp=time.time(),
            type=event_type,
            payload=payload,
            causal_parent=causal_parent,
            privacy_class=privacy_class,
        )
        self._events.append(event)
        self._event_id_set.add(event.event_id)
        # Prune to keep memory bounded
        if len(self._events) > self.MAX_EVENTS:
            removed = self._events[:1000]
            self._events = self._events[1000:]
            for e in removed:
                self._event_id_set.discard(e.event_id)
        print(f"[EventLog] Appended: {event.type} seq={event.sequence} conv={conversation_id}")
        return event

    def has_event(self, event_id: str) -> bool:
        return event_id in self._event_id_set

    def get_events_since(self, sequence: int) -> List[SyncEvent]:
        return [e for e in self._events if e.sequence > sequence]

    def get_conversation_events(self, conversation_id: str) -> List[SyncEvent]:
        return [e for e in self._events if e.conversation_id == conversation_id]
