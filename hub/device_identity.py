"""
Vivy Hub - Device Identity & Profiles
Defines trust levels, device roles, and the dynamic hardware profile for ecosystem nodes.
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List

class TrustLevel(Enum):
    UNSEEN = "UNSEEN"
    DISCOVERED = "DISCOVERED"
    PAIRED = "PAIRED"
    AUTHENTICATED = "AUTHENTICATED"
    TRUSTED = "TRUSTED"
    FULLY_AUTHORIZED = "FULLY_AUTHORIZED"
    REVOKED = "REVOKED"

class DeviceRole(Enum):
    PRIMARY_HOST = "primary_host"
    SECONDARY_COMPUTE = "secondary_compute"
    CONSUMER_NODE = "consumer_node"
    WEARABLE_NODE = "wearable_node"
    SMART_HOME_NODE = "smart_home_node"

@dataclass
class DeviceProfile:
    """
    Runtime-generated profile describing a device's physical capabilities,
    trust status, and execution potential. Hardcoding device names is strictly
    forbidden; execution decisions must rely on these capability flags.
    """
    device_id: str
    device_type: str
    role: DeviceRole
    trust_level: TrustLevel = TrustLevel.DISCOVERED
    
    # OS & System
    operating_system: str = "unknown"
    os_version: str = "unknown"
    architecture: str = "unknown"
    
    # Capabilities & Performance
    performance_class: str = "low"  # low, medium, high
    network_class: str = "unknown"  # low_latency, high_bandwidth, unstable
    
    # Hardware resources
    cpu_cores: int = 1
    gpu_available: bool = False
    ram_mb: int = 1024
    vram_mb: int = 0
    storage_mb: int = 0
    
    # I/O Sensors
    camera_available: bool = False
    mic_available: bool = False
    speaker_available: bool = False
    display_available: bool = False
    sensors: List[str] = field(default_factory=list)
    
    # Execution runtimes
    supported_runtimes: List[str] = field(default_factory=list)
    
    # Execution capability flags
    local_llm: bool = False
    local_vision: bool = False
    local_tts: bool = False
    remote_execution_allowed: bool = True
    
    # Security
    permissions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission: str) -> bool:
        """Check if this device has a specific permission."""
        if self.trust_level in (TrustLevel.UNSEEN, TrustLevel.DISCOVERED, TrustLevel.REVOKED):
            return False
        if permission in self.permissions:
            return True
        # Fully authorized devices implicitly hold broad capabilities (excluding extreme risk ones)
        if self.trust_level == TrustLevel.FULLY_AUTHORIZED:
            if permission not in ["system.shell", "system.filesystem_write"]:
                return True
        return False
