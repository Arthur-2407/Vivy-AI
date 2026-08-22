"""
Vivy Hub - Pairing Manager
Manages device connection lifecycle, authentication, session keys, and trust elevation.
"""
import uuid
import threading
from typing import Dict, Tuple

class PairingManager:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        # Maps device_id -> session_key
        self._active_sessions: Dict[str, str] = {}
        # Maps device_id -> pairing_code
        self._pending_pairings: Dict[str, str] = {}
        
    @classmethod
    def get_instance(cls) -> "PairingManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
            
    def initiate_pairing(self, device_id: str) -> str:
        """Generate a pairing code for a discovered device."""
        with self._lock:
            code = str(uuid.uuid4())[:8]
            self._pending_pairings[device_id] = code
            return code
            
    def complete_pairing(self, device_id: str, code: str) -> Tuple[bool, str]:
        """Validate pairing code and generate a session key."""
        with self._lock:
            if device_id in self._pending_pairings and self._pending_pairings[device_id] == code:
                session_key = f"sk_{uuid.uuid4().hex}"
                self._active_sessions[device_id] = session_key
                del self._pending_pairings[device_id]
                return True, session_key
            return False, ""
            
    def validate_session(self, device_id: str, session_key: str) -> bool:
        """Verify if a request is authenticated."""
        with self._lock:
            return self._active_sessions.get(device_id) == session_key
            
    def revoke_session(self, device_id: str) -> None:
        """Revoke a session key and drop trust."""
        with self._lock:
            if device_id in self._active_sessions:
                del self._active_sessions[device_id]
