"""
Vivy Hub - Capability Router
Extends the existing Capability Registry to support portable capabilities and discovery.
"""
import threading
from typing import Dict, List, Optional
from hub.capability_manifest import CapabilityManifest, ExecutionMode
from hub.device_registry import DeviceRegistry
from hub.device_identity import DeviceProfile

class CapabilityRouter:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self._manifests: Dict[str, CapabilityManifest] = {}
        self._device_registry = DeviceRegistry.get_instance()
        
    @classmethod
    def get_instance(cls) -> "CapabilityRouter":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def register_manifest(self, manifest: CapabilityManifest) -> None:
        """Register a portable capability manifest."""
        with self._lock:
            self._manifests[manifest.capability_id] = manifest

    def discover_capability(self, capability_id: str) -> Optional[CapabilityManifest]:
        """Find a capability by its ID."""
        with self._lock:
            return self._manifests.get(capability_id)
            
    def get_providers_for_capability(self, capability_id: str) -> List[DeviceProfile]:
        """Find devices that have the resources to execute the capability."""
        with self._lock:
            manifest = self.discover_capability(capability_id)
            if not manifest:
                return []
            
            capable_devices = []
            for device in self._device_registry.list_devices():
                if self._can_device_execute(device, manifest):
                    capable_devices.append(device)
            return capable_devices
            
    def _can_device_execute(self, device: DeviceProfile, manifest: CapabilityManifest) -> bool:
        """Check if a device meets the hardware and resource requirements."""
        reqs = manifest.requirements
        
        # Hardware checks
        if reqs.get("camera", False) and not device.camera_available:
            return False
        if reqs.get("mic", False) and not device.mic_available:
            return False
        if reqs.get("speaker", False) and not device.speaker_available:
            return False
            
        # Resource checks
        if reqs.get("gpu") == "required" and not device.gpu_available:
            return False
        if reqs.get("ram_mb", 0) > device.ram_mb:
            return False
        if reqs.get("vram_mb", 0) > device.vram_mb:
            return False
            
        # Missing permissions could also block execution, but we handle that at lease-time
        return True
