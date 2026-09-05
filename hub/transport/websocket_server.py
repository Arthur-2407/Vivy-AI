"""
Vivy Hub - Authenticated WebSocket Server
Accepts connections from Vivy Nodes, validates sessions, and delegates to the Message Dispatcher.

Supports two connection protocols:
  1. device.authenticate (pre-shared session key) — used by hub/node/node_connection.py
  2. identity.request → pairing.challenge → pairing.response — used by hub/node_prototype/node_client.py

Both paths converge to the same authenticated message loop.
"""
import asyncio
import websockets
import threading
import json
from hub.pairing_manager import PairingManager
from hub.protocol.envelope import VivyMessage
from hub.device_registry import DeviceRegistry
from hub.device_identity import DeviceProfile, DeviceRole, TrustLevel
from hub.capability_lease import LeaseManager
from typing import Callable, Coroutine, Any, Optional
import traceback

class HubWebSocketServer:
    _instance = None
    _lock = threading.RLock()

    def __init__(self, port: int = 8765):
        self.port = port
        self.pairing = PairingManager.get_instance()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_future = None
        self.on_message_callback = None  # Callable[[VivyMessage, ws], Coroutine]

    @classmethod
    def get_instance(cls) -> "HubWebSocketServer":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def set_dispatcher(self, callback):
        self.on_message_callback = callback

    # ── Authentication Helpers ────────────────────────────────────────────────

    async def _auth_via_session_key(self, websocket, auth_msg: VivyMessage) -> Optional[str]:
        """Validate pre-shared session key. Returns device_id on success, None on failure."""
        session_key = auth_msg.security.get("session_key")
        device_id = auth_msg.device_id

        if not self.pairing.validate_session(device_id, session_key):
            print(f"[WebSocketServer] Rejected unauthorized connection from {device_id} "
                  f"(key: {session_key}, valid: {self.pairing._active_sessions})")
            await websocket.close(1008, "Invalid session key")
            return None

        print(f"[WebSocketServer] Authenticated Node: {device_id}")
        ack = VivyMessage(
            type="device.authenticate_ack",
            device_id="vivy_primary_host",
            request_id=auth_msg.message_id,
            payload={"plane": "control", "streaming_enabled": True}
        )
        await websocket.send(ack.to_json())
        return device_id

    async def _auth_via_identity_pairing(self, websocket, first_msg_str: str) -> Optional[str]:
        """
        Handle identity.request → pairing.challenge → pairing.response flow.
        Used by node_prototype/node_client.py.
        Returns device_id on success, None on failure.
        """
        try:
            first_msg = json.loads(first_msg_str)
        except Exception:
            await websocket.close(1008, "Malformed identity request")
            return None

        device_id = first_msg.get("device_id", "")
        if not device_id:
            await websocket.close(1008, "Missing device_id in identity.request")
            return None

        # Generate a pairing code and send the challenge
        pairing_code = self.pairing.initiate_pairing(device_id)
        print(f"[WebSocketServer] Identity request from {device_id}. "
              f"Pairing code (show to user): {pairing_code}")

        challenge_msg = {
            "protocol": "vivy",
            "version": "1",
            "type": "pairing.challenge",
            "device_id": "vivy_primary_host",
            "payload": {
                "message": f"Enter the PIN shown for device '{device_id}': {pairing_code}",
                "pairing_code": pairing_code  # In production this would be shown on Hub UI only
            }
        }
        await websocket.send(json.dumps(challenge_msg))

        # Wait for pairing.response
        try:
            resp_str = await asyncio.wait_for(websocket.recv(), timeout=120.0)  # 2 min for user to enter PIN
            resp = json.loads(resp_str)
        except asyncio.TimeoutError:
            await websocket.close(1008, "Pairing timeout — PIN not entered in time")
            return None
        except Exception:
            await websocket.close(1008, "Malformed pairing response")
            return None

        if resp.get("type") != "pairing.response":
            await websocket.close(1008, f"Expected pairing.response, got {resp.get('type')}")
            return None

        pin = resp.get("payload", {}).get("pin", "")
        success, session_key = self.pairing.complete_pairing(device_id, pin)

        if not success:
            print(f"[WebSocketServer] Pairing failed for {device_id}: wrong PIN")
            reject_msg = {
                "protocol": "vivy",
                "version": "1",
                "type": "pairing.failed",
                "device_id": "vivy_primary_host",
                "payload": {"reason": "Invalid PIN"}
            }
            await websocket.send(json.dumps(reject_msg))
            await websocket.close(1008, "Invalid PIN")
            return None

        # Check protocol version compatibility
        client_version = first_msg.get("payload", {}).get("protocol_version", "1.0")
        if not client_version.startswith("1."):
            reject_msg = {
                "protocol": "vivy",
                "version": "1",
                "type": "protocol.update_required",
                "device_id": "vivy_primary_host",
                "payload": {"required_version": "1.0"}
            }
            await websocket.send(json.dumps(reject_msg))
            await websocket.close(1008, "Protocol version mismatch")
            return None

        # Pairing succeeded — register the node in DeviceRegistry with AUTHENTICATED trust
        payload = first_msg.get("payload", {})
        node_profile = DeviceProfile(
            device_id=device_id,
            device_type=payload.get("device_type", "node_prototype"),
            role=DeviceRole.CONSUMER_NODE,
            trust_level=TrustLevel.AUTHENTICATED,
            camera_available="camera" in payload.get("hardware", []),
            mic_available="mic" in payload.get("hardware", []),
            protocol_version=client_version,
            app_version=payload.get("app_version", "unknown")
        )
        DeviceRegistry.get_instance().register_device(node_profile)
        print(f"[WebSocketServer] Pairing complete for {device_id}. Session key issued.")

        # Gather supported capabilities from the router
        from hub.capability_router import CapabilityRouter
        router = CapabilityRouter.get_instance()
        caps = [m.capability_id for m in router._manifests.values()]

        # Send identity.accept with session_id
        accept_msg = {
            "protocol": "vivy",
            "version": "1",
            "type": "identity.accept",
            "device_id": "vivy_primary_host",
            "session_id": session_key,
            "payload": {
                "plane": "control",
                "streaming_enabled": True,
                "api_port": 5000,
                "supported_capabilities": caps,
                "protocol_version": "1.0"
            }
        }
        await websocket.send(json.dumps(accept_msg))
        return device_id

    # ── Disconnect Cleanup ────────────────────────────────────────────────────

    def _cleanup_device_on_disconnect(self, device_id: str):
        """Revoke all active leases and unregister the device on disconnect."""
        try:
            LeaseManager.get_instance().revoke_all_for_device(device_id)
        except Exception as e:
            print(f"[WebSocketServer] Lease cleanup error for {device_id}: {e}")
        try:
            DeviceRegistry.get_instance().unregister_device(device_id)
        except Exception as e:
            print(f"[WebSocketServer] Registry cleanup error for {device_id}: {e}")
        print(f"[WebSocketServer] Cleaned up disconnected node: {device_id}")

    # ── Main Handler ──────────────────────────────────────────────────────────

    async def _handler(self, websocket, *args, **kwargs):
        device_id = None
        try:
            # 1. Receive first message to determine auth protocol
            try:
                first_msg_str = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            except asyncio.TimeoutError:
                print("[WebSocketServer] Client authentication timed out")
                await websocket.close(1008, "Authentication timeout")
                return

            # Parse to detect the auth flow
            try:
                first_data = json.loads(first_msg_str)
                msg_type = first_data.get("type", "")
            except Exception:
                await websocket.close(1008, "Malformed initial message")
                return

            if msg_type == "device.authenticate":
                # Flow 1: pre-shared session key (hub/node/node_connection.py)
                auth_msg = VivyMessage.from_json(first_msg_str)
                device_id = await self._auth_via_session_key(websocket, auth_msg)

            elif msg_type == "identity.request":
                # Flow 2: mDNS-discovered pairing (hub/node_prototype/node_client.py)
                device_id = await self._auth_via_identity_pairing(websocket, first_msg_str)

            else:
                print(f"[WebSocketServer] Unknown initial message type: {msg_type}")
                await websocket.close(1008, f"Unknown auth message type: {msg_type}")
                return

            if device_id is None:
                return  # Authentication failed, connection already closed

            # 2. Authenticated message loop
            async for message_str in websocket:
                try:
                    msg = VivyMessage.from_json(message_str)
                    if self.on_message_callback:
                        asyncio.create_task(self.on_message_callback(msg, websocket))
                except Exception as e:
                    print(f"[WebSocketServer] Error processing message: {e}")
                    traceback.print_exc()

        except websockets.exceptions.ConnectionClosed:
            print(f"[WebSocketServer] Client disconnected: {device_id or 'unknown'}")
        except Exception as e:
            print(f"[WebSocketServer] Error in handler: {e}")
        finally:
            if device_id:
                self._cleanup_device_on_disconnect(device_id)

    # ── Server Lifecycle ──────────────────────────────────────────────────────

    def _start_server(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop_future = self._loop.create_future()

        async def run_server():
            async with websockets.serve(self._handler, "0.0.0.0", self.port):
                print(f"[WebSocketServer] Hub listening on ws://0.0.0.0:{self.port}")
                await self._stop_future

        self._loop.run_until_complete(run_server())
        self._loop.close()

    def start(self):
        with self._lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._start_server, daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            if self._loop and self._stop_future:
                self._loop.call_soon_threadsafe(self._stop_future.set_result, None)
            if self._thread:
                self._thread.join(timeout=2.0)
                self._thread = None
