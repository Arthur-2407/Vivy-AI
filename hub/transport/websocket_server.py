"""
Vivy Hub - Authenticated WebSocket Server
Accepts connections from Vivy Nodes, validates sessions, and delegates to the Message Dispatcher.
"""
import asyncio
import websockets
import threading
from hub.pairing_manager import PairingManager
from hub.protocol.envelope import VivyMessage
from typing import Callable, Coroutine, Any
import traceback

class HubWebSocketServer:
    _instance = None
    _lock = threading.RLock()

    def __init__(self, port: int = 8765):
        self.port = port
        self.pairing = PairingManager.get_instance()
        self._loop = None
        self._thread = None
        self._stop_future = None
        self.on_message_callback = None # Callable[[VivyMessage, websockets.WebSocketServerProtocol], Coroutine[Any, Any, None]]

    @classmethod
    def get_instance(cls) -> "HubWebSocketServer":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
            
    def set_dispatcher(self, callback):
        self.on_message_callback = callback

    async def _handler(self, websocket, *args, **kwargs):
        # 1. Authentication Handshake
        try:
            auth_msg_str = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            auth_msg = VivyMessage.from_json(auth_msg_str)
            
            if auth_msg.type != "device.authenticate":
                await websocket.close(1008, "Expected authentication message")
                return
                
            session_key = auth_msg.security.get("session_key")
            device_id = auth_msg.device_id
            
            if not self.pairing.validate_session(device_id, session_key):
                print(f"[WebSocketServer] Rejected unauthorized connection from {device_id} (key: {session_key}, valid: {self.pairing._active_sessions})")
                await websocket.close(1008, "Invalid session key")
                return
                
            print(f"[WebSocketServer] Authenticated Node: {device_id}")
            
            # Send ack
            ack = VivyMessage(
                type="device.authenticate_ack",
                device_id="vivy_primary_host",
                request_id=auth_msg.message_id,
                payload={"plane": "control", "streaming_enabled": True}
            )
            await websocket.send(ack.to_json())
            
            # 2. Message Loop
            async for message_str in websocket:
                try:
                    msg = VivyMessage.from_json(message_str)
                    if self.on_message_callback:
                        # Dispatch async
                        asyncio.create_task(self.on_message_callback(msg, websocket))
                except Exception as e:
                    print(f"[WebSocketServer] Error processing message: {e}")
                    traceback.print_exc()
                    
        except websockets.exceptions.ConnectionClosed:
            print("[WebSocketServer] Client disconnected")
        except asyncio.TimeoutError:
            print("[WebSocketServer] Client authentication timed out")
            await websocket.close(1008, "Authentication timeout")
        except Exception as e:
            print(f"[WebSocketServer] Error in handler: {e}")

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
