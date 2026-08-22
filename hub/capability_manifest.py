"""
Vivy Hub - Capability Manifest
Defines the schema for portable capabilities and execution modes.
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List

class ExecutionMode(Enum):
    LOCAL = "local"
    REMOTE = "remote"
    HYBRID = "hybrid"

class LatencyClass(Enum):
    REALTIME = "realtime"
    INTERACTIVE = "interactive"
    BACKGROUND = "background"
    DEFERRED = "deferred"

@dataclass
class CapabilityManifest:
    """
    Machine-readable manifest for a portable capability.
    Eliminates hardcoded device logic by specifying requirements.
    """
    capability_id: str
    version: str
    provider: str
    execution_modes: List[ExecutionMode]
    latency_class: LatencyClass
    
    # Resource requirements
    requirements: Dict[str, Any] = field(default_factory=dict)
    
    # Data flow schema
    input_schema: str = "any"
    output_schema: str = "any"
    
    # Security and fallbacks
    permissions: List[str] = field(default_factory=list)
    security_level: str = "low"
    dependencies: List[str] = field(default_factory=list)
    fallback_execution_location: str = "primary_host"
