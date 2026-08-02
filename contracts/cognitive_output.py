import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any

@dataclass
class CognitiveOutput:
    """
    Standardized CognitiveOutput Data Contract (v1.0.0).
    Contains generated response text, emotional intent, behavioral intent,
    reasoning trace, confidence score, and meta-cognitive evaluation.
    """
    version: str = "1.0.0"
    timestamp: float = field(default_factory=time.time)
    response_text: str = ""
    emotional_intent: str = "neutral"
    behavioral_intent: str = "talk"
    reasoning_trace: str = ""
    confidence_score: float = 1.0
    meta_cognitive_evaluation: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CognitiveOutput":
        if not data:
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)
