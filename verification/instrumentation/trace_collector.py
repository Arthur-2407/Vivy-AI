import threading
import time
import uuid
import sys

class TraceSpan:
    def __init__(self, trace_id, name, parent_id=None):
        self.trace_id = trace_id
        self.span_id = str(uuid.uuid4())
        self.parent_id = parent_id
        self.name = name
        self.thread_id = threading.get_ident()
        self.timestamp_start = time.time()
        self.timestamp_end = None
        self.payload = {}
        self.hardware = None
        
    def end(self):
        self.timestamp_end = time.time()
        
    def to_dict(self):
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "thread_id": self.thread_id,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "payload": self.payload,
            "hardware": self.hardware
        }

class TraceCollector:
    def __init__(self):
        self.spans = []
        self._lock = threading.Lock()
        
    def add_span(self, span: TraceSpan):
        with self._lock:
            self.spans.append(span)
            
    def get_spans(self):
        with self._lock:
            return [s.to_dict() for s in self.spans]
            
    def clear(self):
        with self._lock:
            self.spans.clear()

_collector = TraceCollector()
def get_collector():
    return _collector
