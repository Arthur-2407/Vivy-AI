"""
Vivy Hub - Device Registry
Maintains the dynamic runtime profiles of all discovered and connected devices.
"""
import threading
from typing import Dict, List, Optional
from hub.device_identity import DeviceProfile, TrustLevel

class DeviceRegistry:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self._devices: Dict[str, DeviceProfile] = {}
        
    @classmethod
    def get_instance(cls) -> "DeviceRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def register_device(self, profile: DeviceProfile) -> None:
        """Add or update a device profile."""
        with self._lock:
            self._devices[profile.device_id] = profile
            print(f"[DeviceRegistry] Registered device: {profile.device_id} ({profile.device_type})")
            
    def get_device(self, device_id: str) -> Optional[DeviceProfile]:
        """Retrieve a specific device profile."""
        with self._lock:
            return self._devices.get(device_id)
            
    def update_trust(self, device_id: str, level: TrustLevel) -> bool:
        """Update a device's trust level."""
        with self._lock:
            device = self.get_device(device_id)
            if device:
                device.trust_level = level
                return True
            return False
            
    def list_devices(self) -> List[DeviceProfile]:
        """List all devices."""
        with self._lock:
            return list(self._devices.values())
            
    def get_devices_by_capability(self, capability_flag: str) -> List[DeviceProfile]:
        """Find devices that support a specific local capability (e.g. 'local_vision')."""
        with self._lock:
            results = []
            for d in self._devices.values():
                if getattr(d, capability_flag, False):
                    results.append(d)
            return results

    def unregister_device(self, device_id: str) -> bool:
        """Remove a device profile on disconnect or revocation."""
        with self._lock:
            if device_id in self._devices:
                del self._devices[device_id]
                print(f"[DeviceRegistry] Unregistered device: {device_id}")
                return True
            return False

    def get_device_ids(self) -> List[str]:
        """Return all currently registered device IDs."""
        with self._lock:
            return list(self._devices.keys())
