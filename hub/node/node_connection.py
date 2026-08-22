"""
Vivy Hub - Node Connection
WebSocket client that runs on the Edge Node and connects to the Primary Hub.
"""
import asyncio
import websockets
from hub.protocol.envelope import VivyMessage
from typing import Dict, Any

class NodeConnection:
    def __init__(self, host: str, port: int, device_id: str, session_key: str):
        self.uri = f"ws://{host}:{port}"
        self.device_id = device_id
        self.session_key = session_key
        self.websocket = None
        self._pending_requests: Dict[str, asyncio.Future] = {}
        
    async def connect(self):
        self.websocket = await websockets.connect(self.uri)
        print(f"[NodeConnection] Connected to Hub at {self.uri}")
        
        # Authenticate
        auth_msg = VivyMessage(
            type="device.authenticate",
            device_id=self.device_id,
            security={"session_key": self.session_key}
        )
        await self.websocket.send(auth_msg.to_json())
        
        ack_str = await self.websocket.recv()
        ack = VivyMessage.from_json(ack_str)
        if ack.type != "device.authenticate_ack":
            raise Exception(f"Failed to authenticate with Hub, received type '{ack.type}'. Raw: {ack_str}")
        print("[NodeConnection] Successfully authenticated.")
        
        # Start listener loop
        self._listen_task = asyncio.create_task(self._listen())
        
    async def _listen(self):
        try:
            async for message_str in self.websocket:
                msg = VivyMessage.from_json(message_str)
                if msg.request_id and msg.request_id in self._pending_requests:
                    self._pending_requests[msg.request_id].set_result(msg)
                else:
                    print(f"[NodeConnection] Received unhandled async message: {msg.type}")
        except websockets.exceptions.ConnectionClosed:
            print("[NodeConnection] Connection to Hub closed.")
            
    async def request(self, msg: VivyMessage) -> VivyMessage:
        """Send a request and wait for the correlated response."""
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[msg.message_id] = future
        
        await self.websocket.send(msg.to_json())
        result = await future
        
        del self._pending_requests[msg.message_id]
        return result
        
    async def close(self):
        if self.websocket:
            await self.websocket.close()
