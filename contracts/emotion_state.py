import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any

@dataclass
class EmotionState:
    """
    Standardized EmotionState Data Contract (v1.0.0).
    Contains primary emotion, secondary emotions, intensity values,
    valence, arousal, dominance, mood baseline, emotional momentum, and decay rates.
    """
    version: str = "1.0.0"
    timestamp: float = field(default_factory=time.time)
    primary_emotion: str = "neutral"
    secondary_emotions: Dict[str, float] = field(default_factory=dict)
    intensity_values: Dict[str, float] = field(default_factory=dict)
    valence: float = 0.0      # [-1.0 to +1.0]
    arousal: float = 0.5      # [ 0.0 to  1.0]
    dominance: float = 0.5    # [ 0.0 to  1.0]
    mood_baseline: str = "calmness"
    emotional_momentum: float = 1.0
    decay_rate: float = 7200.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmotionState":
        if not data:
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)
