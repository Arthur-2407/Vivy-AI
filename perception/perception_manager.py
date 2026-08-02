"""
perception/perception_manager.py
==================================
Vivy AI — Perception Manager
The single source of truth for all sensor / perceptual state.

Architecture note
-----------------
web_server.py runs as a subprocess of run_vivy.py.  They cannot share
in-memory objects.  The PerceptionManager therefore uses the same
file-based IPC pattern that is already established in the codebase
(e.g. screen_context.txt, status.txt):

  web_server.py  (WRITE side)
      │
      │  shared/perception_state.json
      │
  run_vivy.py / conversation.py  (READ side)

The WRITE side (PerceptionManagerWriter) is imported by web_server.py.
The READ side (PerceptionManagerReader) is imported by run_vivy.py /
conversation.py.

Both sides expose a process-level singleton via get_writer() and
get_reader() respectively.

Diagnostic API
--------------
get_writer().get_diagnostic_report()  →  dict  (runtime state)
get_reader().load_state()             →  dict  (last persisted state)
get_reader().is_screen_sharing_active() → bool
get_reader().build_grounding_context() → str   (LLM-ready text)
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from collections import deque
from typing import Any, Dict, Optional
import ctypes
import ctypes.wintypes

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Shared constants
# ─────────────────────────────────────────────────────────────────────────────

# File written by the write side, read by the read side
_STATE_FILENAME = "perception_state.json"

# Maximum age (seconds) before a frame arrival is considered stale
FRAME_STALE_SECONDS = 45.0

# Maximum age (seconds) before audio arrival is considered stale
# Set to 30s (was 10s) — browser audio chunks arrive every 2-3s, and even
# brief gaps (e.g. during silence classification) would incorrectly flip
# audio_active to False and wipe the audio description from the LLM prompt.
AUDIO_STALE_SECONDS = 30.0

# Minimum frames received before claiming screen sharing is "active"
MIN_FRAMES_FOR_ACTIVE = 2

# Confidence thresholds for natural language
CONF_HIGH   = 0.85
CONF_MEDIUM = 0.55
CONF_LOW    = 0.30


def _project_root() -> str:
    """Return the project root directory (parent of this file's directory)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _shared_dir() -> str:
    """Return the shared/ directory path."""
    try:
        from perception.config_loader import get as _cfg_get
        rel = _cfg_get("paths", "shared_dir", default="shared")
        return os.path.join(_project_root(), rel)
    except Exception:
        return os.path.join(_project_root(), "shared")


def _state_path() -> str:
    return os.path.join(_shared_dir(), _STATE_FILENAME)


# ─────────────────────────────────────────────────────────────────────────────
# WRITE SIDE  (lives in web_server.py process)
# ─────────────────────────────────────────────────────────────────────────────

class PerceptionManagerWriter:
    """
    Tracks real-time sensor state inside web_server.py and periodically
    persists it to shared/perception_state.json for run_vivy.py to read.

    Thread-safe.  All public methods are non-blocking and non-fatal.
    """

    def __init__(self, start_threads: bool = True):
        self._lock = threading.Lock()

        # ── Frame tracking ──
        self._screen_sharing_active: bool  = False
        self._screen_sharing_explicit: bool = False  # True when browser sent explicit start/stop
        self._last_frame_time: float       = 0.0
        self._frames_received: int         = 0
        self._frames_dropped: int          = 0
        self._frame_timestamps: deque      = deque(maxlen=30)  # rolling window
        self._current_app_type: str        = "unknown"
        self._ocr_available: bool          = False
        self._last_ocr_chars: int          = 0
        self._vision_model_used: bool      = False
        self._last_ocr_text: str           = ""  # actual OCR content from latest frame
        self._highlighted_region_text: str = ""  # OCR of cursor-selected / highlighted region
        self._highlighted_region_context: str = ""  # Surrounding context of highlighted region

        # ── Audio tracking ──
        self._audio_active: bool           = False
        self._last_audio_time: float       = 0.0
        self._last_audio_rms: float        = 0.0
        self._last_audio_event_type: str   = "silence"
        self._audio_event_description: str = ""  # human-readable audio description
        self._audio_chunks_received: int   = 0
        self._screen_audio_transcript: str = ""

        # ── Session ──
        self._session_start: float         = time.time()
        self._state_path: str              = _state_path()

        # ── Upgraded diagnostic tracking ──
        self._video_resolution: str        = "0x0"
        self._video_latency: float         = 0.0
        self._audio_sample_rate: int       = 16000
        self._audio_channels: int          = 1
        self._vision_running: bool         = False
        self._vision_inference_time: float = 0.0
        self._vision_latest_caption: str   = ""
        self._audio_model_running: bool    = False
        self._audio_detected_speech: bool  = False
        self._audio_detected_music: bool   = False
        self._audio_detected_sound_events: list = []
        self._audio_model_confidence: float = 0.0
        self._ocr_confidence: float        = 1.0
        self._audio_transcript_confidence: float = 1.0
        self._audio_language: str = "unknown"
        self._audio_speaker_id: str = "speaker_0"
        self._audio_music_title: str = ""
        self._audio_playback_state: str = "stopped"
        self._audio_sound_effects: list = []

        # ── Cursor and active window tracking ──
        self._cursor_x: int = 0
        self._cursor_y: int = 0
        self._cursor_state: str = "unknown"
        self._active_window_title: str = "unknown"
        self._active_window_class: str = "unknown"
        self._active_window_rect: list[int] = [0, 0, 0, 0] # [left, top, right, bottom]
        self._mouse_button_state: str = "none"
        self._relative_cursor_x: float = -1.0
        self._relative_cursor_y: float = -1.0
        self._active_process_name: str = "unknown"

        # ── Temporal memory and layout tracking ──
        self._state_changes: deque = deque(maxlen=50)
        self._last_recorded_state: dict = {}
        self._scene_layout: dict = {}

        # ── Face / Gaze Perception Tracking ──
        self._camera_active: bool = False
        self._camera_paused: bool = False
        self._presence_state: str = "User Missing"
        self._face_count: int = 0
        self._object_count: int = 0
        self._detected_objects: list = []
        self._last_object_update_time: float = 0.0
        self._gaze_direction: str = "Unknown"
        self._eye_contact_score: float = 0.0
        self._eye_contact_strength: str = "None"
        self._attention_score: float = 0.0
        self._engagement_score: float = 0.0
        self._presence_score: float = 0.0
        self._head_orientation: str = "Head Facing Vivy"
        self._hardware_backend: str = "CPU"
        self._hardware_mode: str = "Avatar OFF Mode"
        self._face_perception_data: dict = {}
        self._hand_state: dict = {}
        self._held_objects: list = []
        self._last_hand_update_time: float = 0.0
        self._camera_vlm_caption: str = ""

        # ── Cursor/Window polling thread ──
        self._poll_running: bool = False
        self._poll_thread: Optional[threading.Thread] = None
        if start_threads:
            self._start_poll_thread()

        # ── Auto-flush thread ──
        self._flush_thread: Optional[threading.Thread] = None
        self._flush_running: bool          = False
        if start_threads:
            self._start_flush_thread()

    def record_hand_perception_state(self, hand_state: dict, held_objects: list = None):
        """Record real-time hand tracking and hand-held object state."""
        now = time.time()
        with self._lock:
            self._last_hand_update_time = now
            self._hand_state = hand_state or {}
            if held_objects is not None:
                self._held_objects = [o.to_dict() if hasattr(o, "to_dict") else o for o in held_objects]
        self._flush_to_disk()

    def record_camera_vlm_caption(self, caption: str):
        """Record visual scene caption of camera feed."""
        if caption:
            with self._lock:
                self._camera_vlm_caption = caption[:1000]
            self._flush_to_disk()

    # ── Frame arrival recording ──────────────────────────────────────────────

    def record_frame_arrival(
        self,
        app_type: str = "unknown",
        ocr_chars: int = 0,
        has_ocr: bool = False,
        has_vision: bool = False,
        frame_dropped: bool = False,
        resolution: str = "0x0",
        latency_ms: float = 0.0,
        ocr_text: str = "",
        ocr_confidence: float = 1.0,
        scene_layout: dict = None,
    ):
        """Called by web_server.py every time a frame is received/dropped."""
        now = time.time()
        with self._lock:
            if frame_dropped:
                self._frames_dropped += 1
            else:
                # Race condition guard: If screen share was explicitly stopped,
                # discard late in-flight frames to prevent resurrecting ACTIVE state.
                if self._screen_sharing_explicit and not self._screen_sharing_active:
                    logger.debug("[PerceptionManager] Discarding late in-flight frame after explicit stop signal.")
                    return
                self._frames_received += 1
                self._last_frame_time = now
                self._frame_timestamps.append(now)
                self._screen_sharing_active = True
                self._video_resolution = resolution
                self._video_latency = latency_ms
                self._ocr_confidence = ocr_confidence

            if app_type and app_type != "unknown":
                self._current_app_type = app_type
            if has_ocr:
                self._ocr_available = True
                self._last_ocr_chars = max(self._last_ocr_chars, ocr_chars)
            if has_vision:
                self._vision_model_used = True
            # Always update OCR text when provided (allowing empty string to clear stale text)
            if ocr_text is not None:
                self._last_ocr_text = ocr_text[:10000]
                self._last_ocr_chars = len(ocr_text)
                self._ocr_available = bool(ocr_text.strip())
                logger.debug(f"[PerceptionManager] OCR text recorded: {len(ocr_text)} chars")
            if scene_layout is not None:
                self._scene_layout = scene_layout
        self._flush_to_disk()

    def record_highlighted_region(self, text: str, context: str = ""):
        """Store OCR text extracted from the cursor-selected / highlighted screen region."""
        with self._lock:
            self._highlighted_region_text = text[:500] if text else ""
            self._highlighted_region_context = context[:1000] if context else ""
            if text:
                logger.debug(f"[PerceptionManager] Highlighted region recorded: {len(text)} chars, context: {len(context)} chars")

    def record_audio_event_description(self, description: str):
        """Store the human-readable audio classification description for LLM injection."""
        if description:
            with self._lock:
                self._audio_event_description = description

    def record_screen_audio_transcript(self, transcript: str, confidence: float = 1.0):
        """Record the latest transcribed speech/lyrics from screen audio."""
        with self._lock:
            self._screen_audio_transcript = transcript
            self._audio_transcript_confidence = confidence

    def record_audio_chunk(self, rms: float, event_type: str = "ambient", sample_rate: int = 16000, channels: int = 1):
        """Called by web_server.py every time an audio chunk is received."""
        now = time.time()
        with self._lock:
            self._audio_active = True
            self._last_audio_time = now
            self._last_audio_rms = rms
            self._last_audio_event_type = event_type
            self._audio_chunks_received += 1
            self._audio_sample_rate = sample_rate
            self._audio_channels = channels

    def record_vision_inference(self, running: bool, inference_time_ms: float, latest_caption: str, confidence: float):
        with self._lock:
            self._vision_running = running
            self._vision_inference_time = inference_time_ms
            self._vision_latest_caption = latest_caption
            if running:
                self._vision_model_used = True

    def record_audio_model_inference(self, running: bool, detected_speech: bool, detected_music: bool, detected_sound_events: list, confidence: float):
        with self._lock:
            self._audio_model_running = running
            self._audio_detected_speech = detected_speech
            self._audio_detected_music = detected_music
            self._audio_detected_sound_events = list(detected_sound_events)
            self._audio_model_confidence = confidence

    def record_audio_metadata(self, language: str = None, speaker_id: str = None, music_title: str = None, playback_state: str = None, sound_effects: list = None):
        """Update extended audio metadata (language, speaker, music title, playback state, sound effects)."""
        with self._lock:
            if language is not None:
                self._audio_language = language
            if speaker_id is not None:
                self._audio_speaker_id = speaker_id
            if music_title is not None:
                self._audio_music_title = music_title
            if playback_state is not None:
                self._audio_playback_state = playback_state
            if sound_effects is not None:
                self._audio_sound_effects = list(sound_effects)

    def record_camera_state(self, active: bool = True, paused: bool = False):
        """Record explicit camera state changes (start, stop, pause, resume)."""
        now = time.time()
        with self._lock:
            self._camera_active = active
            self._camera_paused = paused
            self._last_camera_state_time = now
            if not active:
                self._presence_state = "Camera OFF"
                self._face_count = 0
                self._gaze_direction = "Unknown"
                self._eye_contact_score = 0.0
                self._eye_contact_strength = "None"
                self._attention_score = 0.0
                self._engagement_score = 0.0
                self._presence_score = 0.0
                self._face_perception_data = {}
            else:
                if self._presence_state == "Camera OFF":
                    self._presence_state = "User Missing"
        self._flush_to_disk()
        logger.info(f"[PerceptionManager] Camera state recorded: active={active}, paused={paused}")

    def record_object_perception_state(self, objects: list):
        """Record real-time detected objects state in frame."""
        now = time.time()
        with self._lock:
            self._last_object_update_time = now
            self._object_count = len(objects)
            self._detected_objects = [o.to_dict() if hasattr(o, "to_dict") else o for o in objects]
        self._flush_to_disk()

    def record_face_perception_state(self, state_dict: dict):
        """Record real-time face, gaze, presence, attention, and hardware scheduler state."""
        now = time.time()
        with self._lock:
            self._last_face_update_time = now
            if "camera_active" in state_dict:
                self._camera_active = bool(state_dict["camera_active"])
            elif state_dict.get("face_count", 0) > 0:
                self._camera_active = True

            if not self._camera_active:
                self._presence_state = "Camera OFF"
                self._face_count = 0
            else:
                self._presence_state = state_dict.get("presence_state", "User Present")
                self._face_count = state_dict.get("face_count", 0)
            gaze = state_dict.get("gaze", {})
            self._gaze_direction = gaze.get("gaze_direction", "Unknown")
            self._eye_contact_score = gaze.get("eye_contact_score", 0.0)
            self._eye_contact_strength = gaze.get("eye_contact_strength", "None")

            att = state_dict.get("attention", {})
            self._attention_score = att.get("attention_score", 0.0)
            self._engagement_score = att.get("engagement_score", 0.0)
            self._presence_score = att.get("presence_score", 0.0)

            primary_face = state_dict.get("primary_face") or {}
            hp = primary_face.get("head_pose") or {}
            self._head_orientation = hp.get("orientation_label", "Head Facing Vivy")

            hw = state_dict.get("hardware") or {}
            self._hardware_backend = hw.get("backend", "CPU")
            self._hardware_mode = hw.get("mode", "Avatar OFF Mode")
            self._face_perception_data = state_dict
        self._flush_to_disk()

    def recover_perception(self) -> dict:
        """Attempt self-recovery of perception state buffers without restarting Vivy."""
        with self._lock:
            self._face_count = 0
            self._gaze_direction = "Unknown"
            self._eye_contact_score = 0.0
            self._attention_score = 0.0
            self._presence_state = "User Missing"
            self._face_perception_data = {}
        self._flush_to_disk()
        logger.info("[PerceptionManager] Executed perception self-recovery reset.")
        return {"status": "recovered", "timestamp": time.time()}

    def record_frame_queue_drop(self):
        """Called when the frame queue is full and a frame is discarded."""
        with self._lock:
            self._frames_dropped += 1

    def mark_screen_share_started(self):
        """
        Called immediately when the browser successfully acquires a display
        media stream (getDisplayMedia resolves). This is the AUTHORITATIVE
        signal that screen sharing is active — do not wait for frame analysis.
        Sets _screen_sharing_explicit=True so the reader knows this came from
        a direct browser event, not heuristic frame-counting.
        """
        now = time.time()
        with self._lock:
            self._screen_sharing_active   = True
            self._screen_sharing_explicit = True
            # Reset per-session counters and stale perceptual text for a clean new share session
            self._frames_received   = 0
            self._frames_dropped    = 0
            self._last_frame_time   = 0.0
            self._frame_timestamps.clear()
            self._ocr_available     = False
            self._last_ocr_chars    = 0
            self._vision_model_used = False
            self._current_app_type  = "unknown"
            self._last_ocr_text     = ""
            self._highlighted_region_text = ""
            self._highlighted_region_context = ""
            self._vision_latest_caption = ""
            self._screen_audio_transcript = ""
            self._audio_music_title  = ""
            self._audio_event_description = ""
            self._scene_layout      = {}
        self._flush_to_disk()
        logger.info("[PerceptionManager] Screen share STARTED (authoritative browser signal).")

    def mark_screen_share_stopped(self):
        """
        Called immediately when the browser stops the display media stream.
        This is the AUTHORITATIVE stop signal — sets flag to False immediately
        rather than waiting for frame arrival to time out.
        """
        with self._lock:
            self._screen_sharing_active   = False
            self._screen_sharing_explicit = True
            self._last_ocr_text     = ""
            self._highlighted_region_text = ""
            self._highlighted_region_context = ""
            self._vision_latest_caption = ""
            self._screen_audio_transcript = ""
            self._audio_music_title  = ""
            self._audio_event_description = ""
            self._scene_layout      = {}

        # Clear screen_context.txt artifact on disk immediately
        try:
            screen_ctx_file = os.path.join(_shared_dir(), "screen_context.txt")
            if os.path.exists(screen_ctx_file):
                with open(screen_ctx_file, "w", encoding="utf-8") as sf:
                    sf.write("")
        except Exception as _sc_e:
            logger.debug(f"[PerceptionManager] Screen context file clear error: {_sc_e}")

        try:
            from perception.screen_pipeline import reset_screen_pipeline_state
            reset_screen_pipeline_state()
        except Exception as e:
            logger.debug(f"[PerceptionManager] Screen pipeline reset error: {e}")
        self._flush_to_disk()
        logger.info("[PerceptionManager] Screen share STOPPED (authoritative browser signal).")

    def record_screen_share_stopped(self):
        """Alias kept for backward compatibility. Delegates to mark_screen_share_stopped()."""
        self.mark_screen_share_stopped()

    # ── Diagnostics ──────────────────────────────────────────────────────────

    def get_diagnostic_report(self) -> Dict[str, Any]:
        """Return the full runtime state as a dict. Non-blocking."""
        now = time.time()
        with self._lock:
            state = self._build_state(now)
        
        # Merge read-side files here to provide complete diagnostics
        try:
            # Merge prompt builder stats
            stats_path = os.path.join(os.path.dirname(self._state_path), "prompt_builder_stats.json")
            if os.path.exists(stats_path):
                with open(stats_path, "r", encoding="utf-8") as sf:
                    state.update(json.load(sf))
        except Exception as _err:
            print(f"[perception_manager.py] Silenced exception: {_err}")

        try:
            # Merge speech diagnostics
            speech_path = os.path.join(os.path.dirname(self._state_path), "speech_diagnostics.json")
            if os.path.exists(speech_path):
                with open(speech_path, "r", encoding="utf-8") as sf:
                    state.update(json.load(sf))
        except Exception as _err:
            print(f"[perception_manager.py] Silenced exception: {_err}")

        return state

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _compute_fps(self) -> float:
        """Compute rolling FPS from the last 30 frame timestamps."""
        ts = list(self._frame_timestamps)
        if len(ts) < 2:
            return 0.0
        window = min(10.0, ts[-1] - ts[0])
        if window <= 0:
            return 0.0
        return round((len(ts) - 1) / window, 1)

    def _frame_age(self, now: float) -> float:
        """Seconds since the last frame arrived. Returns inf if never."""
        if self._last_frame_time == 0.0:
            return math.inf
        return now - self._last_frame_time

    def _audio_age(self, now: float) -> float:
        if self._last_audio_time == 0.0:
            return math.inf
        return now - self._last_audio_time

    def _vision_confidence(self) -> float:
        """Estimate vision confidence from available signals."""
        if self._frames_received == 0:
            return 0.0
        score = 0.3  # base for any frame arriving
        if self._frames_received >= MIN_FRAMES_FOR_ACTIVE:
            score += 0.2
        if self._current_app_type not in ("unknown", ""):
            score += 0.2
        if self._ocr_available and self._last_ocr_chars > 50:
            score += 0.2
        if self._vision_model_used:
            score += 0.1
        return round(min(1.0, score), 2)

    def _audio_confidence(self) -> float:
        if self._audio_chunks_received == 0:
            return 0.0
        score = 0.4
        if self._last_audio_rms > 80:
            score += 0.3
        if self._audio_chunks_received >= 3:
            score += 0.3
        return round(min(1.0, score), 2)

    def _track_state_change(self, current_state: dict, now: float):
        if not self._last_recorded_state:
            self._last_recorded_state = dict(current_state)
            return

        changes = []
        old_win = self._last_recorded_state.get("active_window_title", "")
        new_win = current_state.get("active_window_title", "")
        if old_win != new_win and new_win not in ("unknown", ""):
            changes.append(f"focused window changed to '{new_win}'")

        old_app = self._last_recorded_state.get("current_app_type", "")
        new_app = current_state.get("current_app_type", "")
        if old_app != new_app and new_app not in ("unknown", ""):
            changes.append(f"application changed to '{new_app}'")

        old_hl = self._last_recorded_state.get("highlighted_region_text", "")
        new_hl = current_state.get("highlighted_region_text", "")
        if old_hl != new_hl and new_hl:
            changes.append(f"highlighted text: '{new_hl}'")

        old_aud = self._last_recorded_state.get("audio_event_type", "")
        new_aud = current_state.get("audio_event_type", "")
        if old_aud != new_aud and new_aud not in ("silence", "unknown", ""):
            changes.append(f"audio activity: {new_aud}")

        old_click = self._last_recorded_state.get("mouse_button_state", "")
        new_click = current_state.get("mouse_button_state", "")
        if old_click != new_click and new_click != "none":
            changes.append(f"mouse click: {new_click}")

        old_ss = self._last_recorded_state.get("screen_sharing_active")
        new_ss = current_state.get("screen_sharing_active")
        if old_ss != new_ss:
            status = "started" if new_ss else "stopped"
            changes.append(f"screen sharing {status}")

        if changes:
            timestamp_str = time.strftime("%H:%M:%S", time.localtime(now))
            for change in changes:
                self._state_changes.append({
                    "timestamp": now,
                    "time_str": timestamp_str,
                    "change": change
                })
            self._last_recorded_state = dict(current_state)

    def _build_state(self, now: float) -> Dict[str, Any]:
        """Build the full state dict. Must be called under self._lock."""
        frame_age = self._frame_age(now)
        audio_age = self._audio_age(now)
        fps = self._compute_fps()

        # Screen active: honour explicit browser signal first; fall back to
        # frame-arrival heuristic only if no explicit signal has been received.
        if self._screen_sharing_explicit:
            if self._screen_sharing_active:
                # Browser explicitly said "started". Trust it immediately.
                # Belt-and-suspenders: only apply the staleness guard AFTER at
                # least one frame has arrived. If frames arrived but are now
                # very old (stream likely died without a stop signal), go inactive.
                if self._frames_received > 0 and frame_age > FRAME_STALE_SECONDS:
                    frame_live = False  # stream appears to have died
                else:
                    frame_live = True   # trust the explicit start signal
            else:
                # Browser explicitly said "stopped".
                frame_live = False
        else:
            # No explicit signal yet — fall back to heuristic
            frame_live = (frame_age < FRAME_STALE_SECONDS) and (self._frames_received >= MIN_FRAMES_FOR_ACTIVE)

        audio_live = audio_age < AUDIO_STALE_SECONDS
        if not audio_live:
            self._screen_audio_transcript = ""

        state = {
            # ── Core flags ──
            "screen_sharing_active": frame_live,
            "audio_active": audio_live,
            "screen_sharing_explicit": self._screen_sharing_explicit,

            # ── Frame stats ──
            "frames_received": self._frames_received,
            "frames_dropped": self._frames_dropped,
            "last_frame_age_seconds": round(frame_age, 1) if frame_age != math.inf else None,
            "current_fps": fps,

            # ── Audio stats ──
            "audio_chunks_received": self._audio_chunks_received,
            "last_audio_age_seconds": round(audio_age, 1) if audio_age != math.inf else None,
            "last_audio_rms": round(self._last_audio_rms, 1),
            "audio_event_type": self._last_audio_event_type,

            # ── Analysis results ──
            "current_app_type": self._current_app_type,
            "ocr_available": self._ocr_available,
            "last_ocr_chars": self._last_ocr_chars,
            "vision_model_used": self._vision_model_used,

            # ── Confidence ──
            "vision_confidence": self._vision_confidence(),
            "audio_confidence": self._audio_confidence(),

            # ── Session ──
            "session_uptime_seconds": round(now - self._session_start, 0),
            "written_at": now,

            # ── Upgraded diagnostics ──
            "video_receiving": frame_live,
            "video_fps": fps,
            "video_resolution": self._video_resolution,
            "video_latency_ms": round(self._video_latency, 1),
            "video_last_timestamp": self._last_frame_time,
            "audio_receiving": audio_live,
            "audio_sample_rate": self._audio_sample_rate,
            "audio_channels": self._audio_channels,
            "audio_last_timestamp": self._last_audio_time,
            "vision_running": self._vision_running,
            "vision_inference_time_ms": round(self._vision_inference_time, 1),
            "vision_latest_caption": self._vision_latest_caption,
            "audio_model_running": self._audio_model_running,
            "audio_detected_speech": self._audio_detected_speech,
            "audio_detected_music": self._audio_detected_music,
            "audio_detected_sound_events": list(self._audio_detected_sound_events),
            "audio_model_confidence": self._audio_model_confidence,
            # ── Cursor/Window tracking ──
            "cursor_x": self._cursor_x,
            "cursor_y": self._cursor_y,
            "cursor_state": self._cursor_state,
            "active_window_title": self._active_window_title,
            "active_window_class": self._active_window_class,
            "active_window_rect": self._active_window_rect,
            "mouse_button_state": self._mouse_button_state,
            "cursor_hovering_active_window": (
                (self._active_window_rect[0] <= self._cursor_x <= self._active_window_rect[2]) and
                (self._active_window_rect[1] <= self._cursor_y <= self._active_window_rect[3])
                if self._active_window_rect != [0, 0, 0, 0] else False
            ),
            "relative_cursor_x": self._relative_cursor_x,
            "relative_cursor_y": self._relative_cursor_y,
            "active_process_name": self._active_process_name,
            # Fine-grained content fields
            "last_ocr_text": self._last_ocr_text,
            "highlighted_region_text": self._highlighted_region_text,
            "highlighted_region_context": self._highlighted_region_context,
            "audio_event_description": self._audio_event_description,
            "screen_audio_transcript": self._screen_audio_transcript,
            "ocr_confidence": self._ocr_confidence,
            "audio_transcript_confidence": self._audio_transcript_confidence,
            "scene_layout": self._scene_layout,
            "audio_language": self._audio_language,
            "audio_speaker_id": self._audio_speaker_id,
            "audio_music_title": self._audio_music_title,
            "audio_playback_state": self._audio_playback_state,
            "audio_sound_effects": self._audio_sound_effects,

            # ── Face / Gaze Perception Fields ──
            "camera_active": self._camera_active,
            "camera_paused": self._camera_paused,
            "face_detected": (self._face_count > 0) and ((now - getattr(self, "_last_face_update_time", 0.0)) < 12.0),
            "user_visible": self._camera_active and (self._face_count > 0) and ((now - getattr(self, "_last_face_update_time", 0.0)) < 12.0) and (self._presence_state in ("User Present", "User Returned", "Multiple People")),
            "visual_input_available": self._camera_active or frame_live,
            "eye_contact_available": self._camera_active and (self._eye_contact_score > 0.0) and ((now - getattr(self, "_last_face_update_time", 0.0)) < 12.0),
            "presence_state": (self._presence_state if ((now - getattr(self, "_last_face_update_time", 0.0)) < 12.0 or self._presence_state == "User Missing") else "User Missing") if self._camera_active else "Camera OFF",
            "face_count": self._face_count if ((now - getattr(self, "_last_face_update_time", 0.0)) < 12.0) else 0,
            "object_count": self._object_count if ((now - getattr(self, "_last_object_update_time", 0.0)) < 12.0) else 0,
            "detected_objects": self._detected_objects if ((now - getattr(self, "_last_object_update_time", 0.0)) < 12.0) else [],
            "gaze_direction": self._gaze_direction,
            "eye_contact_score": round(self._eye_contact_score, 2),
            "eye_contact_strength": self._eye_contact_strength,
            "attention_score": round(self._attention_score, 1),
            "engagement_score": round(self._engagement_score, 1),
            "presence_score": round(self._presence_score, 1),
            "head_orientation": self._head_orientation,
            "hardware_backend": self._hardware_backend,
            "hardware_mode": self._hardware_mode,
            "face_perception_data": self._face_perception_data,
            "hand_state": self._hand_state if ((now - getattr(self, "_last_hand_update_time", 0.0)) < 12.0) else {},
            "held_objects": self._held_objects if ((now - getattr(self, "_last_hand_update_time", 0.0)) < 12.0) else [],
            "camera_vlm_caption": getattr(self, "_camera_vlm_caption", ""),
        }
        self._track_state_change(state, now)
        state["temporal_history"] = list(self._state_changes)
        return state

    # ── Auto-flush to disk ───────────────────────────────────────────────────

    def _start_flush_thread(self):
        self._flush_running = True
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            daemon=True,
            name="PerceptionManager-Flush"
        )
        self._flush_thread.start()

    def _flush_loop(self):
        while self._flush_running:
            try:
                self._flush_to_disk()
            except Exception as e:
                logger.debug(f"[PerceptionManager] Flush error: {e}")
            time.sleep(1.0)

    def _flush_to_disk(self):
        now = time.time()
        with self._lock:
            state = self._build_state(now)
        try:
            os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
            tmp = self._state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            
            # Retry loop for WinError 32 (file in use)
            import time as _time
            for attempt in range(5):
                try:
                    os.replace(tmp, self._state_path)
                    break
                except OSError as e:
                    if attempt == 4:
                        raise
                    _time.sleep(0.02)
                    
            global _reader_instance
            if _reader_instance is not None:
                _reader_instance._cache = None
                _reader_instance._cache_file_mtime = 0.0
        except Exception as e:
            logger.debug(f"[PerceptionManager] Disk write error: {e}")

    def _start_poll_thread(self):
        if os.name == 'nt':
            self._poll_running = True
            self._poll_thread = threading.Thread(
                target=self._poll_loop,
                daemon=True,
                name="PerceptionManager-Poll"
            )
            self._poll_thread.start()

    def _poll_loop(self):
        # Local imports inside loop to prevent cross-platform import issues on startup
        import ctypes
        import ctypes.wintypes

        class CURSORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.wintypes.DWORD),
                ("flags", ctypes.wintypes.DWORD),
                ("hCursor", ctypes.wintypes.HANDLE),
                ("ptScreenPos", ctypes.wintypes.POINT)
            ]

        IDC_ARROW = 32512
        IDC_IBEAM = 32513
        IDC_WAIT = 32514
        IDC_CROSS = 32515
        IDC_HAND = 32649
        IDC_NO = 32648

        user32 = ctypes.windll.user32

        # Load system cursors
        cursor_names = {}
        for name, cid in [
            ("arrow", IDC_ARROW),
            ("ibeam", IDC_IBEAM),
            ("wait", IDC_WAIT),
            ("cross", IDC_CROSS),
            ("hand", IDC_HAND),
            ("no", IDC_NO),
        ]:
            try:
                h = user32.LoadCursorW(None, ctypes.wintypes.LPCWSTR(cid))
                if h:
                    cursor_names[h] = name
            except Exception as _err:
                print(f"[perception_manager.py] Silenced exception: {_err}")

        while self._poll_running:
            try:
                # 1. Cursor position
                pt = ctypes.wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                cx, cy = pt.x, pt.y

                # 2. Click state
                left_down = bool(user32.GetAsyncKeyState(0x01) & 0x8000)
                right_down = bool(user32.GetAsyncKeyState(0x02) & 0x8000)
                click_state = "none"
                if left_down:
                    click_state = "left_click"
                elif right_down:
                    click_state = "right_click"

                # 3. Active window details
                hwnd = user32.GetForegroundWindow()
                win_title = ""
                win_class = ""
                rect_list = [0, 0, 0, 0]
                proc_name = "unknown"

                if hwnd:
                    # Title
                    buf_title = ctypes.create_unicode_buffer(512)
                    user32.GetWindowTextW(hwnd, buf_title, 512)
                    win_title = buf_title.value

                    # Class name
                    buf_class = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, buf_class, 256)
                    win_class = buf_class.value

                    # Rect/Bounds
                    rect = ctypes.wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    rect_list = [rect.left, rect.top, rect.right, rect.bottom]
                    
                    w_w = rect.right - rect.left
                    w_h = rect.bottom - rect.top
                    rel_x = -1.0
                    rel_y = -1.0
                    if w_w > 0 and w_h > 0:
                        rel_x = round((cx - rect.left) / w_w, 3)
                        rel_y = round((cy - rect.top) / w_h, 3)
                    else:
                        rel_x = -1.0
                        rel_y = -1.0

                    # Get executable/process name
                    try:
                        pid = ctypes.wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        h_process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid) # PROCESS_QUERY_LIMITED_INFORMATION
                        if h_process:
                            try:
                                buf_proc = ctypes.create_unicode_buffer(1024)
                                size_proc = ctypes.wintypes.DWORD(len(buf_proc))
                                if ctypes.windll.kernel32.QueryFullProcessImageNameW(h_process, 0, buf_proc, ctypes.byref(size_proc)):
                                    proc_name = os.path.basename(buf_proc.value)
                            finally:
                                ctypes.windll.kernel32.CloseHandle(h_process)
                    except Exception as _err:
                        print(f"[perception_manager.py] Silenced exception: {_err}")
                else:
                    rel_x = -1.0
                    rel_y = -1.0

                # 4. Cursor shape
                cursor_state = "unknown"
                ci = CURSORINFO()
                ci.cbSize = ctypes.sizeof(CURSORINFO)
                if user32.GetCursorInfo(ctypes.byref(ci)):
                    if ci.flags & 1:  # CURSOR_SHOWING
                        cursor_state = cursor_names.get(ci.hCursor, "arrow")
                    else:
                        cursor_state = "hidden"

                with self._lock:
                    self._cursor_x = cx
                    self._cursor_y = cy
                    self._mouse_button_state = click_state
                    self._active_window_title = win_title
                    self._active_window_class = win_class
                    self._active_window_rect = rect_list
                    self._cursor_state = cursor_state
                    self._relative_cursor_x = rel_x
                    self._relative_cursor_y = rel_y
                    self._active_process_name = proc_name

            except Exception as _err:
                print(f"[perception_manager.py] Silenced exception: {_err}")
            time.sleep(0.1)

    def stop(self):
        self._flush_running = False
        self._poll_running = False


# ─────────────────────────────────────────────────────────────────────────────
# UNIFIED MULTIMODAL WORLD STATE
# ─────────────────────────────────────────────────────────────────────────────
class WorldState:
    """
    Unified representation of Vivy's current multimodal worldview.
    Aggregates real-time sensor state, cursor actions, window coordinates,
    audio events, and historical memory context.
    """
    def __init__(self, sensor_state: Dict[str, Any], memory_context: str = ""):
        self.sensor_state = sensor_state or {}
        self.memory_context = memory_context

    def to_dict(self) -> Dict[str, Any]:
        visual_obs = {
            "source": "screen_capture",
            "active": self.sensor_state.get("screen_sharing_active", False),
            "app_type": self.sensor_state.get("current_app_type", "unknown"),
            "vlm_caption": self.sensor_state.get("vision_latest_caption", ""),
            "confidence": self.sensor_state.get("vision_confidence", 0.0),
            "resolution": self.sensor_state.get("video_resolution", "0x0"),
            "fps": self.sensor_state.get("video_fps", 0.0),
            "latency_ms": self.sensor_state.get("video_latency_ms", 0.0),
            "timestamp": self.sensor_state.get("video_last_timestamp", 0.0),
        }
        
        ocr_obs = {
            "source": "screen_ocr",
            "active": self.sensor_state.get("ocr_available", False),
            "chars_read": self.sensor_state.get("last_ocr_chars", 0),
            "text": self.sensor_state.get("last_ocr_text", ""),
            "highlighted_text": self.sensor_state.get("highlighted_region_text", ""),
            "confidence": self.sensor_state.get("ocr_confidence", 1.0),
        }

        audio_obs = {
            "source": "system_audio",
            "active": self.sensor_state.get("audio_active", False),
            "event_type": self.sensor_state.get("audio_event_type", "silence"),
            "description": self.sensor_state.get("audio_event_description", ""),
            "transcript": self.sensor_state.get("screen_audio_transcript", ""),
            "confidence": self.sensor_state.get("audio_model_confidence", 0.0),
            "transcript_confidence": self.sensor_state.get("audio_transcript_confidence", 1.0),
            "rms_level": self.sensor_state.get("last_audio_rms", 0.0),
            "timestamp": self.sensor_state.get("audio_last_timestamp", 0.0),
        }

        os_obs = {
            "source": "window_manager",
            "foreground_window": self.sensor_state.get("active_window_title", "unknown"),
            "window_class": self.sensor_state.get("active_window_class", "unknown"),
            "window_rect": self.sensor_state.get("active_window_rect", [0, 0, 0, 0]),
            "process_name": self.sensor_state.get("active_process_name", "unknown"),
            "cursor": {
                "x": self.sensor_state.get("cursor_x", 0),
                "y": self.sensor_state.get("cursor_y", 0),
                "relative_x": self.sensor_state.get("relative_cursor_x", -1.0),
                "relative_y": self.sensor_state.get("relative_cursor_y", -1.0),
                "state": self.sensor_state.get("cursor_state", "arrow"),
                "hovering_window": self.sensor_state.get("cursor_hovering_active_window", False),
                "click_action": self.sensor_state.get("mouse_button_state", "none"),
            }
        }

        scene_graph = {
            "active_window": {
                "title": self.sensor_state.get("active_window_title", ""),
                "class": self.sensor_state.get("active_window_class", ""),
                "bounds": self.sensor_state.get("active_window_rect", [0, 0, 0, 0]),
                "process": self.sensor_state.get("active_process_name", "")
            },
            "layout": self.sensor_state.get("scene_layout", {}),
            "highlighted": self.sensor_state.get("highlighted_region_text", ""),
            "cursor": {
                "x": self.sensor_state.get("cursor_x", 0),
                "y": self.sensor_state.get("cursor_y", 0),
                "relative_x": self.sensor_state.get("relative_cursor_x", -1.0),
                "relative_y": self.sensor_state.get("relative_cursor_y", -1.0),
                "state": self.sensor_state.get("cursor_state", "arrow")
            }
        }

        return {
            "visual": visual_obs,
            "ocr": ocr_obs,
            "audio": audio_obs,
            "os": os_obs,
            "scene_graph": scene_graph,
            "temporal_history": self.sensor_state.get("temporal_history", []),
            "memory_context": self.memory_context
        }


# ─────────────────────────────────────────────────────────────────────────────
# READ SIDE  (lives in run_vivy.py / conversation.py process)
# ─────────────────────────────────────────────────────────────────────────────

class PerceptionManagerReader:
    """
    Read-only view of the PerceptionManager state for use inside the
    run_vivy.py / conversation.py process.

    Reads shared/perception_state.json written by the web_server.py process.
    Falls back gracefully if the file does not exist.
    """

    _EMPTY_STATE: Dict[str, Any] = {
        "camera_active": False,
        "camera_paused": False,
        "screen_sharing_active": False,
        "audio_active": False,
        "face_detected": False,
        "user_visible": False,
        "visual_input_available": False,
        "eye_contact_available": False,
        "presence_state": "Camera OFF",
        "face_count": 0,
        "object_count": 0,
        "detected_objects": [],
        "gaze_direction": "Unknown",
        "eye_contact_score": 0.0,
        "eye_contact_strength": "None",
        "attention_score": 0.0,
        "engagement_score": 0.0,
        "presence_score": 0.0,
        "head_orientation": "Head Facing Vivy",
        "hardware_backend": "CPU",
        "hardware_mode": "Avatar OFF Mode",
        "frames_received": 0,
        "frames_dropped": 0,
        "last_frame_age_seconds": None,
        "current_fps": 0.0,
        "audio_chunks_received": 0,
        "last_audio_age_seconds": None,
        "last_audio_rms": 0.0,
        "audio_event_type": "silence",
        "current_app_type": "unknown",
        "ocr_available": False,
        "last_ocr_chars": 0,
        "vision_model_used": False,
        "vision_confidence": 0.0,
        "audio_confidence": 0.0,
        "session_uptime_seconds": 0.0,
        "written_at": 0.0,

        # Upgraded diagnostic metrics
        "video_receiving": False,
        "video_fps": 0.0,
        "video_resolution": "0x0",
        "video_latency_ms": 0.0,
        "video_last_timestamp": 0.0,
        "audio_receiving": False,
        "audio_sample_rate": 16000,
        "audio_channels": 1,
        "audio_last_timestamp": 0.0,
        "vision_running": False,
        "vision_inference_time_ms": 0.0,
        "vision_latest_caption": "",
        "audio_model_running": False,
        "audio_detected_speech": False,
        "audio_detected_music": False,
        "audio_detected_sound_events": [],
        "audio_model_confidence": 0.0,
        "prompt_latest_context": "",
        "prompt_characters_added": 0,
        "prompt_last_inject_timestamp": 0.0,
        "last_speech_transcript": "",
        "last_speech_timestamp": 0.0,
        "screen_audio_transcript": "",
        "highlighted_region_text": "",
        "highlighted_region_context": "",
        "relative_cursor_x": -1.0,
        "relative_cursor_y": -1.0,
        "active_process_name": "unknown"
    }

    def __init__(self):
        self._state_path = _state_path()
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: float = 0.0
        self._cache_ttl: float = 1.5  # seconds

    # ── Public API ───────────────────────────────────────────────────────────

    def get_world_state(self, screen_context: str = "", token_budget: Optional[int] = None) -> WorldState:
        """Fetch the unified WorldState containing both sensor variables and fused timeline context."""
        state = self.load_state()
        try:
            from perception.context_injector import get_perception_context
            mem_ctx = get_perception_context(screen_context=screen_context, token_budget=token_budget)
        except Exception as e:
            logger.debug(f"[WorldState] Failed to build context: {e}")
            mem_ctx = ""
        return WorldState(state, mem_ctx)

    def load_state(self, force_reload: bool = False) -> Dict[str, Any]:
        """Load (or return cached) perception state. Non-blocking, non-fatal."""
        if force_reload:
            self._cache = None
            self._cache_file_mtime = 0.0

        now = time.time()
        file_mtime = 0.0
        if os.path.exists(self._state_path):
            try:
                file_mtime = os.path.getmtime(self._state_path)
            except Exception as _err:
                print(f"[perception_manager.py] Silenced exception: {_err}")

        if not force_reload and self._cache is not None and getattr(self, "_cache_file_mtime", 0.0) == file_mtime and (now - getattr(self, "_cache_time", 0.0)) < 0.2 and file_mtime > 0.0:
            return self._cache

        try:
            if not os.path.exists(self._state_path):
                return dict(self._EMPTY_STATE)
            # Check file age — if written_at is > 30s old, treat as stale
            with open(self._state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            self._cache_file_mtime = file_mtime
            written_at = state.get("written_at", 0.0)
            if (now - written_at) > 30.0:
                # State file is stale (web_server may be starting up or briefly paused).
                # Do NOT discard — annotate with _perception_state_stale=True and return
                # the actual state. build_grounding_context() already applies a stricter
                # 120s + frame_age guard to prevent cross-session bleed.
                # Returning _EMPTY_STATE here was the root cause of "screen sharing
                # is inactive" errors even when the browser had just called /api/screen/start.
                state["_perception_state_stale"] = True
                logger.debug(
                    f"[PerceptionManagerReader] State is {now - written_at:.0f}s old "
                    f"(written_at={written_at:.0f}). Returning annotated stale state "
                    f"(screen_sharing_active={state.get('screen_sharing_active', False)})."
                )

            # Load and merge prompt builder stats from prompt_builder_stats.json if present
            stats_path = os.path.join(os.path.dirname(self._state_path), "prompt_builder_stats.json")
            if os.path.exists(stats_path):
                try:
                    with open(stats_path, "r", encoding="utf-8") as sf:
                        stats = json.load(sf)
                    state.update(stats)
                except Exception as _err:
                    print(f"[perception_manager.py] Silenced exception: {_err}")

            # Load and merge speech diagnostics from speech_diagnostics.json if present
            speech_path = os.path.join(os.path.dirname(self._state_path), "speech_diagnostics.json")
            if os.path.exists(speech_path):
                try:
                    with open(speech_path, "r", encoding="utf-8") as sf:
                        speech_diag = json.load(sf)
                    state.update(speech_diag)
                except Exception as _err:
                    print(f"[perception_manager.py] Silenced exception: {_err}")

            self._cache = state
            self._cache_time = now
            return state
        except Exception as e:
            logger.debug(f"[PerceptionManagerReader] Load error: {e}")
            return dict(self._EMPTY_STATE)

    def is_camera_active(self, force_reload: bool = False) -> bool:
        return self.load_state(force_reload=force_reload).get("camera_active", False)

    def is_face_detected(self, force_reload: bool = False) -> bool:
        st = self.load_state(force_reload=force_reload)
        return st.get("face_detected", False) or (st.get("face_count", 0) > 0)

    def is_user_visible(self, force_reload: bool = False) -> bool:
        st = self.load_state(force_reload=force_reload)
        return st.get("user_visible", False) or (self.is_camera_active(force_reload=force_reload) and self.is_face_detected(force_reload=force_reload))

    def get_capability_registry(self, force_reload: bool = False) -> Dict[str, bool]:
        st = self.load_state(force_reload=force_reload)
        cam = st.get("camera_active", False)
        face = st.get("face_detected", False) or (st.get("face_count", 0) > 0)
        screen = st.get("screen_sharing_active", False)
        audio = st.get("audio_active", False)
        vis = cam and face
        obj_cnt = st.get("object_count", 0)
        return {
            "camera_active": cam,
            "face_detected": face,
            "user_visible": vis,
            "visual_input_available": cam or screen,
            "eye_contact_available": cam and face,
            "screen_sharing_active": screen,
            "audio_active": audio,
            "object_detection_available": cam or screen,
            "objects_detected": obj_cnt > 0,
        }

    def is_screen_sharing_active(self, force_reload: bool = False) -> bool:
        return self.load_state(force_reload=force_reload).get("screen_sharing_active", False)

    def is_audio_active(self) -> bool:
        return self.load_state().get("audio_active", False)

    def get_current_fps(self) -> float:
        return self.load_state().get("current_fps", 0.0)

    def get_vision_confidence(self) -> float:
        return self.load_state().get("vision_confidence", 0.0)

    def get_audio_confidence(self) -> float:
        return self.load_state().get("audio_confidence", 0.0)

    def get_current_app_type(self) -> str:
        return self.load_state().get("current_app_type", "unknown")

    def build_grounding_context(self, screen_context: str = "", wants_vision: bool = True, wants_audio: bool = True) -> str:
        """
        Build a factual, LLM-ready grounding block that accurately describes
        Vivy's current perceptual state.  This replaces the old binary
        "Screen Share: Active / Disconnected" block.

        The returned string is inserted into the LLM system prompt.
        It is ALWAYS factual — never invented by the LLM.
        """
        state = self.load_state()
        active = state.get("screen_sharing_active", False)

        # Fix 3 — Stale state age guard
        # If the state file is older than 120s AND last_frame_age is also old,
        # override active=False regardless of stored flag to prevent cross-session
        # bleed-through (e.g. previous session left perception_state.json with
        # screen_sharing_active=True).
        now = time.time()
        written_at = state.get("written_at", 0.0)
        frame_age_s = state.get("last_frame_age_seconds", None)
        _state_stale = (now - written_at) > 120.0 if written_at > 0 else False
        _frames_stale = (frame_age_s is not None) and (frame_age_s > 120.0)
        if active and _state_stale and _frames_stale:
            active = False  # override: stale state file from previous session

        audio  = state.get("audio_active", False)
        fps    = state.get("current_fps", 0.0)
        frames = state.get("frames_received", 0)
        conf   = state.get("vision_confidence", 0.0)
        app    = state.get("current_app_type", "unknown")
        audio_type = state.get("audio_event_type", "silence")
        audio_conf = state.get("audio_confidence", 0.0)
        ocr    = state.get("ocr_available", False)
        frame_age = frame_age_s

        lines = []

        if active:
            conf_pct = int(conf * 100)
            if frame_age is not None and frame_age < 5:
                freshness = "live"
            elif frame_age is not None and frame_age < 20:
                freshness = f"{int(frame_age)}s ago"
            else:
                freshness = "recent"

            lines.append(f"[Perception State — ACTIVE]")
            if wants_vision:
                lines.append(f"  Screen sharing: ✓ ON  ({frames} frames received, last {freshness})")
                if fps > 0:
                    lines.append(f"  Frame rate: {fps} FPS")
                if app and app != "unknown":
                    lines.append(f"  Detected application: {app}")

                # Cursor position, state, click state, active window details
                win_title = state.get("active_window_title", "")
                if win_title:
                    is_vivy = any(x in win_title.lower() for x in ("vivy ai", "neural interface", "127.0.0.1:8080", "localhost:8080"))
                    if is_vivy:
                        lines.append(f"  Focused Application/Window: \"{win_title}\" (Note: This is Vivy's own chat dashboard; the user is currently typing to Vivy)")
                    else:
                        lines.append(f"  Focused Application/Window: \"{win_title}\"")
                    rect = state.get("active_window_rect", [0, 0, 0, 0])
                    if rect != [0, 0, 0, 0]:
                        lines.append(f"  Active Window Bounds: {rect}")
                cx = state.get("cursor_x", 0)
                cy = state.get("cursor_y", 0)
                rel_cx = state.get("relative_cursor_x", -1.0)
                rel_cy = state.get("relative_cursor_y", -1.0)
                cstate = state.get("cursor_state", "arrow")
                click = state.get("mouse_button_state", "none")
                lines.append(f"  Cursor Position: x={cx}, y={cy}")
                if rel_cx != -1.0 and rel_cy != -1.0:
                    lines.append(f"  Relative Position inside Window: x={rel_cx}, y={rel_cy} (0.0 to 1.0 coordinates)")
                lines.append(f"  Cursor Shape/State: {cstate}")
                if click != "none":
                    lines.append(f"  Mouse Action: {click}")
                if state.get("cursor_hovering_active_window"):
                    lines.append(f"  Cursor Hover State: Hovering inside the focused window")
                else:
                    lines.append(f"  Cursor Hover State: Hovering outside the focused window")

                if ocr:
                    ocr_chars = state.get("last_ocr_chars", 0)
                    ocr_conf = state.get("ocr_confidence", 1.0)
                    ocr_conf_pct = int(ocr_conf * 100)
                    lines.append(f"  OCR text extraction: ✓ active ({ocr_chars} chars read, confidence {ocr_conf_pct}%)")
                    # Highlighted/selected region (highest priority for 'what word is highlighted?')
                    highlighted = state.get("highlighted_region_text", "")
                    highlighted_ctx = state.get("highlighted_region_context", "")
                    if highlighted:
                        lines.append(f"  HIGHLIGHTED/SELECTED TEXT (cursor selection): \"{highlighted.strip()}\"")
                        if highlighted_ctx:
                            lines.append(f"  HIGHLIGHTED TEXT SURROUNDING CONTEXT: \"{highlighted_ctx.strip()}\"")
                lines.append(f"  Vision confidence: {conf_pct}%")

                # VLM caption if available
                vlm_caption = state.get("vision_latest_caption", "")
                if vlm_caption:
                    lines.append(f"  VLM screen description: {vlm_caption[:200]}")

                # Screen context status
                if screen_context:
                    lines.append(f"  Screen context: ✓ available ({len(screen_context)} chars)")
                else:
                    lines.append(f"  Screen context: ⏳ still initializing (no context file yet)")

            # Audio
            if wants_audio:
                if audio:
                    audio_conf_pct = int(audio_conf * 100)
                    audio_transcript_conf = state.get("audio_transcript_confidence", 1.0)
                    audio_transcript_conf_pct = int(audio_transcript_conf * 100)
                    lines.append(f"  Audio: ✓ active ({audio_type}, confidence {audio_conf_pct}%)")
                    music_title = state.get("audio_music_title", "")
                    if music_title:
                        lines.append(f"  Music playing: \"{music_title}\"")
                    audio_desc = state.get("audio_event_description", "")
                    if audio_desc:
                        lines.append(f"  Audio description: {audio_desc}")
                    transcript = state.get("screen_audio_transcript", "")
                    if transcript:
                        lines.append(f"  Audio transcript: \"{transcript}\" (transcription confidence {audio_transcript_conf_pct}%)")
                else:
                    lines.append(f"  Audio: no audio stream detected from screen share")

        else:
            # Screen sharing is not active
            if frames > 0:
                # Was active in this session but stopped
                lines.append(f"[Perception State — INACTIVE]")
                if wants_vision:
                    lines.append(f"  Screen sharing: ✗ OFF (was active earlier this session, {frames} frames received)")
                else:
                    lines.append("  Screen sharing: ✗ OFF")
            else:
                lines.append(f"[Perception State — NOT STARTED]")
                if wants_vision:
                    lines.append(f"  Screen sharing: ✗ OFF (no frames received this session)")
                else:
                    lines.append("  Screen sharing: ✗ OFF")
            lines.append(f"  Audio: ✗ none")

        # ── User Visual Presence & Gaze Perception ──
        cam_active = state.get("camera_active", False)
        face_detected = state.get("face_detected", False) or (state.get("face_count", 0) > 0)
        user_visible = state.get("user_visible", False) or (cam_active and face_detected)
        presence = state.get("presence_state", "User Missing" if cam_active else "Camera OFF")
        gaze_dir = state.get("gaze_direction", "Unknown")
        att_score = state.get("attention_score", 0.0)
        eng_score = state.get("engagement_score", 0.0)
        eye_strength = state.get("eye_contact_strength", "None")
        head_orient = state.get("head_orientation", "Head Facing Vivy")
        hw_backend = state.get("hardware_backend", "CPU")
        hw_mode = state.get("hardware_mode", "Avatar OFF Mode")

        lines.append("")
        lines.append(f"[User Presence & Gaze Perception State]")
        lines.append(f"  Camera status: {'✓ ACTIVE' if cam_active else '✗ INACTIVE (User camera is turned OFF)'}")
        lines.append(f"  Face detection: {'✓ Face tracked' if face_detected else ('✗ Camera active, but no face detected' if cam_active else '✗ No face detected')}")
        lines.append(f"  User visibility: {'✓ Visible to AI' if user_visible else '✗ User not visible'}")
        lines.append(f"  Presence state: {presence}")
        if cam_active and face_detected:
            lines.append(f"  Gaze direction: {gaze_dir} (eye contact: {eye_strength})")
            lines.append(f"  Head pose: {head_orient}")
            lines.append(f"  Attention score: {att_score:.0f}/100 | Engagement: {eng_score:.0f}/100")
        lines.append(f"  Perception hardware mode: {hw_mode} ({hw_backend})")

        return "\n".join(lines)

    def get_live_perception_snapshot(self) -> dict:
        """
        Return a structured dict with the actual fine-grained perception content.
        Used by context_injector.py to build a content-rich snapshot section.
        Keys: ocr_text, vlm_caption, audio_description, audio_type, app_type,
              screen_active, audio_active, vision_confidence.
        Always safe to call — returns empty strings if not available.
        """
        state = self.load_state()
        return {
            "screen_active":      state.get("screen_sharing_active", False),
            "audio_active":       state.get("audio_active", False),
            "app_type":           state.get("current_app_type", "unknown"),
            "vision_confidence":  state.get("vision_confidence", 0.0),
            "ocr_text":           state.get("last_ocr_text", ""),
            "vlm_caption":        state.get("vision_latest_caption", ""),
            "audio_type":         state.get("audio_event_type", "silence"),
            "audio_description":  state.get("audio_event_description", ""),
            "ocr_chars":              state.get("last_ocr_chars", 0),
            "fps":                    state.get("current_fps", 0.0),
            "frames_received":        state.get("frames_received", 0),
            "screen_audio_transcript":state.get("screen_audio_transcript", ""),
            "highlighted_region_text":state.get("highlighted_region_text", ""),
            "highlighted_region_context":state.get("highlighted_region_context", ""),
            "cursor_x":               state.get("cursor_x", 0),
            "cursor_y":               state.get("cursor_y", 0),
            "relative_cursor_x":      state.get("relative_cursor_x", -1.0),
            "relative_cursor_y":      state.get("relative_cursor_y", -1.0),
            "cursor_state":           state.get("cursor_state", "arrow"),
            "active_window_title":    state.get("active_window_title", ""),
            "active_window_rect":     state.get("active_window_rect", [0, 0, 0, 0]),
            "mouse_button_state":     state.get("mouse_button_state", "none"),
            "cursor_hovering_active_window": state.get("cursor_hovering_active_window", False),
            "active_process_name":          state.get("active_process_name", "unknown"),
            "scene_layout":                 state.get("scene_layout", {}),
            "audio_language":               state.get("audio_language", "unknown"),
            "audio_speaker_id":             state.get("audio_speaker_id", "speaker_0"),
            "audio_music_title":            state.get("audio_music_title", ""),
            "audio_playback_state":         state.get("audio_playback_state", "stopped"),
            "audio_sound_effects":          state.get("audio_sound_effects", []),
            "temporal_history":             state.get("temporal_history", []),
            "camera_active":                state.get("camera_active", False),
            "face_detected":                state.get("face_detected", False) or (state.get("face_count", 0) > 0),
            "user_visible":                 state.get("user_visible", False),
            "presence_state":               state.get("presence_state", "User Missing"),
            "face_count":                   state.get("face_count", 0),
            "object_count":                 state.get("object_count", 0),
            "detected_objects":             state.get("detected_objects", []),
            "gaze_direction":               state.get("gaze_direction", "Unknown"),
            "eye_contact_score":            state.get("eye_contact_score", 0.0),
        }

    def build_diagnostic_answer(self, wants_vision: bool = True, wants_audio: bool = True) -> str:
        """
        Build a direct, factual answer to questions like 'Can you see my screen?'
        This is the TRUTH — the LLM then rephrases it naturally.

        Returns a compact string the Dialogue Router prepends to the LLM context
        so Vivy's answer is grounded in runtime reality, not imagination.
        """
        state = self.load_state()
        active = state.get("screen_sharing_active", False)

        # Fix 3 — same stale-state age guard as build_grounding_context()
        now = time.time()
        written_at = state.get("written_at", 0.0)
        frame_age_s = state.get("last_frame_age_seconds", None)
        _state_stale  = (now - written_at) > 120.0 if written_at > 0 else False
        _frames_stale = (frame_age_s is not None) and (frame_age_s > 120.0)
        if active and _state_stale and _frames_stale:
            active = False  # override: stale state from previous session

        audio  = state.get("audio_active", False)
        fps    = state.get("current_fps", 0.0)
        frames = state.get("frames_received", 0)
        conf   = state.get("vision_confidence", 0.0)
        app    = state.get("current_app_type", "unknown")
        audio_type = state.get("audio_event_type", "silence")

        if active and conf >= CONF_HIGH:
            parts = []
            if wants_vision:
                parts.append(f"Vision: ✓ active at {fps} FPS")
                if app and app != "unknown":
                    parts.append(f"App: {app}")
            if audio and wants_audio:
                parts.append(f"Audio: ✓ {audio_type}")
            if wants_vision:
                parts.append(f"Confidence: {int(conf*100)}%")
            return "PERCEPTION_FACT: " + " | ".join(parts)

        elif active and conf >= CONF_LOW:
            parts = []
            if wants_vision:
                parts.append(f"Screen share is active ({frames} frames received), but confidence is still building ({int(conf*100)}%)")
                if app != "unknown":
                    parts.append(f"App detected: {app}")
            if audio and wants_audio:
                parts.append(f"Audio: ✓ {audio_type}")
            elif wants_audio:
                parts.append("No audio stream.")
            return "PERCEPTION_FACT: " + " | ".join(parts)

        elif not active and frames > 0:
            if wants_vision:
                return (
                    "PERCEPTION_FACT: Screen sharing was active earlier but appears to have stopped. "
                    "No recent frames received."
                )
            else:
                return "PERCEPTION_FACT: Screen sharing is currently disconnected."

        else:
            cam_on = state.get("camera_active", False)
            if cam_on:
                face_cnt = state.get("face_count", 0)
                pres_st = state.get("presence_state", "User Present")
                return f"PERCEPTION_FACT: Live user camera is ACTIVE (state: {pres_st}, {face_cnt} face(s) tracked). Screen sharing is inactive."
            if wants_vision:
                return (
                    "PERCEPTION_FACT: Screen sharing is not active. "
                    "No frames have been received this session. "
                    "The user has not shared their screen yet."
                )
            else:
                return "PERCEPTION_FACT: Screen sharing is not active."


# ─────────────────────────────────────────────────────────────────────────────
# Process-level singletons
# ─────────────────────────────────────────────────────────────────────────────

_writer_instance: Optional[PerceptionManagerWriter] = None
_writer_lock = threading.Lock()

_reader_instance: Optional[PerceptionManagerReader] = None
_reader_lock = threading.Lock()


def get_writer() -> PerceptionManagerWriter:
    """Return (lazily create) the process-wide PerceptionManagerWriter."""
    global _writer_instance
    if _writer_instance is None:
        with _writer_lock:
            if _writer_instance is None:
                _writer_instance = PerceptionManagerWriter()
                logger.info("[PerceptionManager] Writer singleton created.")
    return _writer_instance


def get_reader() -> PerceptionManagerReader:
    """Return (lazily create) the process-wide PerceptionManagerReader."""
    global _reader_instance
    if _reader_instance is None:
        with _reader_lock:
            if _reader_instance is None:
                _reader_instance = PerceptionManagerReader()
                logger.info("[PerceptionManager] Reader singleton created.")
    return _reader_instance


def log_capability_mismatch(expected_capability: str, actual_capability: str, responsible_module: str, details: dict = None):
    """
    Self-diagnostic log function when perception capability is active but conversation or downstream
    subsystems disagree.
    """
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    diag_entry = {
        "timestamp": ts,
        "expected_capability": expected_capability,
        "actual_capability": actual_capability,
        "responsible_module": responsible_module,
        "details": details or {},
        "repair_suggestion": f"Ensure {responsible_module} syncs live capability state from CapabilityRegistry."
    }
    logger.warning(f"[PERCEPTION_DIAGNOSTIC_MISMATCH] {json.dumps(diag_entry)}")
    try:
        diag_path = os.path.join(_shared_dir(), "perception_mismatches.jsonl")
        with open(diag_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(diag_entry) + "\n")
    except Exception as ex:
        logger.debug(f"[PerceptionManager] Failed to record mismatch log: {ex}")

