"""
circadian/circadian_engine.py
==============================
Vivy AI — Circadian Intelligence Engine

RESPONSIBILITY
--------------
Reads wall-clock time, determines the active time phase, and produces a
CircadianState object containing soft modulation values that influence:

  • emotion_vector  (additive deltas, never overwrites)
  • dialogue tone   (hint injected into LLM prompt)
  • voice speech_rate
  • avatar energy level
  • sleep mode flag
  • hardware routing hint

DESIGN RULES
------------
  - NEVER replaces existing calculations — only adds/multiplies softly.
  - Zero side-effects on import.
  - Thread-safe singleton cached per-second (cheap to call in hot loop).
  - All values come from circadian_config.json — zero hardcoding.
  - Smooth cosine/sine interpolation at phase boundaries (no step jumps).
  - Graceful: if config is missing, defaults keep Vivy running normally.

INTEGRATION POINTS
------------------
  - conversation.py:generate_reply_internal()  — emotion delta + tone hint
  - conversation.py:build()                    — prompt fragment injection
  - run_vivy.py                               — voice speed + state file write
  - avatar_bridge.py                          — circadian_state.json polling
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Shared IPC directory (written for avatar_bridge and web dashboard)
_THIS_DIR     = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
_SHARED_DIR   = os.path.join(_PROJECT_ROOT, "shared")
_STATE_PATH   = os.path.join(_SHARED_DIR, "circadian_state.json")


# ─────────────────────────────────────────────────────────────────────────────
# CircadianState — immutable value object produced each computation cycle
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CircadianState:
    """
    All circadian modulation values for the current moment.
    All numeric fields are pre-interpolated (smooth, no step jumps).
    """
    enabled:           bool                    = True
    phase_name:        str                     = "Afternoon"
    next_phase_name:   str                     = "LateAfternoon"
    phase_progress:    float                   = 0.0   # 0.0=phase start, 1.0=phase end
    energy:            float                   = 0.70  # 0.0–1.0
    initiative_delta:  float                   = 0.00  # additive to initiative score
    emotion_deltas:    Dict[str, float]        = field(default_factory=dict)
    tone_label:        str                     = "neutral"
    voice_speed_delta: float                   = 0.00  # additive to speech_rate (e.g. +0.08)
    voice_warmth_delta:float                   = 0.00  # informational; used in prompt
    avatar_energy:     float                   = 0.70  # 0.0–1.0
    sleep_mode:        bool                    = False
    hardware_hint:     str                     = "gpu" # "cpu" | "gpu" | "hybrid"
    timestamp:         float                   = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────
def _time_to_minutes(t_str: str) -> int:
    """Convert 'HH:MM' to total minutes since midnight."""
    h, m = map(int, t_str.split(":"))
    return h * 60 + m


def _current_minutes() -> int:
    """Current local time as minutes since midnight."""
    now = datetime.now()
    return now.hour * 60 + now.minute


def _cosine_blend(t: float) -> float:
    """
    Cosine interpolation: maps t in [0,1] to a smooth value in [0,1].
    At t=0 → 0.0, at t=1 → 1.0, smooth S-curve in between.
    """
    return (1.0 - math.cos(math.pi * t)) / 2.0


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


# ─────────────────────────────────────────────────────────────────────────────
# CircadianEngine — core computation engine
# ─────────────────────────────────────────────────────────────────────────────
class CircadianEngine:
    """
    Singleton circadian computation engine.

    Public API:
        engine = CircadianEngine()
        state  = engine.get_state()
        frag   = engine.get_modulation_prompt_fragment()
    """

    # Phase ordering for interpolation (must be cyclic)
    _PHASE_ORDER = [
        "Morning", "LateMorning", "Afternoon", "LateAfternoon",
        "Evening", "Night", "LateNight", "PreDawn"
    ]

    def __init__(self):
        self._lock          = threading.Lock()
        self._cached_state: Optional[CircadianState] = None
        self._last_compute: float = 0.0
        self._cache_ttl:    float = 1.0   # recompute at most once per second
        self._config:       dict  = {}
        self._config_loaded: bool = False

    # ── Config ───────────────────────────────────────────────────────────────

    def _ensure_config(self):
        """Lazily load config (first call only). Thread-safe."""
        if self._config_loaded:
            return
        try:
            from circadian.config_loader import get_config
            self._config = get_config()
        except Exception as e:
            logger.warning(f"[CircadianEngine] Config load failed, using hardcoded defaults: {e}")
            self._config = {}
        self._config_loaded = True

    def _get_phase_modulation(self, phase_name: str) -> dict:
        """Return the modulation dict for a named phase, with safe fallback."""
        phases = self._config.get("phase_modulation", {})
        return phases.get(phase_name, {
            "tone": "neutral",
            "emotion_deltas": {},
            "initiative_delta": 0.0,
            "energy": 0.70,
            "voice_speed_delta": 0.0,
            "voice_warmth_delta": 0.0,
            "avatar_energy": 0.70,
        })

    # ── Phase Detection ───────────────────────────────────────────────────────

    def _detect_phase(self, current_minutes: int) -> tuple[str, str, float]:
        """
        Determine (current_phase, next_phase, phase_progress 0-1).

        phase_progress = how far through the current phase we are.
        Handles midnight wrap-around correctly.
        """
        self._ensure_config()
        time_blocks: dict = self._config.get("time_blocks", {})
        transition_win: int = int(
            self._config.get("energy_curve", {}).get("transition_window_minutes", 30)
        )

        # Build ordered list of (name, start_min, end_min)
        phases_parsed: list[tuple[str, int, int]] = []
        for name in self._PHASE_ORDER:
            if name not in time_blocks:
                continue
            blk = time_blocks[name]
            s = _time_to_minutes(blk["start"])
            e = _time_to_minutes(blk["end"])
            # Normalize end: if end < start (e.g. Night 21:00–00:00) add 1440
            if e <= s:
                e += 1440
            phases_parsed.append((name, s, e))

        # Expand times to handle wrap-around (e.g. LateNight 00:00 = 1440)
        cur = current_minutes

        matched_name  = "Afternoon"   # safe fallback
        matched_start = 0
        matched_end   = 1440

        for name, s, e in phases_parsed:
            # Shift current minutes forward if phase wraps midnight
            c = cur if cur >= s else cur + 1440
            if s <= c < e:
                matched_name  = name
                matched_start = s
                matched_end   = e
                break

        # Compute next phase (circular)
        idx = self._PHASE_ORDER.index(matched_name) if matched_name in self._PHASE_ORDER else 0
        next_name = self._PHASE_ORDER[(idx + 1) % len(self._PHASE_ORDER)]

        # Progress within current phase [0.0 – 1.0]
        phase_duration = matched_end - matched_start
        if phase_duration <= 0:
            phase_duration = 180
        c = cur if cur >= matched_start else cur + 1440
        raw_progress = (c - matched_start) / phase_duration
        progress = max(0.0, min(1.0, raw_progress))

        return matched_name, next_name, progress

    # ── Smooth Interpolation ─────────────────────────────────────────────────

    def _interpolate_numeric(
        self, key: str, current_mod: dict, next_mod: dict, blend: float
    ) -> float:
        a = float(current_mod.get(key, 0.0))
        b = float(next_mod.get(key, 0.0))
        return _lerp(a, b, blend)

    def _interpolate_emotion_deltas(
        self, current_mod: dict, next_mod: dict, blend: float
    ) -> Dict[str, float]:
        all_keys = set(current_mod.get("emotion_deltas", {}).keys()) | \
                   set(next_mod.get("emotion_deltas", {}).keys())
        result = {}
        for k in all_keys:
            a = float(current_mod.get("emotion_deltas", {}).get(k, 0.0))
            b = float(next_mod.get("emotion_deltas", {}).get(k, 0.0))
            result[k] = _lerp(a, b, blend)
        return result

    def _pick_tone(self, current_mod: dict, next_mod: dict, blend: float) -> str:
        """Pick tone label: use current unless we're >70% into the transition window."""
        return next_mod.get("tone", "neutral") if blend > 0.70 else current_mod.get("tone", "neutral")

    # ── Hardware hint (lightweight) ───────────────────────────────────────────

    def _compute_hardware_hint(self) -> str:
        """
        Determine hardware routing hint based on config + optional psutil.
        Returns "cpu" | "gpu" | "hybrid".
        Falls back to configured default if psutil unavailable.
        """
        hw_policy = self._config.get("hardware_policy", {})
        default_device = hw_policy.get("default_llm_device", "gpu")
        cpu_thresh = float(hw_policy.get("cpu_threshold_percent", 80))
        gpu_thresh = float(hw_policy.get("gpu_threshold_percent", 80))

        try:
            import psutil
            cpu_pct = psutil.cpu_percent(interval=None)
            # Try GPU via nvidia-smi subprocess (optional)
            gpu_pct = 0.0
            try:
                import subprocess
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=1.0
                )
                if result.returncode == 0:
                    vals = [float(x.strip()) for x in result.stdout.strip().split("\n") if x.strip()]
                    if vals:
                        gpu_pct = max(vals)
            except Exception as _err:
                print(f"[circadian_engine.py] Silenced exception: {_err}")  # nvidia-smi not available — use 0

            cpu_high = cpu_pct >= cpu_thresh
            gpu_high = gpu_pct >= gpu_thresh

            if cpu_high and gpu_high:
                return "hybrid"
            elif cpu_high:
                return "cpu"
            else:
                return default_device

        except ImportError:
            # psutil not installed — use configured default
            return default_device
        except Exception as e:
            logger.debug(f"[CircadianEngine] Hardware hint error (non-fatal): {e}")
            return default_device

    # ── Sleep mode ────────────────────────────────────────────────────────────

    def _is_sleep_mode(self, phase_name: str) -> bool:
        sleep_cfg = self._config.get("sleep", {})
        if not self._config.get("sleep_enabled", True):
            return False
        active_phases = sleep_cfg.get("active_phases", ["LateNight", "PreDawn"])
        return phase_name in active_phases

    # ── Core computation ─────────────────────────────────────────────────────

    def _compute(self) -> CircadianState:
        """
        Compute the CircadianState for the current moment.
        Uses cosine interpolation at phase boundaries for smooth transitions.
        """
        self._ensure_config()

        if not self._config.get("enabled", True):
            return CircadianState(enabled=False, timestamp=time.time())

        now_min    = _current_minutes()
        phase_name, next_phase_name, progress = self._detect_phase(now_min)

        current_mod = self._get_phase_modulation(phase_name)
        next_mod    = self._get_phase_modulation(next_phase_name)

        # Determine transition blend based on energy_curve config
        interp_mode = self._config.get("energy_curve", {}).get("interpolation", "cosine")
        transition_win = float(
            self._config.get("energy_curve", {}).get("transition_window_minutes", 30)
        )

        # blend = how much of next phase leaks in (0=pure current, 1=pure next)
        # Only apply blending in the LAST transition_window_minutes of the phase
        # To compute phase duration, check its entry in time_blocks
        time_blocks = self._config.get("time_blocks", {})
        phase_dur_min = 180  # fallback
        if phase_name in time_blocks:
            blk = time_blocks[phase_name]
            s = _time_to_minutes(blk["start"])
            e = _time_to_minutes(blk["end"])
            if e <= s:
                e += 1440
            phase_dur_min = max(1, e - s)

        # How far (in minutes) from the end of this phase
        minutes_to_end = phase_dur_min * (1.0 - progress)
        blend = 0.0
        if minutes_to_end <= transition_win:
            raw_blend = 1.0 - (minutes_to_end / transition_win)
            blend = _cosine_blend(raw_blend) if interp_mode == "cosine" else raw_blend

        # Interpolate all numeric fields
        energy            = self._interpolate_numeric("energy",            current_mod, next_mod, blend)
        initiative_delta  = self._interpolate_numeric("initiative_delta",  current_mod, next_mod, blend)
        voice_speed_delta = self._interpolate_numeric("voice_speed_delta", current_mod, next_mod, blend)
        voice_warmth_delta= self._interpolate_numeric("voice_warmth_delta",current_mod, next_mod, blend)
        avatar_energy     = self._interpolate_numeric("avatar_energy",     current_mod, next_mod, blend)
        emotion_deltas    = self._interpolate_emotion_deltas(current_mod, next_mod, blend)
        tone_label        = self._pick_tone(current_mod, next_mod, blend)
        sleep_mode        = self._is_sleep_mode(phase_name)
        hardware_hint     = self._compute_hardware_hint()

        state = CircadianState(
            enabled            = True,
            phase_name         = phase_name,
            next_phase_name    = next_phase_name,
            phase_progress     = progress,
            energy             = round(energy, 4),
            initiative_delta   = round(initiative_delta, 4),
            emotion_deltas     = {k: round(v, 4) for k, v in emotion_deltas.items()},
            tone_label         = tone_label,
            voice_speed_delta  = round(voice_speed_delta, 4),
            voice_warmth_delta = round(voice_warmth_delta, 4),
            avatar_energy      = round(avatar_energy, 4),
            sleep_mode         = sleep_mode,
            hardware_hint      = hardware_hint,
            timestamp          = time.time(),
        )

        logger.info(
            f"[Circadian] Phase: {phase_name} | Energy: {energy:.2f} | "
            f"Initiative: {initiative_delta:+.2f} | Voice Warmth: {voice_warmth_delta:+.2f} | "
            f"Hardware: {hardware_hint} | Sleep: {sleep_mode}"
        )

        return state

    # ── State file writer ─────────────────────────────────────────────────────

    def _write_state_file(self, state: CircadianState):
        """
        Write circadian_state.json to shared/ for avatar_bridge and dashboard.
        Non-blocking: uses atomic write with temp file to prevent partial reads.
        """
        try:
            os.makedirs(_SHARED_DIR, exist_ok=True)
            payload = {
                "phase":          state.phase_name,
                "next_phase":     state.next_phase_name,
                "phase_progress": state.phase_progress,
                "energy":         state.energy,
                "initiative":     state.initiative_delta,
                "emotion_deltas": state.emotion_deltas,
                "tone":           state.tone_label,
                "voice_speed_delta":  state.voice_speed_delta,
                "voice_warmth_delta": state.voice_warmth_delta,
                "avatar_energy":  state.avatar_energy,
                "sleep_mode":     state.sleep_mode,
                "hardware_hint":  state.hardware_hint,
                "timestamp":      state.timestamp,
            }
            tmp = _STATE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, _STATE_PATH)
        except Exception as e:
            logger.debug(f"[CircadianEngine] State file write failed (non-fatal): {e}")

    # ── Public API ────────────────────────────────────────────────────────────

    def get_state(self) -> CircadianState:
        """
        Return the current CircadianState (cached per TTL, thread-safe).
        This is the primary API — safe to call from any thread in the pipeline.
        """
        now = time.time()
        with self._lock:
            if self._cached_state is not None and (now - self._last_compute) < self._cache_ttl:
                return self._cached_state

        # Compute outside the lock to avoid blocking callers during config load
        try:
            state = self._compute()
        except Exception as e:
            logger.error(f"[CircadianEngine] Computation failed (non-fatal): {e}")
            state = CircadianState(enabled=False, timestamp=time.time())

        with self._lock:
            self._cached_state = state
            self._last_compute = now

        # Write state file in a background thread every ~60 seconds
        # (We check if timestamp drifted enough to avoid spamming disk)
        try:
            last_write = getattr(self, "_last_file_write", 0.0)
            if now - last_write >= 60.0:
                self._last_file_write = now
                import threading as _t
                _t.Thread(target=self._write_state_file, args=(state,), daemon=True).start()
        except Exception as _err:
            print(f"[circadian_engine.py] Silenced exception: {_err}")

        return state

    def get_modulation_prompt_fragment(self) -> str:
        """
        Return a short natural-language hint for the LLM system prompt.
        This is injected softly — it does not override persona or instructions.
        Returns empty string if circadian is disabled or state is minimal.
        """
        try:
            state = self.get_state()
            if not state.enabled:
                return ""

            # Tone → natural prose hint
            tone_prose = {
                "energetic":  "Right now you feel bright, energetic, and eager to engage.",
                "engaged":    "You feel alert and engaged, naturally attentive.",
                "focused":    "You feel calm, focused, and quietly efficient.",
                "neutral":    "",
                "warm":       "You feel warm and unhurried, naturally more affectionate.",
                "reflective": "You feel reflective and calm - more gentle and thoughtful.",
                "quiet":      "You feel soft and quiet, naturally speaking gently.",
                "minimal":    "You feel very still and calm - speaking only when it truly matters.",
            }.get(state.tone_label, "")


            parts = []
            if tone_prose:
                parts.append(tone_prose)
            if state.sleep_mode:
                parts.append("It is very late — keep responses especially brief and gentle.")

            if not parts:
                return ""

            frag = "[CIRCADIAN HINT] " + " ".join(parts)
            return frag

        except Exception as e:
            logger.debug(f"[CircadianEngine] Prompt fragment error (non-fatal): {e}")
            return ""


# ─────────────────────────────────────────────────────────────────────────────
# Process-wide singleton
# ─────────────────────────────────────────────────────────────────────────────
_global_engine: Optional[CircadianEngine] = None
_global_engine_lock = threading.Lock()


def _get_engine() -> CircadianEngine:
    """Return (or lazily create) the process-wide CircadianEngine."""
    global _global_engine
    if _global_engine is None:
        with _global_engine_lock:
            if _global_engine is None:
                _global_engine = CircadianEngine()
    return _global_engine


def get_state() -> CircadianState:
    """
    Module-level convenience function.
    Returns the current CircadianState from the singleton engine.

    Usage:
        from circadian.circadian_engine import get_state
        state = get_state()
        print(state.phase_name, state.energy)
    """
    return _get_engine().get_state()


def get_modulation_prompt_fragment() -> str:
    """
    Module-level convenience function.
    Returns the LLM prompt fragment for the current circadian state.

    Usage:
        from circadian.circadian_engine import get_modulation_prompt_fragment
        frag = get_modulation_prompt_fragment()
    """
    return _get_engine().get_modulation_prompt_fragment()


# ─────────────────────────────────────────────────────────────────────────────
# Standalone test / smoke check
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import os as _os
    # Allow running directly from within the circadian/ directory
    _proj_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    if _proj_root not in sys.path:
        sys.path.insert(0, _proj_root)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    print("=" * 60)
    print("  Vivy AI - Circadian Intelligence Engine  (Standalone Test)")
    print("=" * 60)
    state = get_state()
    print(f"\n  Current Time:  {datetime.now().strftime('%H:%M')}")
    print(f"  Phase:         {state.phase_name}")
    print(f"  Next Phase:    {state.next_phase_name}")
    print(f"  Progress:      {state.phase_progress * 100:.1f}%")
    print(f"  Energy:        {state.energy:.2f}")
    print(f"  Initiative d:  {state.initiative_delta:+.2f}")
    print(f"  Tone:          {state.tone_label}")
    print(f"  Voice Speed d: {state.voice_speed_delta:+.3f}")
    print(f"  Voice Warmth d:{state.voice_warmth_delta:+.3f}")
    print(f"  Avatar Energy: {state.avatar_energy:.2f}")
    print(f"  Sleep Mode:    {state.sleep_mode}")
    print(f"  Hardware Hint: {state.hardware_hint}")
    print(f"\n  Emotion Deltas:")
    for k, v in state.emotion_deltas.items():
        print(f"    {k:15s}: {v:+.3f}")
    print(f"\n  Prompt Fragment:")
    frag = get_modulation_prompt_fragment()
    print(f"  {frag if frag else '(empty - no hint for this phase)'}")
    print()

