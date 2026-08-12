"""
perception/fusion_engine.py
==============================
Multimodal event fusion layer for the Vivy AI perception system.
Manages asynchronous processing queue, speaker diarization/persistence,
character persistence, and deduplication/prioritization logic.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from typing import Optional, List, Dict, Any

from perception.event_memory import (
    EventMemory,
    PerceptionEvent,
    make_event,
    get_global_memory,
)

logger = logging.getLogger(__name__)


class FusionEngine:
    """
    Multimodal event fusion coordinator.
    Routes semantic events from all perception sources into the shared
    EventMemory via a non-blocking asynchronous queue.
    """

    def __init__(self, memory: Optional[EventMemory] = None):
        self._memory: EventMemory   = memory or get_global_memory()
        self._flush_thread: Optional[threading.Thread] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._running: bool         = False
        self._lock                  = threading.Lock()
        
        self._events_path: Optional[str] = None
        self._flush_interval: float = 1.0
        
        self._last_screen_description: str = ""  # Dedup filter
        self._last_speech_time: float = 0.0      # Priority overlap check

        # ── Observation Narrative Accumulator (Gap 6 — Silent Observation Mode) ──
        self._observation_narrative: str = ""         # Current synthesized narrative
        self._narrative_last_update: float = 0.0      # Timestamp of last narrative update
        self._narrative_interval: float = 30.0        # Update narrative every 30 seconds
        self._current_activity: str = "unknown"       # Detected activity type
        self._media_state: str = "unknown"            # "playing"|"paused"|"stopped"|"unknown"
        self._last_audio_event_time: float = 0.0      # For silence detection
        self._last_user_interaction_time: float = time.time()  # For passive session detection
        self._screen_share_start_time: float = 0.0   # When screen sharing began

        # Async Queue for capture -> perception -> fusion separation
        self._event_queue = queue.Queue(maxsize=1000)
        
        # Diarization & Character Tracking (Session-wide, in-memory)
        self._speakers: Dict[str, str] = {
            "speaker_0": "User (Satyajeet)"
        }
        self._characters: Dict[str, str] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        """Start the background worker and flush threads. Safe to call multiple times."""
        if os.environ.get("VIVY_PROCESS_ROLE") == "runner":
            logger.info("[FusionEngine] Running as runner, background loops skipped.")
            return

        with self._lock:
            if self._running:
                return
            self._running = True
            self._load_config()
            
            # Start asynchronous queue processing worker
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name="FusionEngine-Worker"
            )
            self._worker_thread.start()
            
            # Start background flush thread
            self._flush_thread = threading.Thread(
                target=self._flush_loop,
                daemon=True,
                name="FusionEngine-Flush",
            )
            self._flush_thread.start()
            logger.info("[FusionEngine] Started background worker and flush threads.")

    def stop(self):
        """Signal background threads to stop."""
        with self._lock:
            self._running = False
        logger.info("[FusionEngine] Stopped.")

    # ── Push helpers (asynchronous, puts to queue immediately) ────────────────

    def push_screen_event(self, screen_event: dict):
        self._enqueue("screen", screen_event)

    def push_audio_event(self, audio_event: dict):
        self._enqueue("audio", audio_event)

    def push_user_action(self, action: str, metadata: dict = None):
        self._enqueue("user_action", {"action": action, "metadata": metadata or {}})

    def push_speech_event(self, text: str, metadata: dict = None):
        self._enqueue("speech", {"text": text, "metadata": metadata or {}})

    def push_system_event(self, description: str, importance: float = 0.5):
        self._enqueue("system", {"description": description, "importance": importance})

    def push_perception_event(self, source: str, semantic: str, importance: float = 0.5, confidence: float = 1.0, scope: str = "global", metadata: dict = None):
        self._enqueue("perception", {
            "source": source,
            "semantic": semantic,
            "importance": importance,
            "confidence": confidence,
            "scope": scope,
            "metadata": metadata or {}
        })

    def push_face_event(self, description: str, importance: float = 0.7, metadata: dict = None):
        """Push face detection/presence event into timeline."""
        self.push_perception_event(
            source="face_perception",
            semantic=description,
            importance=importance,
            confidence=1.0,
            scope="local",
            metadata=metadata or {}
        )

    def push_gaze_event(self, description: str, importance: float = 0.6, metadata: dict = None):
        """Push gaze/eye-contact event into timeline."""
        self.push_perception_event(
            source="gaze_perception",
            semantic=description,
            importance=importance,
            confidence=1.0,
            scope="local",
            metadata=metadata or {}
        )

    # ── Internal Queue handling ──────────────────────────────────────────────

    def _enqueue(self, source: str, data: Any):
        if os.environ.get("VIVY_PROCESS_ROLE") == "runner":
            # Forward to web server process in a background thread to keep execution non-blocking
            threading.Thread(target=self._forward_event_http, args=(source, data), daemon=True).start()
            return

        if not self._running:
            self.start()
        try:
            # Non-blocking put, drops event if queue is full (back-pressure safety)
            self._event_queue.put_nowait((source, data))
        except queue.Full:
            logger.warning(f"[FusionEngine] Queue full, dropped event from: {source}")

    def _forward_event_http(self, source: str, data: Any):
        try:
            import requests
            url = "http://127.0.0.1:8080/api/perception/push"
            resp = requests.post(url, json={"source": source, "data": data}, timeout=2.0)
            if resp.status_code != 200:
                logger.warning(f"[FusionEngine] Failed to forward event to web server: {resp.status_code}")
        except Exception as e:
            logger.debug(f"[FusionEngine] HTTP forwarding error: {e}")

    def _worker_loop(self):
        """Processes events from the queue sequentially in background thread."""
        while self._running:
            try:
                # Timeout allows periodic checks of self._running
                item = self._event_queue.get(timeout=0.5)
                source, data = item
                try:
                    self._process_event(source, data)
                except Exception as ex:
                    logger.error(f"[FusionEngine] Error processing event from {source}: {ex}")
                finally:
                    self._event_queue.task_done()
            except queue.Empty:
                # Use idle time to update the observation narrative (Gap 6)
                try:
                    self._update_observation_narrative()
                except Exception as _ne:
                    logger.debug(f"[FusionEngine] Narrative update error: {_ne}")
                continue
            except Exception as e:
                logger.error(f"[FusionEngine] Worker loop processing error: {e}")

    def _process_event(self, source: str, data: Any):
        """Fused event handling, de-duplication, confidence weighting, and diarization."""
        if not data:
            return

        if source == "screen":
            self._process_screen(data)
        elif source == "audio":
            self._process_audio(data)
        elif source == "speech":
            self._process_speech(data)
        elif source == "user_action":
            self._process_user_action(data)
        elif source == "system":
            self._process_system(data)
        elif source == "perception":
            self._process_perception(data)

    # ── Specialized Processing & Deduplication Heuristics ────────────────────

    def _process_screen(self, screen_event: dict):
        description = (screen_event.get("raw_description") or "").strip()
        if not description:
            return

        # Gap 5 fix: Allow rich OCR/VLM events through dedup even if description
        # text is similar — they carry higher-fidelity content worth logging.
        has_rich_data = bool(
            screen_event.get("ocr_text", "") or
            screen_event.get("vision_description", "")
        )
        if description == self._last_screen_description and not has_rich_data:
            return
        self._last_screen_description = description

        # Update screen share tracking for narrative
        if self._screen_share_start_time == 0.0:
            self._screen_share_start_time = time.time()

        # Update current activity from app_type
        app_type = screen_event.get("app_type", "")
        if app_type:
            self._current_activity = app_type

        # Extract character persistence details if present in VLM metadata
        vlm_meta = screen_event.get("vision_metadata", {})
        characters = vlm_meta.get("detected_characters", [])
        for char in characters:
            char_id = char.get("id")
            char_desc = char.get("description", "")
            if char_id and char_desc:
                # Persist temporary session-wide identifier
                self._characters[char_id] = char_desc

        # Build context
        has_ocr     = bool(screen_event.get("ocr_text", ""))
        has_vision  = bool(screen_event.get("vision_description", ""))
        importance  = 0.8 if (has_ocr or has_vision) else 0.4

        event = make_event(
            source="screen_capture",
            semantic=description,
            importance=importance,
            confidence=screen_event.get("ocr_confidence", 1.0),
            scope="shared_screen",
            metadata={
                "app_type":       screen_event.get("app_type", ""),
                "brightness":     screen_event.get("brightness", 0),
                "has_sidebar":    screen_event.get("has_sidebar", False),
                "content_density": screen_event.get("content_density", ""),
                "ocr_chars":      len(screen_event.get("ocr_text", "")),
            },
        )
        self._memory.add(event)

    def _process_audio(self, audio_event: dict):
        description = (audio_event.get("description") or "").strip()
        if not description:
            return

        event_type = audio_event.get("event_type", "ambient")

        # Dedup identical consecutive events within 10 seconds to avoid memory spam
        now = time.time()
        last_audio = getattr(self, "_last_audio_event_data", {})
        if (last_audio.get("event_type") == event_type and 
            last_audio.get("description") == description and 
            now - last_audio.get("time", 0.0) < 10.0):
            return
        
        self._last_audio_event_data = {
            "event_type": event_type,
            "description": description,
            "time": now
        }

        # Track audio state for meaningful event detection (Gap 7)
        if event_type in ("speech", "music", "ambient"):
            self._media_state = "playing"
            self._last_audio_event_time = time.time()
        elif event_type == "silence":
            # Significant silence — check if media was previously playing
            if self._media_state == "playing" and self._last_audio_event_time > 0:
                silence_duration = time.time() - self._last_audio_event_time
                if silence_duration > 30.0:
                    self._media_state = "paused"
                    # Emit meaningful event for proactivity engine
                    self.push_system_event(
                        f"Audio went silent after {int(silence_duration)}s of activity — media may have paused.",
                        importance=0.7
                    )
        
        # Deduplication: If we recently (last 2 seconds) processed actual speech recognition,
        # ignore heuristic audio classification labeled as 'speech' to prioritize high confidence.
        if event_type == "speech" and (time.time() - self._last_speech_time < 2.0):
            logger.debug("[FusionEngine] Dropped heuristic speech event; prioritized high-confidence transcription.")
            return

        importance = {
            "speech":  0.7,
            "music":   0.5,
            "alarm":   0.9,
            "ambient": 0.3,
            "silence": 0.1,
        }.get(event_type, 0.4)

        source_label = audio_event.get("source_label") or audio_event.get("source") or "audio"
        source_name = "system_audio" if source_label in ("screen_audio", "system") else "microphone_audio"
        scope = "shared_screen" if source_name == "system_audio" else "local"
        confidence = audio_event.get("confidence", 1.0)

        event = make_event(
            source=source_name,
            semantic=description,
            importance=importance,
            confidence=confidence,
            scope=scope,
            metadata={
                "event_type":       event_type,
                "confidence":       confidence,
                "duration_seconds": audio_event.get("duration_seconds", 0.0),
            },
        )
        self._memory.add(event)

    def _process_speech(self, data: dict):
        text = (data.get("text") or "").strip()
        if not text:
            return
        
        self._last_speech_time = time.time()
        metadata = data.get("metadata", {})
        
        # Speaker Diarization / Persistence mapping
        speaker_id = metadata.get("speaker_id", "speaker_0")
        speaker_name = self._speakers.get(speaker_id)
        if not speaker_name:
            # Create a temporary identifier for a new speaker
            speaker_name = f"Speaker {len(self._speakers)}"
            self._speakers[speaker_id] = speaker_name
            
        semantic_text = f"[{speaker_name}]: {text}"

        event = make_event(
            source="speech_recognition",
            semantic=semantic_text,
            importance=0.9,
            confidence=metadata.get("confidence", 1.0),
            scope="local",
            metadata=metadata,
        )
        self._memory.add(event)

    def _process_user_action(self, data: dict):
        action = (data.get("action") or "").strip()
        if not action:
            return
        metadata = data.get("metadata", {})

        # Track last user interaction time for passive session detection (Gap 7)
        self._last_user_interaction_time = time.time()

        event = make_event(
            source="user_action",
            semantic=action,
            importance=0.6,
            confidence=1.0,
            scope="session",
            metadata=metadata,
        )
        self._memory.add(event)

    def _process_system(self, data: dict):
        desc = data.get("description", "")
        importance = data.get("importance", 0.5)
        
        event = make_event(
            source="system",
            semantic=desc,
            importance=importance,
            confidence=1.0,
            scope="session",
        )
        self._memory.add(event)

    def _process_perception(self, data: dict):
        event = make_event(
            source=data.get("source", "system"),
            semantic=data.get("semantic", ""),
            importance=data.get("importance", 0.5),
            confidence=data.get("confidence", 1.0),
            scope=data.get("scope", "global"),
            metadata=data.get("metadata", {}),
        )
        self._memory.add(event)
        
        # Phase 2 Integration: Belief Engine for highly important visual/social events
        if event["importance"] >= 0.7 and event["confidence"] >= 0.8:
            if event["source"] in ("face_perception", "gaze_perception"):
                try:
                    from agi.belief_engine import get_belief_engine
                    get_belief_engine().assert_belief(
                        f"Current User State: {event['semantic']}",
                        confidence=event["confidence"],
                        evidence=f"Live perception from {event['source']}",
                        category="user_state"
                    )
                except Exception as _be_err:
                    pass

    # ── Observation Narrative (Gap 6 — Silent Observation Mode) ─────────────

    def _update_observation_narrative(self):
        """
        Synthesize a rolling plain-text narrative of what Vivy has been observing.
        Updates every self._narrative_interval seconds.
        Called from the worker loop (background thread, non-blocking).
        """
        now = time.time()
        if now - self._narrative_last_update < self._narrative_interval:
            return
        self._narrative_last_update = now

        try:
            # Gather recent events (last 5 minutes)
            recent = self._memory.get_recent_events(max_age_seconds=300)
            if not recent:
                self._observation_narrative = ""
                return

            # Count sources
            screen_evs  = [e for e in recent if e["source"] in ("screen", "screen_capture")]
            audio_evs   = [e for e in recent if e["source"] in ("audio", "system_audio", "microphone_audio")]
            speech_evs  = [e for e in recent if e["source"] in ("speech", "speech_recognition")]

            parts = []

            # Screen observation summary
            if screen_evs:
                activity = self._current_activity or "the screen"
                if self._screen_share_start_time > 0:
                    elapsed_min = int((now - self._screen_share_start_time) / 60)
                    if elapsed_min >= 1:
                        parts.append(f"Screen share active for ~{elapsed_min} min showing {activity}.")
                    else:
                        parts.append(f"Screen share just started showing {activity}.")
                else:
                    parts.append(f"Observing {activity} on screen.")

                # Most recent screen description
                last_screen = screen_evs[-1]["semantic"] if screen_evs else ""
                if last_screen and last_screen not in parts[-1]:
                    parts.append(f"Latest: {last_screen[:120]}")

            # Audio observation summary
            if audio_evs:
                # Get most recent distinct audio event types
                recent_audio_types = list(dict.fromkeys(
                    e["metadata"].get("event_type", "ambient")
                    for e in reversed(audio_evs)
                ))[:3]
                audio_summary = ", ".join(t for t in recent_audio_types if t != "silence")
                if audio_summary:
                    parts.append(f"Background audio: {audio_summary}.")
                elif self._media_state == "paused":
                    parts.append("Audio recently went silent (media may be paused).")
            elif self._screen_share_start_time > 0:
                parts.append("No audio detected from screen share.")

            # Speech observation
            if speech_evs:
                parts.append(f"{len(speech_evs)} voice message(s) recorded this session.")

            # Passive session detection (Gap 7)
            passive_duration = now - self._last_user_interaction_time
            if passive_duration > 300 and self._screen_share_start_time > 0:  # 5 min
                parts.append(
                    f"No user interaction for {int(passive_duration / 60)} min "
                    f"— Vivy has been silently observing."
                )
                # Emit meaningful system event for proactivity engine
                try:
                    self.push_system_event(
                        f"User has been passively present for {int(passive_duration / 60)} minutes "
                        f"while Vivy observes the screen ({self._current_activity or 'activity'}).",
                        importance=0.6
                    )
                except Exception as _err:
                    print(f"[fusion_engine.py] Silenced exception: {_err}")

            self._observation_narrative = " ".join(parts) if parts else ""

        except Exception as e:
            logger.debug(f"[FusionEngine] Narrative update failed: {e}")

    def get_observation_narrative(self) -> str:
        """Return the current synthesized observation narrative for prompt injection."""
        if os.environ.get("VIVY_PROCESS_ROLE") == "runner":
            try:
                import requests
                resp = requests.get("http://127.0.0.1:8080/api/perception/narrative", timeout=2.0)
                if resp.status_code == 200:
                    return resp.json().get("narrative", "")
            except Exception as e:
                logger.debug(f"[FusionEngine] Failed to fetch narrative from web server: {e}")
        return self._observation_narrative

    # ── Context & Status Accessors ───────────────────────────────────────────

    def get_recent_events(self, max_age_seconds: Optional[float] = None) -> List[PerceptionEvent]:
        if os.environ.get("VIVY_PROCESS_ROLE") == "runner":
            try:
                import requests
                url = "http://127.0.0.1:8080/api/perception/events"
                resp = requests.get(url, timeout=2.0)
                if resp.status_code == 200:
                    events = resp.json().get("events", [])
                    if max_age_seconds:
                        cutoff = time.time() - max_age_seconds
                        events = [e for e in events if e.get("timestamp", 0.0) >= cutoff]
                    return events
            except Exception as e:
                logger.debug(f"[FusionEngine] Failed to fetch events from web server: {e}")
                try:
                    self._memory.load_state()
                except Exception as _err:
                    print(f"[fusion_engine.py] Silenced exception: {_err}")
            return self._memory.get_recent_events(max_age_seconds)

        try:
            self._event_queue.join()
        except Exception as _err:
            print(f"[fusion_engine.py] Silenced exception: {_err}")
        return self._memory.get_recent_events(max_age_seconds)

    def get_context_for_prompt(self, token_budget: Optional[int] = None) -> str:
        try:
            self._event_queue.join()
        except Exception as _err:
            print(f"[fusion_engine.py] Silenced exception: {_err}")
        return self._memory.get_context_for_prompt(token_budget)

    def event_count(self) -> int:
        if os.environ.get("VIVY_PROCESS_ROLE") == "runner":
            try:
                import requests
                resp = requests.get("http://127.0.0.1:8080/api/perception/status", timeout=2.0)
                if resp.status_code == 200:
                    return resp.json().get("event_count", 0)
            except Exception as e:
                logger.debug(f"[FusionEngine] Failed to fetch event count from web server: {e}")
        try:
            self._event_queue.join()
        except Exception as _err:
            print(f"[fusion_engine.py] Silenced exception: {_err}")
        return self._memory.event_count()

    # ── Storage Synchronization ──────────────────────────────────────────────

    def _load_config(self):
        try:
            from perception.config_loader import get, get_project_root
            self._flush_interval = float(
                get("multimodal", "fusion_interval_seconds", default=1.0)
            )
            shared_dir = get("paths", "shared_dir", default="shared")
            self._events_path = os.path.join(
                get_project_root(), shared_dir, "perception_events.json"
            )
        except Exception as e:
            logger.warning(f"[FusionEngine] Config load error, using defaults: {e}")
            self._flush_interval = 1.0
            self._events_path    = None

    def _flush_loop(self):
        while self._running:
            try:
                self._flush_to_disk()
            except Exception as e:
                logger.debug(f"[FusionEngine] Flush error: {e}")
            time.sleep(self._flush_interval)

    def _flush_to_disk(self):
        try:
            # Auto-save the full hierarchical memory state
            self._memory.save_state()
        except Exception as e:
            logger.debug(f"[FusionEngine] Memory state auto-save failed: {e}")

        if not self._events_path:
            return

        events = self._memory.get_recent_events()
        if not events:
            return

        payload = {
            "flushed_at": time.time(),
            "count":      len(events),
            "events": [
                {
                    "id":         e["id"],
                    "timestamp":  e["timestamp"],
                    "source":     e["source"],
                    "semantic":   e["semantic"],
                    "importance": e["importance"],
                }
                for e in events[-50:]
            ],
        }

        try:
            os.makedirs(os.path.dirname(self._events_path), exist_ok=True)
            tmp = self._events_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self._events_path)
        except Exception as e:
            logger.debug(f"[FusionEngine] Disk flush failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Process-wide singleton
# ─────────────────────────────────────────────────────────────────────────────
_global_engine: FusionEngine | None = None
_global_engine_lock = threading.Lock()


def get_global_engine() -> FusionEngine:
    global _global_engine
    if _global_engine is None:
        with _global_engine_lock:
            if _global_engine is None:
                _global_engine = FusionEngine()
                _global_engine.start()
    return _global_engine
