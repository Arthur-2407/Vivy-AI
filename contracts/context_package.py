from dataclasses import dataclass
from typing import Optional

@dataclass
class ContextPackage:
    """Canonical Context Assembly for LLM Pipeline"""
    session_id: str
    user_input: str
    conversation_history: list
    active_memory: dict
    perception_state: Optional[dict]
    system_prompt: str
    
    def to_dict(self):
        return self.__dict__
