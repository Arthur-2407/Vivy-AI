import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List

@dataclass
class AnimationResponse:
    """
    Standardized AnimationResponse Data Contract (v1.0.0).
    Contains resolved clip references, procedural parameters, blend configuration,
    layer assignments, estimated duration, and status.
    """
    version: str = "1.0.0"
    request_id: str = ""
    timestamp: float = field(default_factory=time.time)
    status: str = "queued"  # "queued", "playing", "completed", "interrupted", "failed"
    resolved_clips: List[str] = field(default_factory=list)
    procedural_params: Dict[str, Any] = field(default_factory=dict)
    blend_config: Dict[str, float] = field(default_factory=dict)
    layer_assignments: Dict[str, float] = field(default_factory=dict)
    estimated_duration: float = 0.0
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnimationResponse":
        if not data:
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)
