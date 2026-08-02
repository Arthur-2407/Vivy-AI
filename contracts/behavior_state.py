import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List

@dataclass
class BehaviorState:
    """
    Standardized BehaviorState Data Contract (v1.0.0).
    Contains current behavior mode, active behavior stack, priority levels,
    interruption policy, planned behaviors queue, and completion status.
    """
    version: str = "1.0.0"
    timestamp: float = field(default_factory=time.time)
    current_mode: str = "idle"
    active_stack: List[str] = field(default_factory=lambda: ["idle"])
    priority_levels: Dict[str, int] = field(default_factory=dict)
    interruption_policy: str = "interrupt_if_higher"
    planned_queue: List[Dict[str, Any]] = field(default_factory=list)
    completion_status: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BehaviorState":
        if not data:
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)
