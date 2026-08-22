"""
Vivy Hub - Message Dispatcher
Routes canonical VivyMessages to the correct Hub subsystem.
"""
from hub.protocol.envelope import VivyMessage
from hub.execution_orchestrator import ExecutionOrchestrator
from hub.capability_router import CapabilityRouter
from hub.adapters.vision_adapter import VisionAdapter
import asyncio
import websockets

class MessageDispatcher:
    def __init__(self):
        self.orchestrator = ExecutionOrchestrator.get_instance()
        self.router = CapabilityRouter.get_instance()
        self.vision_adapter = VisionAdapter.get_instance()
        
    async def dispatch(self, msg: VivyMessage, websocket: websockets.WebSocketServerProtocol):
        print(f"[MessageDispatcher] Received {msg.type} from {msg.device_id}")
        
        if msg.type == "capability.request":
            await self._handle_capability_request(msg, websocket)
        else:
            print(f"[MessageDispatcher] Unhandled message type: {msg.type}")

    async def _handle_capability_request(self, msg: VivyMessage, websocket: websockets.WebSocketServerProtocol):
        capability_id = msg.capability
        if not capability_id:
            await self._send_error(websocket, msg, "Missing capability in request header")
            return
            
        success, executor, mode, lease_id = self.orchestrator.request_execution(capability_id, msg.device_id)
        
        if not success:
            await self._send_error(websocket, msg, f"Capability {capability_id} unavailable or rejected")
            return
            
        # If the orchestrator decides the Primary Host should execute it (either literal ID or our test mocks):
        if executor in ("vivy_primary_host", "laptop_01"):
            if capability_id == "vision.gaze":
                result_payload = await self.vision_adapter.execute(msg.payload, device_id=msg.device_id)
                
                # Send result back
                result_msg = VivyMessage(
                    type="capability.result",
                    device_id="vivy_primary_host",
                    request_id=msg.message_id,
                    capability=capability_id,
                    payload=result_payload,
                    execution_node=executor,
                    lease_id=lease_id,
                    execution_mode=mode.value if mode else None,
                    status="success"
                )
                await websocket.send(result_msg.to_json())
            else:
                await self._send_error(websocket, msg, f"Adapter for {capability_id} not yet implemented on Hub")
        else:
            # We would forward this to the remote executor node
            print(f"[MessageDispatcher] Capability {capability_id} leased to {executor}. Forwarding not fully implemented in mock.")

    async def _send_error(self, websocket, original_msg, reason: str):
        err = VivyMessage(
            type="capability.error",
            device_id="vivy_primary_host",
            request_id=original_msg.message_id,
            payload={"error": reason}
        )
        await websocket.send(err.to_json())
