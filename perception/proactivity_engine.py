"""
perception/proactivity_engine.py
==================================
Proactivity engine for Vivy AI — allows Vivy to spontaneously comment
on significant perceived events without waiting for the user to speak.

DISABLED BY DEFAULT — set "proactivity.enabled": true in vivy_config.json.
When disabled, this module is completely inert.

When enabled:
  1. Monitors the FusionEngine's event stream in a background thread
  2. Scores new events by significance using heuristics
  3. If a significant event exceeds the configured threshold AND the
     minimum interval has elapsed, injects a proactive trigger by
     writing to shared/user_text.txt with a special prefix
  4. The prefix tells run_vivy.py this is a proactive (non-user) message
     so it does NOT play voice output or trigger lip sync

Design rules:
  - Never interrupts the pipeline if a response is in progress
  - Respects min_interval_seconds to avoid spam
  - Respects max_per_session to limit total proactive comments
  - The special trigger is indistinguishable to conversation.py — it is
    just text that Vivy responds to naturally
  - session safety: reads shared/status.txt before injecting to avoid
    interrupting thinking/speaking states

Proactive message format injected to user_text.txt:
  [PERCEPTION_TRIGGER] <context about what was observed>
    
run_vivy.py detects the [PERCEPTION_TRIGGER] prefix and:
  - processes it as a text-mode turn (no voice output)
  - strips the prefix before passing to conversation.py
  - uses input_source.txt="proactive" to signal no audio
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Prefix used to identify proactive triggers in user_text.txt
PROACTIVE_PREFIX = "[PERCEPTION_TRIGGER]"


class ProactivityEngine:
    """
    Background proactivity monitor.

    Watches the perception event stream for significant events and
    injects proactive triggers into the pipeline when appropriate.
    """

    def __init__(self):
        self._thread:        Optional[threading.Thread] = None
        self._running:       bool                       = False
        self._lock           = threading.Lock()
        self._last_inject_ts: float                     = 0.0
        self._inject_count:   int                       = 0
        self._config:         dict                      = {}
        self._shared_dir:     str                       = ""
        self._user_txt:       str                       = ""
        self._status_txt:     str                       = ""
        self._source_txt:     str                       = ""
        self._triggered_event_ids: set[str]             = set()

    def start(self) -> bool:
        """Start if enabled by config. Returns True if started."""
        cfg = self._load_config()
        if not cfg.get("enabled", False):
            logger.info("[ProactivityEngine] Disabled by config — not starting.")
            return False

        with self._lock:
            if self._running:
                return True
            self._running = True

        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="ProactivityEngine",
        )
        self._thread.start()
        logger.info("[ProactivityEngine] Started.")
        return True

    def stop(self):
        with self._lock:
            self._running = False
        logger.info("[ProactivityEngine] Stopped.")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        try:
            from perception.config_loader import get_config, get_project_root, get
            self._config = get_config().get("proactivity", {})
            shared_dir   = get("paths", "shared_dir", default="shared")
            root         = get_project_root()
            self._shared_dir = os.path.join(root, shared_dir)
            self._user_txt   = os.path.join(self._shared_dir, "user_text.txt")
            self._status_txt = os.path.join(self._shared_dir, "status.txt")
            self._source_txt = os.path.join(self._shared_dir, "input_source.txt")
        except Exception as e:
            logger.warning(f"[ProactivityEngine] Config load error: {e}")
            self._config = {}
        return self._config

    def _monitor_loop(self):
        """Background loop: check for significant events and inject triggers."""
        check_interval = 5.0  # Check every 5 seconds (low overhead)
        threshold       = float(self._config.get("threshold", 0.8))
        min_interval    = float(self._config.get("min_interval_seconds", 30))
        max_per_session = int(self._config.get("max_per_session", 20))

        logger.info("[ProactivityEngine] Entering monitor loop.")

        while self._running:
            try:
                # Phase 4 Integration: Do not trigger proactive speech during Sleep/PreDawn
                try:
                    from circadian_intelligence import get_circadian_intelligence
                    ci = get_circadian_intelligence()
                    current_phase = ci.get_current_phase()
                    if current_phase in ["Sleep", "PreDawn", "LateNight"]:
                        time.sleep(check_interval)
                        continue
                except Exception:
                    pass

                # Safety: don't inject if pipeline is busy
                if self._pipeline_is_busy():
                    time.sleep(check_interval)
                    continue

                # Rate limit
                now = time.time()
                if (now - self._last_inject_ts) < min_interval:
                    time.sleep(check_interval)
                    continue

                # Session cap
                if self._inject_count >= max_per_session:
                    logger.info("[ProactivityEngine] Session cap reached. Stopping.")
                    break

                # Check user_text.txt — don't inject if user already typed something
                if self._user_txt_occupied():
                    time.sleep(check_interval)
                    continue

                # Score recent events
                res = self._find_significant_event(threshold)
                if res:
                    ev_id, trigger_text = res
                    self._inject(trigger_text)
                    self._triggered_event_ids.add(ev_id)
                    self._last_inject_ts = time.time()
                    self._inject_count  += 1

            except Exception as e:
                logger.debug(f"[ProactivityEngine] Monitor error: {e}")

            time.sleep(check_interval)

    def _pipeline_is_busy(self) -> bool:
        """Return True if the pipeline is currently thinking/speaking/processing."""
        busy_states = {"thinking", "speaking", "generating_tts", "applying_rvc",
                       "transcribing", "processing", "recording"}
        try:
            if not os.path.exists(self._status_txt):
                return False
            with open(self._status_txt, "r", encoding="utf-8") as f:
                status = f.read().strip().lower()
            return status in busy_states
        except Exception:
            return False

    def _user_txt_occupied(self) -> bool:
        """Return True if user_text.txt already has content waiting to be processed."""
        try:
            if not os.path.exists(self._user_txt):
                return False
            with open(self._user_txt, "r", encoding="utf-8") as f:
                return bool(f.read().strip())
        except Exception:
            return False

    def _find_significant_event(self, threshold: float) -> Optional[tuple[str, str]]:
        """
        Scan recent perception events for one that exceeds the threshold.
        Returns (event_id, formatted trigger string) or None if nothing significant found.
        """
        try:
            from perception.fusion_engine import get_global_engine
            engine  = get_global_engine()
            # Look at events in the last 60 seconds only
            recent  = engine.get_recent_events(max_age_seconds=60)
            if not recent:
                return None

            # Find highest-importance event not yet acted on
            best_importance = 0.0
            best_event      = None
            for ev in reversed(recent):  # newest first
                ev_id = ev.get("id")
                if ev_id in self._triggered_event_ids:
                    continue
                imp = ev.get("importance", 0.0)
                if imp > best_importance and imp >= threshold:
                    # Skip "user_action" and "speech" events
                    if ev.get("source") not in ("user_action", "speech"):
                        best_importance = imp
                        best_event      = ev

            if best_event is None:
                return None

            semantic = best_event.get("semantic", "")
            source   = best_event.get("source", "")
            # Build a natural trigger prompt for Vivy
            triggers = {
                "screen": f"[Vivy notices the screen] {semantic}",
                "audio":  f"[Vivy hears something] {semantic}",
                "system": f"[System notice] {semantic}",
            }
            trigger_text = triggers.get(source, f"[Vivy observes] {semantic}")
            return best_event["id"], trigger_text

        except Exception as e:
            logger.debug(f"[ProactivityEngine] Event scan failed: {e}")
            return None

    def _inject(self, trigger_text: str):
        """Write a proactive trigger to shared/user_text.txt."""
        try:
            os.makedirs(self._shared_dir, exist_ok=True)

            # Mark as proactive source
            with open(self._source_txt, "w", encoding="utf-8") as f:
                f.write("proactive")

            # Write trigger
            payload = f"{PROACTIVE_PREFIX} {trigger_text}"
            with open(self._user_txt, "w", encoding="utf-8") as f:
                f.write(payload)

            logger.info(f"[ProactivityEngine] Injected proactive trigger: {trigger_text[:80]}...")
        except Exception as e:
            logger.warning(f"[ProactivityEngine] Inject failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────────────────────────────────────
_global_engine: Optional[ProactivityEngine] = None
_global_lock = threading.Lock()


def get_global_engine() -> ProactivityEngine:
    """Return (or lazily create) the process-wide ProactivityEngine."""
    global _global_engine
    if _global_engine is None:
        with _global_lock:
            if _global_engine is None:
                _global_engine = ProactivityEngine()
    return _global_engine


def start_if_enabled() -> bool:
    """
    Convenience function called from run_vivy.py.
    Starts the proactivity engine only if config enables it.
    Always safe to call.
    """
    try:
        return get_global_engine().start()
    except Exception as e:
        logger.warning(f"[ProactivityEngine] start_if_enabled() failed: {e}")
        return False
