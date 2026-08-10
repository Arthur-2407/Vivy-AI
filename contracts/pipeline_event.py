import time
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class PipelineEvent:
    response_id: str
    user_turn_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    
    # Context-aware cancellation checking
    def is_cancelled(self, context_manager) -> bool:
        """
        Delegates cancellation check to a central context manager.
        """
        if hasattr(context_manager, "is_cancelled"):
            return context_manager.is_cancelled(self.response_id)
        return False
