import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any

@dataclass
class DiagnosticEvent:
    """
    Standardized DiagnosticEvent Data Contract (v1.0.0).
    Contains module identifier, event type, severity, message,
    timestamp, stack context, and associated metrics.
    """
    version: str = "1.0.0"
    timestamp: float = field(default_factory=time.time)
    module_id: str = "Unknown"
    event_type: str = "general"
    severity: str = "INFO"  # TRACE, DEBUG, INFO, WARN, ERROR, FATAL
    message: str = ""
    stack_context: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiagnosticEvent":
        if not data:
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)
