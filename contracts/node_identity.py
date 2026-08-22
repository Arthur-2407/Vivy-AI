from dataclasses import dataclass

@dataclass
class NodeIdentity:
    """Canonical Identity for Distributed Devices on Vivy Hub"""
    node_id: str
    public_key: str
    risk_clearance: str
    is_primary_host: bool
    capabilities: list
    
    def to_dict(self):
        return self.__dict__
