"""
Vivy AI — Developer Runtime Diagnostic Manager
================================================
Provides a zero-overhead, toggleable Developer Diagnostic Mode for full-stack
observability across Perception, WebSocket, Animation, Prompt Construction,
LLM Reasoning, and Fallback Execution.

Key Principles:
1. Disabled by default (`enabled: False`). Zero performance overhead when disabled.
2. Thread-safe ring buffering for live diagnostic telemetry.
3. Automated defect flagging when fallbacks trigger despite valid perception data.
4. Non-intrusive: never alters production logic or model output.
"""

import os
import sys
import time
import json
import threading
from collections import deque

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(BASE_DIR, "shared")
DIAGNOSTIC_STATE_JSON = os.path.join(SHARED_DIR, "developer_diagnostic_state.json")


class DeveloperDiagnosticManager:
    """Central singleton managing Developer Diagnostic Mode state and telemetry buffers."""

    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DeveloperDiagnosticManager, cls).__new__(cls)
                cls._instance._init_manager()
            return cls._instance

    def _init_manager(self):
        self.enabled = False
        self.debug_level = "INFO"
        self.start_time = time.time()
        self.last_update = time.time()

        # Telemetry ring buffers (max 500 items each)
        self._frame_telemetry = deque(maxlen=500)
        self._websocket_packets = deque(maxlen=500)
        self._animation_events = deque(maxlen=500)
        self._prompt_traces = deque(maxlen=200)
        self._fallback_events = deque(maxlen=200)
        self._defects_logged = deque(maxlen=200)

        # Counter metrics
        self.stats = {
            "total_frames_processed": 0,
            "total_ws_packets": 0,
            "total_prompts_inspected": 0,
            "total_fallbacks_detected": 0,
            "total_defects_flagged": 0,
            "active_defects_count": 0,
        }

        # Load persisted toggle state if present
        self._load_persisted_state()

    def _load_persisted_state(self):
        try:
            if os.path.exists(DIAGNOSTIC_STATE_JSON):
                with open(DIAGNOSTIC_STATE_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.enabled = data.get("enabled", False)
                    self.debug_level = data.get("debug_level", "INFO")
        except Exception as e:
            print(f"[DeveloperDiagnostics] State load warning: {e}")

    def _persist_state(self):
        try:
            os.makedirs(SHARED_DIR, exist_ok=True)
            payload = {
                "enabled": self.enabled,
                "debug_level": self.debug_level,
                "last_update": time.time(),
                "stats": self.stats,
            }
            tmp = DIAGNOSTIC_STATE_JSON + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, DIAGNOSTIC_STATE_JSON)
        except Exception as e:
            print(f"[DeveloperDiagnostics] State persist error: {e}")

    def is_enabled(self) -> bool:
        return self.enabled

    def toggle(self, enable: bool = None) -> bool:
        """Toggle Developer Diagnostic Mode on or off."""
        with self._lock:
            if enable is None:
                self.enabled = not self.enabled
            else:
                self.enabled = bool(enable)
            self.last_update = time.time()
            self._persist_state()
            status_str = "ENABLED" if self.enabled else "DISABLED"
            print(f"[DeveloperDiagnostics] Developer Diagnostic Mode is now {status_str}.")
            return self.enabled

    def set_debug_level(self, level: str):
        with self._lock:
            self.debug_level = str(level).upper()
            self._persist_state()

    # ───────────────────────────────────────────────────────────────────
    # Live Perception Pipeline Instrumentation (Phase 3)
    # ───────────────────────────────────────────────────────────────────
    def record_frame(
        self,
        frame_num: int,
        camera_source: str,
        resolution: tuple,
        latency_ms: float,
        fps: float,
        dropped_frames: int,
        detections: dict,
        capture_status: str = "OK",
        confidence_scores: dict = None,
        context_injected: str = None,
        final_prompt: str = None,
        raw_llm_response: str = None,
        final_displayed_response: str = None,
        fallback_used: bool = False,
        fallback_reason: str = None,
    ):
        """Record per-frame perception pipeline telemetry with full Phase 4 evidence details."""
        if not self.enabled:
            return

        now = time.time()
        entry = {
            "timestamp": now,
            "frame_num": frame_num,
            "camera_source": camera_source,
            "resolution": f"{resolution[0]}x{resolution[1]}" if isinstance(resolution, (tuple, list)) and len(resolution) == 2 else str(resolution),
            "latency_ms": round(latency_ms, 2),
            "fps": round(fps, 1),
            "dropped_frames": dropped_frames,
            "capture_status": capture_status,
            "face_detection": detections.get("face", {}),
            "hand_detection": detections.get("hand", {}),
            "object_detection": detections.get("object", {}),
            "body_pose": detections.get("pose", {}),
            "gaze_estimation": detections.get("gaze", {}),
            "ocr_text": detections.get("ocr", {}),
            "scene_description": detections.get("scene", ""),
            "confidence_scores": confidence_scores or detections.get("confidence_scores", {}),
            "context_injected": context_injected or "",
            "final_prompt": final_prompt or "",
            "raw_llm_response": raw_llm_response or "",
            "final_displayed_response": final_displayed_response or "",
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason or "",
        }

        with self._lock:
            self._frame_telemetry.appendleft(entry)
            self.stats["total_frames_processed"] += 1

    # ───────────────────────────────────────────────────────────────────
    # Live WebSocket Monitor Instrumentation (Phase 4)
    # ───────────────────────────────────────────────────────────────────
    def record_ws_packet(
        self,
        direction: str,  # "OUTGOING" or "INCOMING"
        message_type: str,
        payload_size: int,
        ser_time_ms: float = 0.0,
        deser_time_ms: float = 0.0,
        latency_ms: float = 0.0,
        status: str = "OK",
        error: str = None,
        data_preview: dict = None,
    ):
        """Record packet-level WebSocket telemetry."""
        if not self.enabled:
            return

        now = time.time()
        entry = {
            "timestamp": now,
            "time_str": time.strftime("%H:%M:%S", time.localtime(now)),
            "direction": direction.upper(),
            "message_type": message_type,
            "payload_size_bytes": payload_size,
            "serialization_ms": round(ser_time_ms, 3),
            "deserialization_ms": round(deser_time_ms, 3),
            "latency_ms": round(latency_ms, 2),
            "status": status,
            "error": error,
            "data_preview": data_preview or {},
        }

        with self._lock:
            self._websocket_packets.appendleft(entry)
            self.stats["total_ws_packets"] += 1

    # ───────────────────────────────────────────────────────────────────
    # Live Animation Monitor Instrumentation (Phase 5)
    # ───────────────────────────────────────────────────────────────────
    def record_animation(
        self,
        current_anim: str,
        prev_anim: str,
        next_anim: str,
        animator_state: str,
        animator_layer: int,
        blend_weight: float,
        transition_progress: float,
        queue: list,
        interruptions: int,
        procedural_motion: dict = None,
        emotion_modifiers: dict = None,
    ):
        """Record real-time animation state telemetry."""
        if not self.enabled:
            return

        now = time.time()
        entry = {
            "timestamp": now,
            "current_animation": current_anim,
            "previous_animation": prev_anim,
            "next_animation": next_anim,
            "animator_state": animator_state,
            "animator_layer": animator_layer,
            "blend_weight": round(blend_weight, 2),
            "transition_progress": round(transition_progress, 2),
            "queue": queue or [],
            "interruptions": interruptions,
            "procedural_motion": procedural_motion or {},
            "emotion_modifiers": emotion_modifiers or {},
        }

        with self._lock:
            self._animation_events.appendleft(entry)

    # ───────────────────────────────────────────────────────────────────
    # Prompt Inspection Instrumentation (Phase 6)
    # ───────────────────────────────────────────────────────────────────
    def record_prompt_trace(
        self,
        user_query: str,
        camera_observations: dict,
        vision_model_output: dict,
        context_builder_output: str,
        final_prompt_sent: str,
        raw_llm_response: str,
        filtered_response: str,
        final_spoken_response: str,
        fallback_triggered: bool = False,
        fallback_reason: str = None,
    ):
        """Record end-to-end prompt assembly & LLM generation trace for perception queries."""
        if not self.enabled:
            return

        now = time.time()
        entry = {
            "timestamp": now,
            "time_str": time.strftime("%H:%M:%S", time.localtime(now)),
            "user_query": user_query,
            "camera_observations": camera_observations or {},
            "vision_model_output": vision_model_output or {},
            "context_builder_output": context_builder_output or "",
            "final_prompt_length": len(final_prompt_sent or ""),
            "final_prompt_sent": final_prompt_sent or "",
            "raw_llm_response": raw_llm_response or "",
            "filtered_response": filtered_response or "",
            "final_spoken_response": final_spoken_response or "",
            "fallback_triggered": fallback_triggered,
            "fallback_reason": fallback_reason,
        }

        with self._lock:
            self._prompt_traces.appendleft(entry)
            self.stats["total_prompts_inspected"] += 1

    # ───────────────────────────────────────────────────────────────────
    # Fallback Detector Instrumentation (Phase 7)
    # ───────────────────────────────────────────────────────────────────
    def record_fallback(
        self,
        trigger_phrase: str,
        file_path: str,
        class_name: str,
        method_name: str,
        line_num: int,
        trigger_condition: str,
        runtime_evidence: dict,
        why_executed: str,
        vision_was_valid: bool,
    ):
        """
        Record a fallback trigger event and automatically flag a defect if
        the fallback executed while valid vision/perception data existed.
        """
        if not self.enabled:
            return

        now = time.time()
        is_defect = (vision_was_valid is True)

        entry = {
            "timestamp": now,
            "time_str": time.strftime("%H:%M:%S", time.localtime(now)),
            "trigger_phrase": trigger_phrase,
            "location": f"{os.path.basename(file_path)}:{class_name}.{method_name}():L{line_num}",
            "file": file_path,
            "class": class_name,
            "method": method_name,
            "line": line_num,
            "trigger_condition": trigger_condition,
            "runtime_evidence": runtime_evidence or {},
            "why_executed": why_executed,
            "vision_was_valid": vision_was_valid,
            "is_defect": is_defect,
        }

        with self._lock:
            self._fallback_events.appendleft(entry)
            self.stats["total_fallbacks_detected"] += 1

            if is_defect:
                defect_entry = dict(entry)
                defect_entry["defect_id"] = f"DEFECT-{int(now * 1000)}"
                defect_entry["root_cause_summary"] = (
                    f"Fallback '{trigger_phrase}' executed at {entry['location']} "
                    f"despite valid perception data being present."
                )
                self._defects_logged.appendleft(defect_entry)
                self.stats["total_defects_flagged"] += 1
                self.stats["active_defects_count"] = len(self._defects_logged)
                print(f"[DeveloperDiagnostics][DEFECT DETECTED] {defect_entry['root_cause_summary']}")

    # ───────────────────────────────────────────────────────────────────
    # Snapshot & Retrieval API (Phase 12 Dashboard & Telemetry)
    # ───────────────────────────────────────────────────────────────────
    def get_snapshot(self) -> dict:
        """Return full diagnostic snapshot for UI dashboard."""
        with self._lock:
            latest_frame = self._frame_telemetry[0] if self._frame_telemetry else {}
            latest_anim = self._animation_events[0] if self._animation_events else {}
            latest_prompt = self._prompt_traces[0] if self._prompt_traces else {}

            return {
                "enabled": self.enabled,
                "debug_level": self.debug_level,
                "uptime_seconds": int(time.time() - self.start_time),
                "stats": dict(self.stats),
                "latest_frame": latest_frame,
                "latest_animation": latest_anim,
                "latest_prompt": latest_prompt,
                "recent_packets": list(self._websocket_packets)[:20],
                "recent_fallbacks": list(self._fallback_events)[:20],
                "active_defects": list(self._defects_logged)[:20],
            }

    def get_prompt_traces(self, limit: int = 20) -> list:
        with self._lock:
            return list(self._prompt_traces)[:limit]

    def get_ws_packets(self, limit: int = 50) -> list:
        with self._lock:
            return list(self._websocket_packets)[:limit]

    def get_fallbacks(self, limit: int = 50) -> list:
        with self._lock:
            return list(self._fallback_events)[:limit]

    def get_defects(self, limit: int = 50) -> list:
        with self._lock:
            return list(self._defects_logged)[:limit]


def get_developer_diagnostic_manager() -> DeveloperDiagnosticManager:
    return DeveloperDiagnosticManager()
