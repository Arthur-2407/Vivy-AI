"""
Vivy Animation Planner
======================
Maps Vivy's emotion labels to Mate Engine animation trigger names and
forwards them to the Unity avatar via avatar_bridge.push_animation().

Architecture:
    run_vivy.py → detect_emotion() → VivyAnimationPlanner.on_emotion()
    → avatar_bridge.push_animation() → WebSocket → VivyWebSocketClient
    → Animator.SetTrigger() (guarded by HasParameter check in Unity)

Design rules:
    - Zero hardcoding. All emotion→animation maps are in animation_config.json.
    - Modular: new emotions, new triggers — edit JSON only.
    - Stateful: suppresses redundant triggers (no re-firing the same animation).
    - Thread-safe: on_emotion() may be called from any thread.
    - All push_animation() calls are forwarded via the bridge's thread-safe
      _schedule_broadcast() — no direct socket access.
"""

import os
import json
import random
import threading
import time


# ──────────────────────────────────────────────────────────────────────────────
# Config loader
# ──────────────────────────────────────────────────────────────────────────────
_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_BASE_DIR, "animation_config.json")


def _load_config() -> dict:
    """Load animation_config.json.  Returns default config on failure."""
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[AnimPlanner] animation_config.json not found at {_CONFIG_PATH}. Using defaults.")
    except json.JSONDecodeError as e:
        print(f"[AnimPlanner] animation_config.json is malformed: {e}. Using defaults.")
    return _default_config()


def _default_config() -> dict:
    """
    Fallback modular configuration.
    """
    return {
        "emotion_layers": {
            "joy": {
                "Base Layer": ["IdleHappy", "IdleCheer"],
                "Face Layer": ["SmileBig"],
                "Gesture Layer": [],
                "Procedural Layer": []
            },
            "sadness": {
                "Base Layer": ["IdleSad"],
                "Face Layer": ["Frown"],
                "Gesture Layer": [],
                "Procedural Layer": []
            },
            "anger": {
                "Base Layer": ["IdleAngry"],
                "Face Layer": ["AngryFace"],
                "Gesture Layer": [],
                "Procedural Layer": []
            },
            "surprise": {
                "Base Layer": ["IdleSurprise"],
                "Face Layer": ["WideEyes"],
                "Gesture Layer": [],
                "Procedural Layer": []
            },
            "fear": {
                "Base Layer": [], "Face Layer": [], "Gesture Layer": [], "Procedural Layer": []
            },
            "disgust": {
                "Base Layer": [], "Face Layer": [], "Gesture Layer": [], "Procedural Layer": []
            },
            "neutral": {
                "Base Layer": [], "Face Layer": [], "Gesture Layer": [], "Procedural Layer": []
            }
        },
        "cooldown_seconds": {
            "Base Layer": 3.0,
            "Face Layer": 1.0,
            "Gesture Layer": 2.0,
            "Procedural Layer": 0.5
        },
        "enabled": True
    }


# ──────────────────────────────────────────────────────────────────────────────
import uuid
from contracts.animation_request import AnimationRequest
from logging_framework.vivy_logger import get_logger
from config.config_manager import get_config_manager

logger = get_logger("AnimationPlanner")

# ──────────────────────────────────────────────────────────────────────────────
# VivyAnimationPlanner
# ──────────────────────────────────────────────────────────────────────────────
class VivyAnimationPlanner:
    """
    Stateful emotion → animation trigger planner (v1.0.0).
    Per Phase 2 & Phase 7 of the Master Hyperprompt.

    Maps emotion labels & internal states to AnimationRequest data contracts.
    """

    def __init__(self, bridge=None):
        self._bridge        = bridge
        self._config        = _load_config()
        self._last_emotion  = ""
        self._last_triggers = {}
        self._last_sent_at  = {}
        self._lock          = threading.Lock()

    def reload_config(self):
        """Hot-reload animation_config.json without restarting."""
        with self._lock:
            self._config = _load_config()
        logger.info("Config reloaded.")

    def on_emotion(self, emotion_label: str, circadian_energy: float = 0.7, vocal_style: str = None) -> AnimationRequest:
        """
        Called after detect_emotion() produces a new label.
        Chooses appropriate modular animation triggers per layer, constructs 
        AnimationRequest contracts, and sends them to Unity concurrently.
        """
        if not emotion_label:
            return None

        emotion = emotion_label.lower().strip()
        if circadian_energy < 0.20 and emotion != "sleeping":
            logger.info(f"Suppressing animation for emotion '{emotion}': Circadian energy is {circadian_energy:.2f} (< 0.20 sleep threshold).")
            return None

        if vocal_style is None:
            try:
                from voice.voice_manager import get_voice_manager
                vocal_style = get_voice_manager().get_active_voice().get("active_style", "Professional")
            except Exception:
                vocal_style = "Professional"

        dispatched_requests = []

        with self._lock:
            cfg = self._config

            if not cfg.get("enabled", True):
                return None

            now = time.time()
            emotion_layers = cfg.get("emotion_layers", {})
            layer_map = emotion_layers.get(emotion, {})
            cooldown_config = cfg.get("cooldown_seconds", {})

            if not layer_map:
                self._last_emotion = emotion
                return None

            for layer_name, triggers in layer_map.items():
                if not triggers:
                    continue

                cooldown = float(cooldown_config.get(layer_name, 3.0))
                last_sent = self._last_sent_at.get(layer_name, 0.0)

                # Skip this layer if the overall emotion hasn't changed AND it's on cooldown
                if emotion == self._last_emotion and (now - last_sent) < cooldown:
                    continue

                if len(triggers) > 1 and circadian_energy < 0.4:
                    selectable = triggers[:max(1, len(triggers)//2)]
                else:
                    selectable = triggers

                trigger = random.choice(selectable)

                # Prevent re-triggering the exact same clip on the same layer rapidly
                if trigger == self._last_triggers.get(layer_name) and (now - last_sent) < cooldown:
                    continue

                self._last_triggers[layer_name] = trigger
                self._last_sent_at[layer_name] = now

                transition_time = 0.5 if vocal_style in ("Soft", "Calm") else 0.3
                anim_req = AnimationRequest(
                    request_id=str(uuid.uuid4()),
                    category="emotion",
                    clip_or_procedural_id=trigger,
                    target_layers=[layer_name],
                    blend_weight=1.0,
                    transition_duration=transition_time,
                    priority=1,
                    source_module="VivyAnimationPlanner",
                    parameters={"emotion": emotion, "circadian_energy": circadian_energy, "vocal_style": vocal_style}
                )
                
                self._dispatch(trigger, anim_req)
                dispatched_requests.append(anim_req)

            self._last_emotion = emotion

        # Return the first request for backward compatibility, or None
        return dispatched_requests[0] if dispatched_requests else None

    def _dispatch(self, trigger_name: str, request: AnimationRequest = None):
        """Forward trigger and AnimationRequest to Unity via the bridge or execute Python script."""
        # Check if this is an auto-generated python animation
        auto_anim_script = os.path.join(_BASE_DIR, "auto_animations", f"{trigger_name}.py")
        if os.path.exists(auto_anim_script):
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(f"auto_anim_{trigger_name}", auto_anim_script)
                anim_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(anim_module)
                
                if hasattr(anim_module, "play") and self._bridge is not None:
                    anim_module.play(self._bridge)
                    logger.info(f"→ Executed Python animation script '{trigger_name}' (RequestID: {request.request_id if request else 'N/A'})")
                    return
            except Exception as e:
                logger.error(f"Failed to execute Python animation script '{trigger_name}': {e}")
        
        # Fallback to standard Unity trigger push
        if self._bridge is not None:
            try:
                self._bridge.push_animation(trigger_name)
                logger.info(f"→ push_animation('{trigger_name}') (RequestID: {request.request_id if request else 'N/A'})")
            except Exception as e:
                logger.error(f"Failed to push animation '{trigger_name}': {e}")
        else:
            logger.info(f"(no bridge) Would push_animation('{trigger_name}')")

