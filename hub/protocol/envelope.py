"""
Vivy Hub - Canonical Protocol Envelope
Defines the single canonical envelope for all cross-device communication.
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional
import uuid
import time
import json

@dataclass
class VivyMessage:
    protocol: str = "vivy"
    version: str = "1"
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    request_id: Optional[str] = None
    device_id: str = ""
    session_id: Optional[str] = None
    type: str = "unknown"
    timestamp: float = field(default_factory=time.time)
    
    # Subsystem specific headers
    capability: Optional[str] = None
    
    # Payload
    payload: Dict[str, Any] = field(default_factory=dict)
    
    # Security & Provenance
    security: Dict[str, Any] = field(default_factory=dict)
    execution_node: Optional[str] = None
    lease_id: Optional[str] = None
    execution_mode: Optional[str] = None
    sequence: int = 0
    status: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self))
        
    @classmethod
    def from_json(cls, json_str: str) -> "VivyMessage":
        data = json.loads(json_str)
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in field_names}
        return cls(**filtered_data)
