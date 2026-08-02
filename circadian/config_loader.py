"""
circadian/config_loader.py
===========================
Configuration loader for the Vivy AI Circadian Intelligence System.

Mirrors the design of perception/config_loader.py:
  - Zero side-effects on import
  - Thread-safe singleton
  - Deep-merge with built-in defaults so the system always starts
  - Callers use get(section, key, default) for typed access

Usage:
    from circadian.config_loader import get, get_config, get_project_root
    energy = get("phase_modulation", "Evening", default={})
"""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Locate the project root and config file
# ---------------------------------------------------------------------------
_THIS_DIR     = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)           # d:\Vivy
_CONFIG_PATH  = os.path.join(_PROJECT_ROOT, "circadian_config.json")

# ---------------------------------------------------------------------------
# Built-in defaults  (used if circadian_config.json is absent or partial)
# ---------------------------------------------------------------------------
_DEFAULTS: dict = {
    "enabled":      True,
    "sleep_enabled": True,

    "time_blocks": {
        "Morning":       {"start": "06:00", "end": "09:00"},
        "LateMorning":   {"start": "09:00", "end": "12:00"},
        "Afternoon":     {"start": "12:00", "end": "15:00"},
        "LateAfternoon": {"start": "15:00", "end": "18:00"},
        "Evening":       {"start": "18:00", "end": "21:00"},
        "Night":         {"start": "21:00", "end": "00:00"},
        "LateNight":     {"start": "00:00", "end": "03:00"},
        "PreDawn":       {"start": "03:00", "end": "06:00"},
    },

    "phase_modulation": {
        "Morning":       {"tone": "energetic",  "emotion_deltas": {}, "initiative_delta": 0.20,  "energy": 0.85, "voice_speed_delta": 0.08,  "voice_warmth_delta": 0.00, "avatar_energy": 0.90},
        "LateMorning":   {"tone": "engaged",    "emotion_deltas": {}, "initiative_delta": 0.12,  "energy": 0.80, "voice_speed_delta": 0.05,  "voice_warmth_delta": 0.05, "avatar_energy": 0.80},
        "Afternoon":     {"tone": "focused",    "emotion_deltas": {}, "initiative_delta": 0.00,  "energy": 0.70, "voice_speed_delta": 0.00,  "voice_warmth_delta": 0.00, "avatar_energy": 0.70},
        "LateAfternoon": {"tone": "neutral",    "emotion_deltas": {}, "initiative_delta":-0.03,  "energy": 0.72, "voice_speed_delta":-0.02,  "voice_warmth_delta": 0.08, "avatar_energy": 0.70},
        "Evening":       {"tone": "warm",       "emotion_deltas": {}, "initiative_delta":-0.05,  "energy": 0.74, "voice_speed_delta":-0.03,  "voice_warmth_delta": 0.15, "avatar_energy": 0.70},
        "Night":         {"tone": "reflective", "emotion_deltas": {}, "initiative_delta":-0.15,  "energy": 0.45, "voice_speed_delta":-0.08,  "voice_warmth_delta": 0.20, "avatar_energy": 0.40},
        "LateNight":     {"tone": "quiet",      "emotion_deltas": {}, "initiative_delta":-0.25,  "energy": 0.20, "voice_speed_delta":-0.12,  "voice_warmth_delta": 0.10, "avatar_energy": 0.20},
        "PreDawn":       {"tone": "minimal",    "emotion_deltas": {}, "initiative_delta":-0.30,  "energy": 0.10, "voice_speed_delta":-0.15,  "voice_warmth_delta": 0.05, "avatar_energy": 0.10},
    },

    "energy_curve": {
        "interpolation":             "cosine",
        "transition_window_minutes": 30,
    },

    "sleep": {
        "active_phases":       ["LateNight", "PreDawn"],
        "reduce_initiative":   True,
        "reduce_proactivity":  True,
    },

    "hardware_policy": {
        "cpu_workloads":         ["dialogue", "memory", "circadian", "emotion", "scheduling", "text", "ocr"],
        "gpu_workloads":         ["avatar", "vision", "lip_sync", "image_gen", "large_model"],
        "cpu_threshold_percent": 80,
        "gpu_threshold_percent": 80,
        "hysteresis_seconds":    10,
        "default_llm_device":    "gpu",
    },
}

# ---------------------------------------------------------------------------
# Singleton state
# ---------------------------------------------------------------------------
_config: Optional[dict] = None
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Deep-merge helper
# ---------------------------------------------------------------------------
def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = copy.deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_config() -> dict:
    """
    Return the merged circadian configuration dict.
    Thread-safe singleton — loads once, caches forever.
    Always returns a complete config (all keys guaranteed from _DEFAULTS).
    """
    global _config
    if _config is not None:
        return _config

    with _lock:
        if _config is not None:
            return _config

        file_cfg: dict = {}
        # Candidate paths in priority order
        candidate_paths = [
            os.path.join(_PROJECT_ROOT, "config", "circadian.yaml"),
            os.path.join(_PROJECT_ROOT, "config", "circadian.yml"),
            os.path.join(_PROJECT_ROOT, "config", "circadian.json"),
            os.path.join(_PROJECT_ROOT, "circadian_config.json"),
        ]

        loaded_path = None
        for path in candidate_paths:
            if os.path.exists(path):
                try:
                    if path.endswith((".yaml", ".yml")):
                        try:
                            import yaml
                            with open(path, "r", encoding="utf-8") as f:
                                raw = yaml.safe_load(f) or {}
                            loaded_path = path
                        except ImportError:
                            logger.warning(f"[CircadianConfig] PyYAML not installed. Skipping YAML config: {path}")
                            continue
                    else:
                        with open(path, "r", encoding="utf-8") as f:
                            raw = json.load(f)
                        loaded_path = path

                    # Strip comment keys
                    file_cfg = {k: v for k, v in raw.items() if not str(k).startswith("_comment")}
                    logger.info(f"[CircadianConfig] Loaded config from {loaded_path}")
                    break
                except Exception as e:
                    logger.warning(f"[CircadianConfig] Could not read {path}: {e}")

        if not loaded_path:
            logger.info("[CircadianConfig] No external config file found. Using built-in defaults.")

        _config = _deep_merge(_DEFAULTS, file_cfg)

    return _config


def get(section: str, key: str, default: Any = None) -> Any:
    """
    Typed single-key accessor for a top-level section.

    Examples
    --------
    >>> from circadian.config_loader import get
    >>> tone = get("phase_modulation", "Evening", default={}).get("tone", "neutral")
    """
    cfg = get_config()
    section_data = cfg.get(section, {})
    if not isinstance(section_data, dict):
        return default
    return section_data.get(key, default)


def get_top(key: str, default: Any = None) -> Any:
    """Access a top-level key directly (e.g. 'enabled', 'sleep_enabled')."""
    return get_config().get(key, default)


def get_project_root() -> str:
    """Return the absolute path to the Vivy project root (d:/Vivy)."""
    return _PROJECT_ROOT


def reload() -> dict:
    """Force-reload config from disk. Returns newly loaded config."""
    global _config
    with _lock:
        _config = None
    return get_config()
