"""
agi/bus/event_bus.py
==============================
Unified Cognitive Event Bus for Vivy AI.
Implements a strict publish/subscribe pattern for all 11 architectural levels.
"""

import threading
import time
import json
from typing import Callable, Dict, List, Any

class EventBus:
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}
        self.history = []
        self._lock = threading.Lock()
        
    def subscribe(self, topic: str, callback: Callable):
        with self._lock:
            if topic not in self.subscribers:
                self.subscribers[topic] = []
            if callback not in self.subscribers[topic]:
                self.subscribers[topic].append(callback)
                
    def publish(self, topic: str, payload: Any):
        event = {
            "timestamp": time.time(),
            "topic": topic,
            "payload": payload
        }
        with self._lock:
            self.history.append(event)
            # Keep history bounded
            if len(self.history) > 1000:
                self.history.pop(0)
            subs = list(self.subscribers.get(topic, []))
            
        for callback in subs:
            try:
                callback(event)
            except Exception as e:
                print(f"[EventBus] Error in subscriber for {topic}: {e}")

_global_bus = EventBus()

def get_event_bus() -> EventBus:
    return _global_bus
