import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List

@dataclass
class ContextPackage:
    """
    Standardized ContextPackage Data Contract (v1.0.0).
    Contains assembled context window data, conversation history, retrieved memories,
    current emotion state, user profile, environment state, relationship state, and system prompts.
    """
    version: str = "1.0.0"
    timestamp: float = field(default_factory=time.time)
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    retrieved_memories: List[Dict[str, Any]] = field(default_factory=list)
    emotion_state: Dict[str, Any] = field(default_factory=dict)
    user_profile: Dict[str, Any] = field(default_factory=dict)
    environment_state: Dict[str, Any] = field(default_factory=dict)
    relationship_state: Dict[str, Any] = field(default_factory=dict)
    system_prompts: List[str] = field(default_factory=list)
    token_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextPackage":
        if not data:
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)
