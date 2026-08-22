"""
Vivy Hub - Node Capability Client
Helper for issuing capability requests from the Node to the Hub.
"""
from hub.node.node_connection import NodeConnection
from hub.protocol.envelope import VivyMessage
from typing import Dict, Any

class CapabilityClient:
    def __init__(self, connection: NodeConnection):
        self.connection = connection
        
    async def execute_remote(self, capability_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Requests remote execution of a capability."""
        req = VivyMessage(
            type="capability.request",
            device_id=self.connection.device_id,
            capability=capability_id,
            payload=payload
        )
        print(f"[CapabilityClient] Requesting remote execution for {capability_id}...")
        
        resp = await self.connection.request(req)
        
        if resp.type == "capability.error":
            raise Exception(f"Remote execution failed: {resp.payload.get('error')}")
            
        return resp.payload
