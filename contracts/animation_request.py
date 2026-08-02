import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List

@dataclass
class AnimationRequest:
    """
    Standardized AnimationRequest Data Contract (v1.0.0).
    Contains requested animation category, clip identifier or procedural system identifier,
    target layers, blend weight, transition duration, priority, interruption policy, and source module.
    """
    version: str = "1.0.0"
    request_id: str = ""
    timestamp: float = field(default_factory=time.time)
    category: str = "idle"
    clip_or_procedural_id: str = ""
    target_layers: List[str] = field(default_factory=lambda: ["Base Layer"])
    blend_weight: float = 1.0
    transition_duration: float = 0.3
    priority: int = 0  # Higher value = higher priority
    interruption_policy: str = "interrupt_if_higher"  # "allow", "block", "interrupt_if_higher"
    source_module: str = "AnimationPlanner"
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnimationRequest":
        if not data:
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)
