import uuid
import threading
from dataclasses import dataclass, field

class CancellationToken:
    """Thread-safe cancellation token for propagating interrupts down the pipeline."""
    def __init__(self):
        self._is_cancelled = False
        self._lock = threading.Lock()
        
    def cancel(self):
        with self._lock:
            self._is_cancelled = True
            
    @property
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._is_cancelled

@dataclass
class ResponseContext:
    """
    Context for a single generated response stream.
    All chunks belonging to this stream carry this context to ensure order and cancellation.
    """
    response_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    cancellation_token: CancellationToken = field(default_factory=CancellationToken)
    
    def cancel(self):
        self.cancellation_token.cancel()
        
    @property
    def is_cancelled(self) -> bool:
        return self.cancellation_token.is_cancelled

@dataclass
class ChunkInfo:
    """
    Metadata for a specific audio chunk in the pipeline.
    """
    context: ResponseContext
    chunk_id: int
    text: str
    wav_path: str = ""
    is_final_chunk: bool = False
