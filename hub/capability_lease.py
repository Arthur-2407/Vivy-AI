"""
Vivy Hub - Capability Lease
Manages temporary authorizations for executing capabilities remotely.
"""
import time
import uuid
import threading
from typing import Dict, Optional
from dataclasses import dataclass

@dataclass
class CapabilityLease:
    lease_id: str
    capability_id: str
    requester_device_id: str
    executor_device_id: str
    granted_at: float
    expires_at: float
    status: str = "active"  # active, expired, cancelled, completed

class LeaseManager:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self._leases: Dict[str, CapabilityLease] = {}
        
    @classmethod
    def get_instance(cls) -> "LeaseManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def create_lease(self, capability_id: str, requester_id: str, executor_id: str, duration_sec: float = 60.0) -> CapabilityLease:
        with self._lock:
            lease_id = f"lease_{uuid.uuid4().hex[:12]}"
            now = time.time()
            lease = CapabilityLease(
                lease_id=lease_id,
                capability_id=capability_id,
                requester_device_id=requester_id,
                executor_device_id=executor_id,
                granted_at=now,
                expires_at=now + duration_sec
            )
            self._leases[lease_id] = lease
            print(f"[LeaseManager] Created lease {lease_id} for {capability_id} ({requester_id} -> {executor_id})")
            return lease
            
    def validate_lease(self, lease_id: str, requester_id: str, capability_id: str, risk_level: str = "low") -> bool:
        with self._lock:
            lease = self._leases.get(lease_id)
            if not lease or lease.status != "active": return False
            if lease.requester_device_id != requester_id or lease.capability_id != capability_id: return False
            if time.time() > lease.expires_at:
                lease.status = "expired"
                return False
            # Enforce risk clearance
            if risk_level == "critical" and not requester_id.startswith("auth_admin"):
                return False
            return True
            
    def revoke_lease(self, lease_id: str) -> None:
        with self._lock:
            if lease_id in self._leases:
                self._leases[lease_id].status = "cancelled"
                print(f"[LeaseManager] Revoked lease {lease_id}")
                
    def cleanup_expired(self) -> None:
        with self._lock:
            now = time.time()
            for lease in self._leases.values():
                if lease.status == "active" and now > lease.expires_at:
                    lease.status = "expired"
