"""
perception/config_loader.py
============================
Centralised configuration loader for the Vivy AI perception system.

All modules in the perception/ package (and patched existing modules) call
get_config() or the typed-access helper get() instead of reading values
directly from hardcoded strings.

Design rules:
  - Zero side-effects on import (no file I/O at module level).
  - Thread-safe: _config is set once and never mutated.
  - Graceful: returns deep-merged defaults if vivy_config.json is missing or
    partially populated, so the system always starts.
  - Callers never crash because a key is absent from the JSON file.

Usage:
    from perception.config_loader import get_config, get

    cfg = get_config()
    fps = get("screen_perception", "fps", default=2)
"""

import os
import json
import copy
import threading
import logging

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# DEFAULTS — every key that might be read anywhere in the codebase must exist
# here so we never raise KeyError when vivy_config.json is absent or partial.
# ─────────────────────────────────────────────────────────────────────────────
_DEFAULTS: dict = {
    "models": {
        "llm":     "models/Qwen3-8B-Q4_K_M.gguf",
        "whisper": "models/ggml-small.bin",
        "tts":     "tts_models/en/ljspeech/tacotron2-DDC",
        "emotion": "j-hartmann/emotion-english-distilroberta-base",
        "vision":  None,
    },
    "screen_perception": {
        "enabled":                      True,
        "fps":                          30,
        "staleness_seconds":            60,
        "ocr_enabled":                  True,
        "vision_model_enabled":         False,
        "capture_resolution_max_width": 1280,
        "ocr_char_limit":               800,
        "tesseract_paths": [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            r"C:\Users\SATYAJEET\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
        ],
        "adaptive_sampling_enabled":    True,
        "min_sampling_delay_ms":        33,
        "max_sampling_delay_ms":        2000,
        "static_threshold":             0.02,
    },
    "model_routing": {
        "vision_preferred":             "null",
        "speech_preferred":             "whisper_cpp",
        "ocr_preferred":                "pytesseract",
        "audio_analysis_preferred":      "heuristic",
    },
    "privacy": {
        "persistent_recording":         False,
    },
    "audio_perception": {
        "enabled":                   False,
        "system_audio_capture":      False,
        "ambient_analysis_interval": 2.0,
        "speech_ambient_separation": True,
        "min_audio_level_db":        -40.0,
    },
    "multimodal": {
        "event_memory_minutes":    10,
        "event_memory_max_events": 200,
        "context_token_budget":    300,
        "fusion_interval_seconds": 1.0,
        "summary_trigger_count":   50,
        "short_term_memory_seconds": 30,
    },
    "proactivity": {
        "enabled":              False,
        "threshold":            0.8,
        "min_interval_seconds": 30,
        "max_per_session":      20,
    },
    "pipeline": {
        "poll_interval_seconds":    0.25,
        "mic_sample_rate":          16000,
        "mic_frame_ms":             30,
        "mic_base_silence_timeout": 1.2,
        "mic_max_silence_limit":    3.0,
        "whisper_threads":          2,
        "llm_n_ctx":                8192,
        "llm_n_threads":            8,
        "llm_n_batch":              512,
        "llm_n_ubatch":             512,
        "llm_n_gpu_layers":         -1,
        "llm_temperature":          0.75,
        "llm_repeat_penalty":       1.15,
    },
    "server": {
        "host":               "127.0.0.1",
        "web_port":           8080,
        "ws_port":            8765,
        "ws_reconnect_delay": 3.0,
    },
    "paths": {
        "shared_dir":       "shared",
        "recordings_dir":   "recordings",
        "transcripts_dir":  "transcripts",
        "uploads_dir":      "shared/uploads",
        "audio_static_dir": "static/audio",
        "memory_file":      "vivy_memory.json",
        "history_file":     "vivy_history.json",
        "rvc_dir":          "rvc_cpu",
    },
    # ── Circadian Intelligence System defaults ─────────────────────────────
    # Full config lives in circadian_config.json; these are safety fallbacks.
    "circadian": {
        "enabled":      True,
        "sleep_enabled": True,
        "config_path":  "circadian_config.json",
    },
    # ── Perception Model Backends & Hardware Optimization ──────────────────
    # Controls which ML models power face/object/emotion/vision perception,
    # their device assignments (cpu/gpu/auto), confidence thresholds, and
    # model weight file paths.  All keys have safe defaults so the system
    # starts even when model files are absent.
    "perception_models": {
        "face_detection": {
            # Priority order: retinaface → mediapipe → haar → heuristic
            "backend":                   "auto",   # auto | retinaface | mediapipe | haar
            "device":                    "auto",   # auto | cpu | gpu
            "min_confidence":            0.5,
            "retinaface_model_path":     "models/retinaface/det_10g.onnx",
            "retinaface_input_size":     [640, 640],
        },
        "face_embedding": {
            "enabled":                   True,
            "backend":                   "auto",   # auto | insightface | none
            "device":                    "auto",   # auto | cpu | gpu
            "insightface_model_path":    "models/insightface/w600k_r50.onnx",
            "embedding_dim":             512,
            "recognition_threshold":     0.45,
        },
        "object_detection": {
            # Priority order: yolov11 → mobilenet_ssd → mediapipe → heuristic
            "backend":                   "auto",   # auto | yolov11 | mobilenet_ssd | mediapipe
            "device":                    "auto",   # auto | cpu | gpu
            "min_confidence":            0.4,
            "yolov11_model_path":        "models/yolov11/yolo11n-face.pt",
            "yolov11_input_size":        640,
            "max_detections":            10,
        },
        "hand_tracking": {
            "enabled":                   True,
            "backend":                   "mediapipe",  # mediapipe (CPU-only)
            "device":                    "cpu",
            "min_confidence":            0.5,
            "max_hands":                 2,
        },
        "face_emotion": {
            # Priority order: onnx_fer → landmark_heuristics
            "backend":                   "auto",   # auto | onnx_fer | landmark_heuristics
            "device":                    "auto",   # auto | cpu | gpu
            "min_confidence":            0.5,
            "onnx_fer_model_path":       "models/fer/emotion-ferplus-8.onnx",
        },
        "vision_summary": {
            # Priority order: florence2 → heuristic
            "backend":                   "auto",   # auto | florence2 | heuristic
            "device":                    "auto",   # auto | cpu | gpu
            "florence2_model_id":        "microsoft/Florence-2-base",
            "florence2_max_tokens":      77,
            "inference_interval_seconds": 2.0,     # rate-limit GPU VLM calls
        },
        # Global GPU memory budget (MB) — used by hardware_scheduler to
        # prevent OOM when multiple models co-exist on a single GPU.
        "gpu_vram_budget_mb":            6144,     # RTX 5050 = 8 GB, reserve 2 GB for LLM/system
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Internal state
# ─────────────────────────────────────────────────────────────────────────────
_config: dict | None = None
_lock = threading.Lock()

# Resolve config file path relative to the project root (d:\Vivy\)
_THIS_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)  # d:\Vivy
_CONFIG_PATH  = os.path.join(_PROJECT_ROOT, "vivy_config.json")

# ─────────────────────────────────────────────────────────────────────────────
# Test isolation flag — set to True in tests to prevent the shared-folder
# override scan from reading real machine-local .txt files.
# Production code must NEVER set this flag.
# ─────────────────────────────────────────────────────────────────────────────
_DISABLE_SHARED_OVERRIDES: bool = False



# ─────────────────────────────────────────────────────────────────────────────
# Deep merge helper
# ─────────────────────────────────────────────────────────────────────────────
def _deep_merge(base: dict, override: dict) -> dict:
    """Return a new dict with override values merged onto base (recursive)."""
    result = copy.deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def get_config() -> dict:
    """
    Return the merged configuration dict.

    First call: loads vivy_config.json (if present) and merges with defaults.
    Subsequent calls: returns the cached dict (thread-safe, no re-read).

    Returns
    -------
    dict
        Always complete — all keys guaranteed to exist from _DEFAULTS.
    """
    global _config
    if _config is not None:
        return _config

    with _lock:
        # Double-checked locking
        if _config is not None:
            return _config

        file_cfg: dict = {}
        if os.path.exists(_CONFIG_PATH):
            try:
                with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                # Strip comment keys (keys starting with "_comment")
                file_cfg = {k: v for k, v in raw.items() if not k.startswith("_comment")}
                logger.info("[ConfigLoader] Loaded vivy_config.json")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"[ConfigLoader] Could not read vivy_config.json: {e}. Using defaults.")
        else:
            logger.info("[ConfigLoader] vivy_config.json not found. Using built-in defaults.")

        _config = _deep_merge(_DEFAULTS, file_cfg)

        # Apply shared folder config overrides (for hot-reloading)
        # Skipped when _DISABLE_SHARED_OVERRIDES is True (test isolation).
        if not _DISABLE_SHARED_OVERRIDES:
            shared_dir = _config.get("paths", {}).get("shared_dir", "shared")
            shared_path = os.path.join(_PROJECT_ROOT, shared_dir)
            if os.path.exists(shared_path):
                # Audio Perception Override
                if os.path.exists(os.path.join(shared_path, "audio_perception_disable.txt")):
                    _config.setdefault("audio_perception", {})["enabled"] = False
                elif os.path.exists(os.path.join(shared_path, "audio_perception_enable.txt")):
                    _config.setdefault("audio_perception", {})["enabled"] = True

                # Proactivity Override
                if os.path.exists(os.path.join(shared_path, "proactivity_disable.txt")):
                    _config.setdefault("proactivity", {})["enabled"] = False
                elif os.path.exists(os.path.join(shared_path, "proactivity_enable.txt")):
                    _config.setdefault("proactivity", {})["enabled"] = True

                # Screen Perception Override
                if os.path.exists(os.path.join(shared_path, "screen_perception_disable.txt")):
                    _config.setdefault("screen_perception", {})["enabled"] = False
                elif os.path.exists(os.path.join(shared_path, "screen_perception_enable.txt")):
                    _config.setdefault("screen_perception", {})["enabled"] = True

                # Vision Model Override
                if os.path.exists(os.path.join(shared_path, "vision_model_disable.txt")):
                    _config.setdefault("screen_perception", {})["vision_model_enabled"] = False
                elif os.path.exists(os.path.join(shared_path, "vision_model_enable.txt")):
                    _config.setdefault("screen_perception", {})["vision_model_enabled"] = True

                # Adaptive Sampling Override
                if os.path.exists(os.path.join(shared_path, "adaptive_sampling_disable.txt")):
                    _config.setdefault("screen_perception", {})["adaptive_sampling_enabled"] = False
                elif os.path.exists(os.path.join(shared_path, "adaptive_sampling_enable.txt")):
                    _config.setdefault("screen_perception", {})["adaptive_sampling_enabled"] = True


    return _config


def get(section: str, key: str, default=None):
    """
    Typed single-key access helper.

    Parameters
    ----------
    section : str
        Top-level config section, e.g. "screen_perception".
    key : str
        Key within the section, e.g. "fps".
    default : any
        Returned if the section or key is missing (shouldn't happen with
        defaults in place, but provided as safety net).

    Returns
    -------
    The value from config, or ``default``.

    Examples
    --------
    >>> from perception.config_loader import get
    >>> fps = get("screen_perception", "fps", default=2)
    >>> staleness = get("screen_perception", "staleness_seconds", default=60)
    """
    cfg = get_config()
    section_data = cfg.get(section, {})
    if not isinstance(section_data, dict):
        return default
    return section_data.get(key, default)


def get_project_root() -> str:
    """Return the absolute path to the Vivy project root directory."""
    return _PROJECT_ROOT


def get_absolute_path(relative_or_absolute: str) -> str:
    """
    Resolve a path from config to an absolute path.

    If the path is already absolute, return it unchanged.
    If relative, resolve relative to the project root.
    """
    if os.path.isabs(relative_or_absolute):
        return relative_or_absolute
    return os.path.join(_PROJECT_ROOT, relative_or_absolute)


def reload() -> dict:
    """
    Force-reload config from disk (hot-reload support).

    Useful for runtime config changes without restarting the process.
    Returns the newly loaded config.
    """
    global _config
    with _lock:
        _config = None
    return get_config()
