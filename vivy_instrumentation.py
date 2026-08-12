import sys
import os
import time
import json
import uuid
import threading
from unittest.mock import patch
import builtins

# We use an instrumentation proxy to wrap target functions without editing the actual codebase.
class TraceContext:
    def __init__(self, conversation_id: str, turn_id: str):
        self.conversation_id = conversation_id
        self.turn_id = turn_id
        self.events = []
        self._lock = threading.Lock()
        
    def log_event(self, source_level: str, dest_level: str, payload_type: str, details: dict):
        event_id = f"E{len(self.events) + 100}"
        parent_id = f"E{len(self.events) + 99}" if self.events else "ROOT"
        
        evt = {
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "event_id": event_id,
            "parent_event_id": parent_id,
            "source_level": source_level,
            "destination_level": dest_level,
            "timestamp": time.time(),
            "payload_type": payload_type,
            "hardware": details.get("hardware", "CPU"),
            "provider": details.get("provider", "Native"),
            "function": details.get("function", "")
        }
        with self._lock:
            self.events.append(evt)
        return event_id

class VivyInstrumentation:
    def __init__(self):
        self.active_context = None
        self.patches = []
        
    def start_trace(self, turn_id="TURN-001"):
        self.active_context = TraceContext(str(uuid.uuid4()), turn_id)
        self._apply_patches()
        
    def stop_trace(self) -> list:
        self._remove_patches()
        if self.active_context:
            return self.active_context.events
        return []

    def _apply_patches(self):
        # We hook into critical pipeline junctions
        try:
            import conversation
            self._wrap(conversation, "health_priority_engine", "L2", "L5", "health_symptoms")
            self._wrap(conversation, "conversation_director", "L5", "L5", "cognitive_plan")
            self._wrap(conversation, "update_emotion_vector", "L5", "L4", "emotion_update")
            self._wrap(conversation, "get_perception_context", "L2", "L5", "perception_event")
        except ImportError:
            pass

        # Intercept LLM execution to grab hardware info
        try:
            import llama_cpp
            original_init = llama_cpp.Llama.__init__
            def patched_init(self_obj, *args, **kwargs):
                hw = "CUDA AVAILABLE" if kwargs.get("n_gpu_layers", 0) > 0 else "CPU"
                if self.active_context:
                    self.active_context.log_event("L5", "L5", "model_load", {
                        "hardware": hw, 
                        "provider": "llama_cpp",
                        "function": "Llama.__init__"
                    })
                original_init(self_obj, *args, **kwargs)
            
            p = patch.object(llama_cpp.Llama, '__init__', patched_init)
            p.start()
            self.patches.append(p)
        except ImportError:
            pass
            
    def _remove_patches(self):
        for p in self.patches:
            p.stop()
        self.patches.clear()
        
    def _wrap(self, module, func_name, src, dst, payload_type):
        if not hasattr(module, func_name):
            return
            
        original = getattr(module, func_name)
        def wrapper(*args, **kwargs):
            if self.active_context:
                self.active_context.log_event(src, dst, payload_type, {
                    "function": func_name,
                    "hardware": "CPU", # default python exec
                    "provider": "Native"
                })
            return original(*args, **kwargs)
            
        p = patch.object(module, func_name, wrapper)
        p.start()
        self.patches.append(p)

_global_instrumentation = VivyInstrumentation()

def get_instrumentation():
    return _global_instrumentation
