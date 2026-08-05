"""
voice/voice_profiles.py
=======================
Expressive Vocal Style Profiles for Vivy AI.
Allows the exact same cloned RVC voice model to dynamically transition across speaking styles:
  Soft -> Professional -> Cheerful -> Calm -> Energetic
Without requiring any model retraining or extra GPU training passes.
Achieves expressive divergence via targeted acoustic modulation (speech rate, pitch shift, RMS volume curve, and RVC protection ratios).
"""

import threading
from typing import Dict, Any, List, Optional

class VoiceProfileManager:
    """Manages dynamic speaking style modulation profiles for active cloned voices."""

    def __init__(self):
        self._lock = threading.RLock()
        self.active_style = "Professional"
        self.styles: Dict[str, Dict[str, Any]] = {
            "Professional": {
                "label": "Professional",
                "speech_rate": 1.00,
                "pitch_shift": 0,
                "volume_scale": 1.00,
                "rms_mix_rate": 0.25,
                "protect_ratio": 0.33,
                "description": "Clear, articulate, standard pace and balanced acoustic tone."
            },
            "Soft": {
                "label": "Soft",
                "speech_rate": 0.92,
                "pitch_shift": -1,
                "volume_scale": 0.90,
                "rms_mix_rate": 0.15,
                "protect_ratio": 0.45,
                "description": "Gentle, intimate, comforting tone with softened transients and slower pacing."
            },
            "Cheerful": {
                "label": "Cheerful",
                "speech_rate": 1.08,
                "pitch_shift": 1,
                "volume_scale": 1.05,
                "rms_mix_rate": 0.30,
                "protect_ratio": 0.28,
                "description": "Bright, enthusiastic, slightly elevated pitch and brisk pacing."
            },
            "Calm": {
                "label": "Calm",
                "speech_rate": 0.95,
                "pitch_shift": 0,
                "volume_scale": 0.95,
                "rms_mix_rate": 0.20,
                "protect_ratio": 0.38,
                "description": "Relaxed, composed, steady conversational cadence."
            },
            "Energetic": {
                "label": "Energetic",
                "speech_rate": 1.14,
                "pitch_shift": 1,
                "volume_scale": 1.10,
                "rms_mix_rate": 0.35,
                "protect_ratio": 0.25,
                "description": "Dynamic, upbeat, punchy vocal delivery with rapid response pacing."
            }
        }

    def get_style_parameters(self, style_name: Optional[str] = None) -> Dict[str, Any]:
        """Returns acoustic synthesis parameters for the target style (or current active style)."""
        with self._lock:
            s = style_name or self.active_style
            if s not in self.styles:
                s = "Professional"
            return dict(self.styles[s])

    def set_active_style(self, style_name: str) -> bool:
        """Switch active vocal expressive mode in real time."""
        with self._lock:
            for k in self.styles.keys():
                if k.lower() == style_name.strip().lower():
                    self.active_style = k
                    return True
            return False

    def list_styles(self) -> List[str]:
        with self._lock:
            return list(self.styles.keys())

    def resolve_style_from_relationship_and_mood(self, relationship_stage: str, mood: str, user_emotion: str = "") -> str:
        """
        Dynamically selects the optimal expressive style based on Vivy's relationship intimacy
        and active conversation mood without requiring manual intervention.
        """
        with self._lock:
            m_lower = mood.lower()
            u_lower = user_emotion.lower()
            rel_lower = relationship_stage.lower()

            # Comfort and vulnerability prioritization
            if any(w in u_lower for w in ["sad", "vulnerable", "comfort", "grief", "stressed", "anxious"]):
                self.active_style = "Soft"
                return "Soft"

            # Joy, banter, and playfulness
            if any(w in m_lower for w in ["playful", "joyous", "enthusiastic", "celebrate"]):
                if "bonded" in rel_lower or "close friend" in rel_lower:
                    self.active_style = "Energetic"
                    return "Energetic"
                self.active_style = "Cheerful"
                return "Cheerful"

            # Cozy or relaxed circadian phase
            if any(w in m_lower for w in ["cozy", "relaxing", "calm", "sleep", "rest"]):
                self.active_style = "Calm"
                return "Calm"

            # High intimacy defaults to warm companionship styles
            if "deeply bonded" in rel_lower:
                self.active_style = "Soft"
                return "Soft"
            elif "close friend" in rel_lower or "familiar" in rel_lower:
                self.active_style = "Cheerful"
                return "Cheerful"
            else:
                self.active_style = "Professional"
                return "Professional"

# Singleton
_global_profile_mgr: Optional[VoiceProfileManager] = None

def get_voice_profile_manager() -> VoiceProfileManager:
    global _global_profile_mgr
    if _global_profile_mgr is None:
        _global_profile_mgr = VoiceProfileManager()
    return _global_profile_mgr
