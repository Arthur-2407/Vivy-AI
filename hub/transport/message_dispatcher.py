"""
Vivy Hub - Message Dispatcher
Routes canonical VivyMessages to the correct Hub subsystem.
Routes ALL registered capability types through the appropriate adapter.
Uses the ApiProxyAdapter for REST-backed capabilities and dedicated adapters
for streaming capabilities (vision, audio, GPS).
Fault class: Recoverable.
"""
import time
from hub.protocol.envelope import VivyMessage
from hub.execution_orchestrator import ExecutionOrchestrator
from hub.capability_router import CapabilityRouter
from hub.adapters.vision_adapter import VisionAdapter
from hub.adapters.api_proxy_adapter import ApiProxyAdapter
from hub.adapters.audio_adapter import AudioAdapter
import asyncio
import websockets
from websockets.asyncio.server import ServerConnection as WebSocketServerConnection


class MessageDispatcher:
    def __init__(self):
        self.orchestrator = ExecutionOrchestrator.get_instance()
        self.router = CapabilityRouter.get_instance()
        self.vision_adapter = VisionAdapter.get_instance()
        self.api_proxy = ApiProxyAdapter.get_instance()
        self.audio_adapter = AudioAdapter.get_instance()

    async def dispatch(self, msg: VivyMessage, websocket: WebSocketServerConnection):
        print(f"[MessageDispatcher] {msg.type} from {msg.device_id}")

        if msg.type == "capability.request":
            await self._handle_capability_request(msg, websocket)
        elif msg.type == "heartbeat":
            await self._handle_heartbeat(msg, websocket)
        elif msg.type == "gps.update":
            await self._handle_gps_update(msg, websocket)
        elif msg.type == "telemetry.update":
            await self._handle_telemetry_update(msg, websocket)
        else:
            print(f"[MessageDispatcher] Unhandled message type: {msg.type}")

    async def _handle_capability_request(self, msg: VivyMessage, websocket: WebSocketServerConnection):
        capability_id = msg.capability
        if not capability_id:
            await self._send_error(websocket, msg, "Missing capability in request header")
            return

        success, executor, mode, lease_id = self.orchestrator.request_execution(
            capability_id, msg.device_id
        )

        if not success:
            await self._send_error(
                websocket, msg,
                f"Capability '{capability_id}' unavailable — no eligible provider found."
            )
            return

        # Primary host handles execution
        if executor == "vivy_primary_host":
            result_payload = await self._execute_on_host(msg, capability_id)
        else:
            # Remote node execution — forward the lease to the target node
            # (real forwarding to connected node websocket handled by websocket_server)
            result_payload = {
                "status": "delegated",
                "executor": executor,
                "lease_id": lease_id,
                "message": f"Capability '{capability_id}' delegated to node {executor}"
            }

        result_msg = VivyMessage(
            type="capability.result",
            device_id="vivy_primary_host",
            request_id=msg.message_id,
            capability=capability_id,
            payload=result_payload,
            execution_node=executor,
            lease_id=lease_id,
            execution_mode=mode.value if mode else None,
            status="success" if "error" not in result_payload else "error"
        )
        await websocket.send(result_msg.to_json())

    async def _execute_on_host(self, msg: VivyMessage, capability_id: str) -> dict:
        """
        Route to the correct adapter based on capability type.
        All adapters are non-blocking wrappers around synchronous code,
        executed in a thread pool via asyncio.to_thread.
        """
        loop = asyncio.get_event_loop()

        # Vision capabilities → VisionAdapter
        # Special case: vision.screen_capture without an 'image' payload key means
        # the remote client (Android) wants to VIEW the host screen, not send a camera
        # frame to Vivy. Route it through screen.capture → /api/screen/screenshot instead.
        # VisionAdapter requires an image from the client; screen.capture captures the host.
        if capability_id.startswith("vision."):
            payload = msg.payload or {}
            if capability_id == "vision.screen_capture" and "image" not in payload:
                print(f"[MessageDispatcher] vision.screen_capture (no image) → screen.capture on host for {msg.device_id}")
                return await loop.run_in_executor(
                    None,
                    lambda: self.api_proxy.execute("screen.capture", {}, device_id=msg.device_id)
                )
            return await loop.run_in_executor(
                None,
                lambda: asyncio.run(
                    self.vision_adapter.execute(msg.payload, device_id=msg.device_id, capability_id=capability_id)
                )
            )

        # Audio capabilities → AudioAdapter
        if capability_id.startswith("audio."):
            return await loop.run_in_executor(
                None,
                lambda: self.audio_adapter.execute(capability_id, msg.payload, device_id=msg.device_id)
            )

        # All REST-backed capabilities → ApiProxyAdapter
        if self.api_proxy.can_handle(capability_id):
            session_key = getattr(msg, "session_id", None) or (msg.payload.get("session_key", "") if msg.payload else "")
            return await loop.run_in_executor(
                None,
                lambda: self.api_proxy.execute(capability_id, msg.payload or {}, device_id=msg.device_id, session_key=session_key)
            )

        # Unknown capability — return a clear error, never silently succeed
        return {"error": f"No adapter registered for capability '{capability_id}' on primary host."}

    async def _handle_heartbeat(self, msg: VivyMessage, websocket: WebSocketServerConnection):
        """Update device telemetry from heartbeat payload."""
        try:
            from hub.sync_manager import SyncManager
            SyncManager.get_instance().update_device_telemetry(
                device_id=msg.device_id,
                telemetry=msg.payload or {}
            )
            # Echo an ack
            ack = VivyMessage(
                type="heartbeat.ack",
                device_id="vivy_primary_host",
                request_id=msg.message_id,
                payload={"timestamp": time.time()}
            )
            await websocket.send(ack.to_json())
        except Exception as e:
            print(f"[MessageDispatcher] Heartbeat handling error: {e}")

    async def _handle_gps_update(self, msg: VivyMessage, websocket: WebSocketServerConnection):
        """Store GPS update from a node in the DeviceRegistry metadata."""
        try:
            from hub.device_registry import DeviceRegistry
            device = DeviceRegistry.get_instance().get_device(msg.device_id)
            if device:
                if device.metadata is None:
                    device.metadata = {}
                device.metadata["gps"] = msg.payload
                device.metadata["gps_updated"] = time.time()
            print(f"[MessageDispatcher] GPS update from {msg.device_id}: {msg.payload}")
        except Exception as e:
            print(f"[MessageDispatcher] GPS update error: {e}")

    async def _handle_telemetry_update(self, msg: VivyMessage, websocket: WebSocketServerConnection):
        """Handle explicit telemetry updates from nodes."""
        await self._handle_heartbeat(msg, websocket)

    async def _send_error(self, websocket: WebSocketServerConnection, original_msg: VivyMessage, reason: str):
        err = VivyMessage(
            type="capability.error",
            device_id="vivy_primary_host",
            request_id=original_msg.message_id,
            payload={"error": reason}
        )
        await websocket.send(err.to_json())
