"""
perception/event_memory.py
============================
Rolling semantic event log for the Vivy AI multimodal perception system.
Implements Hierarchical Memory layers: Short-term, Working, Episodic, and Long-term.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import TypedDict, List, Optional, Dict, Any

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────
class PerceptionEvent(TypedDict):
    """A single semantic perception event — the atomic unit of the event log."""
    id:         str
    timestamp:  float
    source:     str
    confidence: float
    scope:      str
    semantic:   str
    importance: float
    metadata:   dict


# ─────────────────────────────────────────────────────────────────────────────
# EventMemory
# ─────────────────────────────────────────────────────────────────────────────
class EventMemory:
    """
    Thread-safe rolling semantic event log.
    
    Layers:
      - Short-term: Last few seconds (configurable, default 30s)
      - Working memory: Last several minutes (from 30s up to retention window)
      - Episodic: Summaries of completed scenes
      - Long-term: User-approved important facts
    """

    def __init__(self):
        self._events:            List[PerceptionEvent] = []
        self._summary:           str                   = ""
        self._lock               = threading.Lock()
        self._evict_counter:     int                   = 0
        self._episodic_summaries: List[str]             = []
        self._long_term_approved: List[str]             = []
        self._state_loaded:      bool                  = False

        # Config (loaded lazily)
        self._retention_seconds: Optional[float] = None
        self._max_events:        Optional[int]   = None
        self._token_budget:      Optional[int]   = None
        self._summary_trigger:   Optional[int]   = None
        self._summary_path:      Optional[str]   = None
        self._short_term_seconds: Optional[float] = None

    def _load_config(self):
        """Lazy config load — called once on first use."""
        try:
            from perception.config_loader import get, get_project_root
            if self._retention_seconds is None:
                minutes = get("multimodal", "event_memory_minutes", default=10)
                self._retention_seconds = float(minutes) * 60
            if self._max_events is None:
                self._max_events = int(get("multimodal", "event_memory_max_events", default=200))
            if self._token_budget is None:
                self._token_budget = int(get("multimodal", "context_token_budget", default=300))
            if self._summary_trigger is None:
                self._summary_trigger = int(get("multimodal", "summary_trigger_count", default=50))
            if self._short_term_seconds is None:
                self._short_term_seconds = float(get("multimodal", "short_term_memory_seconds", default=30))
            if self._summary_path is None:
                shared_dir = get("paths", "shared_dir", default="shared")
                self._summary_path = os.path.join(get_project_root(), shared_dir, "perception_summary.txt")
        except Exception as e:
            logger.warning(f"[EventMemory] Config load failed, using defaults: {e}")
            if self._retention_seconds is None:
                self._retention_seconds = 600.0
            if self._max_events is None:
                self._max_events = 200
            if self._token_budget is None:
                self._token_budget = 300
            if self._summary_trigger is None:
                self._summary_trigger = 50
            if self._short_term_seconds is None:
                self._short_term_seconds = 30.0
            if self._summary_path is None:
                self._summary_path = None

        # Load serialized state once configuration paths are resolved
        if not getattr(self, "_state_loaded", False):
            self._state_loaded = True
            try:
                self.load_state()
            except Exception as le:
                logger.error(f"[EventMemory] Error loading state on init: {le}")

    # ── Public API ────────────────────────────────────────────────────────────

    def add(self, event: PerceptionEvent):
        """Add a new perception event to the log."""
        self._load_config()
        with self._lock:
            self._events.append(event)
            self._evict_counter += 1

            # Trigger summarization periodically
            if self._evict_counter >= self._summary_trigger:
                self._evict_counter = 0
                self._evict_old_events()

            # Hard cap
            if len(self._events) > self._max_events:
                self._evict_old_events()

    def get_recent_events(self, max_age_seconds: Optional[float] = None) -> List[PerceptionEvent]:
        """Return events newer than max_age_seconds (or retention window if None)."""
        self._load_config()
        cutoff = time.time() - (max_age_seconds or self._retention_seconds)
        with self._lock:
            return [e for e in self._events if e["timestamp"] >= cutoff]

    # ── Hierarchical Memory Layer Accessors ───────────────────────────────────

    def get_short_term_events(self) -> List[PerceptionEvent]:
        """Get events from the last short_term_seconds (default 30s)."""
        self._load_config()
        cutoff = time.time() - self._short_term_seconds
        with self._lock:
            return [e for e in self._events if e["timestamp"] >= cutoff]

    def get_working_memory_events(self) -> List[PerceptionEvent]:
        """Get working memory events (older than short term, but within retention window)."""
        self._load_config()
        now = time.time()
        st_cutoff = now - self._short_term_seconds
        ret_cutoff = now - self._retention_seconds
        with self._lock:
            return [e for e in self._events if ret_cutoff <= e["timestamp"] < st_cutoff]

    def add_episodic_summary(self, summary: str):
        """Add a semantic summary of a completed scene or boundary."""
        with self._lock:
            self._episodic_summaries.append(summary)
            # Cap episodic summaries to last 20 to control space
            if len(self._episodic_summaries) > 20:
                self._episodic_summaries.pop(0)

    def get_episodic_summaries(self) -> List[str]:
        with self._lock:
            return list(self._episodic_summaries)

    def approve_for_long_term(self, event_id: str):
        """Promote a specific perception event to long-term approved memory."""
        with self._lock:
            for ev in self._events:
                if ev["id"] == event_id:
                    mem_str = f"Observed at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ev['timestamp']))}: {ev['semantic']}"
                    if mem_str not in self._long_term_approved:
                        self._long_term_approved.append(mem_str)
                        logger.info(f"[EventMemory] Promoted event {event_id} to long-term memory.")
                    break

    def get_long_term_memories(self) -> List[str]:
        with self._lock:
            return list(self._long_term_approved)

    # ── LLM Prompt Context Builder ──────────────────────────────────────────

    def get_context_for_prompt(self, token_budget: Optional[int] = None) -> str:
        """
        Return a formatted string of hierarchical perception events for prompt injection.
        Prioritizes: Short-term > Working Memory > Episodic Summaries > Long-term memories.
        """
        self._load_config()
        budget = token_budget or self._token_budget
        char_budget = budget * 4  # approximate chars -> tokens

        with self._lock:
            now = time.time()
            st_cutoff = now - self._short_term_seconds
            
            # 1. Short-term (newest first)
            short_term = [e for e in self._events if e["timestamp"] >= st_cutoff]
            short_term.sort(key=lambda x: x["timestamp"], reverse=True)
            
            # 2. Working memory (newest first)
            working = [e for e in self._events if e["timestamp"] < st_cutoff]
            working.sort(key=lambda x: x["timestamp"], reverse=True)
            
            # 3. Episodic summaries
            episodes = list(self._episodic_summaries)
            
            # 4. Long-term approved memories
            long_term = list(self._long_term_approved)
            
            # 5. Earlier evicted summaries (if any)
            rolling_summary = self._summary

        lines: list[str] = []
        used_chars = 0

        has_content = False

        # Inject approved long-term memories first if available
        if long_term:
            lt_header = "[Important Relational Memories]"
            lines.append(lt_header)
            used_chars += len(lt_header) + 1
            for lt in long_term:
                line = f"• {lt}"
                if used_chars + len(line) + 1 > char_budget:
                    break
                lines.append(line)
                used_chars += len(line) + 1
                has_content = True

        # Inject episodic scene summaries
        if episodes:
            ep_header = "\n[Recent Scene Summary]"
            if used_chars + len(ep_header) + 1 <= char_budget:
                lines.append(ep_header)
                used_chars += len(ep_header) + 1
                for ep in reversed(episodes):
                    line = f"• {ep}"
                    if used_chars + len(line) + 1 > char_budget:
                        break
                    lines.append(line)
                    used_chars += len(line) + 1
                    has_content = True

        # Inject rolling evicted summary
        if rolling_summary:
            rs_line = f"\n[Earlier activity summary]\n{rolling_summary}"
            if used_chars + len(rs_line) + 1 <= char_budget:
                lines.append(rs_line)
                used_chars += len(rs_line) + 1
                has_content = True

        # Inject short-term and working-memory events chronologically
        recent_header = "\n[Timeline of observations]"
        if (short_term or working) and used_chars + len(recent_header) + 1 <= char_budget:
            lines.append(recent_header)
            used_chars += len(recent_header) + 1

            # Interleave short term and working memory, newest first, respect budget
            combined_recent = (short_term + working)[:self._summary_trigger]
            for ev in combined_recent:
                ts_str = _fmt_timestamp(ev["timestamp"])
                line = f"[{ts_str}] ({ev['source']}) {ev['semantic']}"
                if used_chars + len(line) + 1 > char_budget:
                    break
                lines.append(line)
                used_chars += len(line) + 1
                has_content = True

        if not has_content:
            return ""

        return "\n".join(lines)

    def get_recent_narrative(self, max_events: int = 10) -> str:
        self._load_config()
        with self._lock:
            recent = list(reversed(self._events))[:max_events]

        if not recent:
            return ""

        parts = []
        for ev in reversed(recent):  # chronological order
            ts_str = _fmt_timestamp(ev["timestamp"])
            parts.append(f"{ts_str}: {ev['semantic']}")
        return "\n".join(parts)

    def get_temporal_history_string(self, duration_seconds: float = 60.0) -> str:
        """Get a chronological textual description of events in the last duration_seconds."""
        self._load_config()
        events = self.get_recent_events(max_age_seconds=duration_seconds)
        events.sort(key=lambda x: x["timestamp"])
        if not events:
            return "No activity recorded in the last minute."
        lines = []
        for ev in events:
            ts_str = _fmt_timestamp(ev["timestamp"])
            lines.append(f"[{ts_str}] ({ev['source']}) {ev['semantic']}")
        return "\n".join(lines)

    def clear(self):
        with self._lock:
            self._events.clear()
            self._summary = ""
            self._episodic_summaries.clear()
            self._long_term_approved.clear()

    def event_count(self) -> int:
        with self._lock:
            return len(self._events)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _evict_old_events(self):
        now = time.time()
        cutoff = now - self._retention_seconds

        to_evict = [e for e in self._events if e["timestamp"] < cutoff]
        to_keep  = [e for e in self._events if e["timestamp"] >= cutoff]

        if len(to_keep) > self._max_events:
            to_keep.sort(key=lambda e: (e["importance"], e["timestamp"]))
            overflow  = len(to_keep) - self._max_events
            to_evict += to_keep[:overflow]
            to_keep   = to_keep[overflow:]

        if to_evict:
            self._events = to_keep
            self._summary = self._compress_into_summary(to_evict, self._summary)
            self._persist_summary()
            logger.debug(f"[EventMemory] Evicted {len(to_evict)} events. Summary length: {len(self._summary)}")

    def _compress_into_summary(self, evicted: List[PerceptionEvent], existing_summary: str) -> str:
        if not evicted:
            return existing_summary

        lines = []
        for ev in evicted:
            ts_str = _fmt_timestamp(ev["timestamp"])
            lines.append(f"• {ts_str}: {ev['semantic']}")

        new_section = "\n".join(lines)
        combined = (existing_summary + "\n" + new_section).strip() if existing_summary else new_section

        if len(combined) > 500:
            combined = combined[-500:]
            nl_idx = combined.find("\n")
            if nl_idx > 0:
                combined = combined[nl_idx + 1:]

        return combined

    def save_state(self):
        """Serialize the current EventMemory state to shared/event_memory_state.json."""
        self._load_config()
        if not self._summary_path:
            return
        state_path = os.path.join(os.path.dirname(self._summary_path), "event_memory_state.json")
        try:
            import json
            state = {
                "events": self._events,
                "summary": self._summary,
                "episodic_summaries": self._episodic_summaries,
                "long_term_approved": self._long_term_approved,
            }
            tmp = f"{state_path}.{os.getpid()}_{threading.get_ident()}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            
            # Windows-safe atomic file replace with retry loop for file lock contention
            replaced = False
            for attempt in range(5):
                try:
                    os.replace(tmp, state_path)
                    replaced = True
                    break
                except (PermissionError, OSError):
                    time.sleep(0.05 * (2 ** attempt))
            if not replaced:
                try:
                    import shutil
                    shutil.copy2(tmp, state_path)
                except Exception as _err:
                    print(f"[event_memory.py] Silenced exception: {_err}")
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception as _err:
                    print(f"[event_memory.py] Silenced exception: {_err}")
            logger.debug(f"[EventMemory] Saved memory state to {state_path}")
        except Exception as e:
            logger.error(f"[EventMemory] Failed to save memory state: {e}")

    def load_state(self):
        """Deserialize the EventMemory state from shared/event_memory_state.json."""
        self._load_config()
        if not self._summary_path:
            return
        state_path = os.path.join(os.path.dirname(self._summary_path), "event_memory_state.json")
        if not os.path.exists(state_path):
            logger.info(f"[EventMemory] No serialized state found at {state_path}")
            return
        try:
            import json
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            self._events = state.get("events", [])
            self._summary = state.get("summary", "")
            self._episodic_summaries = state.get("episodic_summaries", [])
            self._long_term_approved = state.get("long_term_approved", [])
            logger.info(f"[EventMemory] Loaded memory state from {state_path} ({len(self._events)} events)")
        except Exception as e:
            logger.error(f"[EventMemory] Failed to load memory state: {e}")

    def _persist_summary(self):
        if not self._summary_path:
            return
        try:
            os.makedirs(os.path.dirname(self._summary_path), exist_ok=True)
            with open(self._summary_path, "w", encoding="utf-8") as f:
                f.write(self._summary)
        except Exception as e:
            logger.debug(f"[EventMemory] Could not persist summary: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _fmt_timestamp(ts: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def make_event(
    source: str,
    semantic: str,
    importance: float = 0.5,
    confidence: float = 1.0,
    scope: str = "global",
    metadata: dict = None,
    timestamp: Optional[float] = None
) -> PerceptionEvent:
    import uuid
    return PerceptionEvent(
        id=str(uuid.uuid4()),
        timestamp=timestamp or time.time(),
        source=source,
        confidence=confidence,
        scope=scope,
        semantic=semantic,
        importance=importance,
        metadata=metadata or {},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────────────────────────────────────
_global_memory: EventMemory | None = None
_global_lock = threading.Lock()


def get_global_memory() -> EventMemory:
    global _global_memory
    if _global_memory is None:
        with _global_lock:
            if _global_memory is None:
                _global_memory = EventMemory()
    return _global_memory
