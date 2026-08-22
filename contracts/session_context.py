from dataclasses import dataclass

@dataclass
class SessionContext:
    """Canonical Session Scope for a Chat Instance"""
    session_id: str
    auth_token: str
    user_profile_id: str
    session_start_time: float
    client_device_type: str
    network_origin: str
    active_capabilities: list
    
    def to_dict(self):
        return self.__dict__
