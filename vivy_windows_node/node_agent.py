"""
Vivy Windows Node — Node Agent
The main agent for Windows secondary nodes.
Discovers the Vivy Hub via mDNS, authenticates via PIN-based pairing,
maintains a live WebSocket connection with heartbeat, and proxies all
Vivy feature requests to the primary host through the Hub.
Fault class: Recoverable (reconnect loop with exponential backoff).
"""
import asyncio
import json
import os
import sys
import time
import uuid
import threading
import socket
import subprocess
import hashlib
import hmac
import base64
import getpass

# Ensure vivy root is in path when running from vivy_windows_node/
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import websockets
except ImportError:
    print("[VivyNode] websockets not installed. Run: pip install websocket-client websockets")
    sys.exit(1)

try:
    from vivy_windows_node.hardware_detector import detect as detect_hardware
except ImportError:
    from hardware_detector import detect as detect_hardware

# ── Node identity ────────────────────────────────────────────────────────────
NODE_VERSION = "1.0.0"
PROTOCOL_VERSION = "1.0"
HUB_PROTOCOL_VERSION = "1.0"

_NODE_ID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".node_id")

def _get_or_create_node_id() -> str:
    """Persistent node ID — stable across restarts for pairing continuity."""
    if os.path.exists(_NODE_ID_FILE):
        with open(_NODE_ID_FILE) as f:
            return f.read().strip()
    nid = f"vivy-win-{uuid.uuid4().hex[:8]}"
    with open(_NODE_ID_FILE, "w") as f:
        f.write(nid)
    return nid

NODE_ID = _get_or_create_node_id()

_ENDPOINT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_hub")

def _get_cached_endpoint():
    if os.path.exists(_ENDPOINT_FILE):
        try:
            with open(_ENDPOINT_FILE) as f:
                parts = f.read().strip().split(":")
                if len(parts) == 2:
                    return parts[0], int(parts[1])
        except Exception:
            pass
    return None, None

def _save_cached_endpoint(host, port):
    try:
        with open(_ENDPOINT_FILE, "w") as f:
            f.write(f"{host}:{port}")
    except Exception:
        pass

def get_bt_pan_gateway() -> str:
    """Detect Bluetooth PAN adapter and return its default gateway (likely the Hub)."""
    try:
        result = subprocess.run(
            ["wmic", "nicconfig", "where", "Description like '%Bluetooth%' and IPEnabled=TRUE", "get", "DefaultIPGateway", "/value"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "DefaultIPGateway=" in line:
                gw = line.split("=", 1)[1].strip().strip('{"}')
                if gw:
                    return gw
    except Exception:
        pass
    return None

def discover_hub_mdns(timeout: float = 6.0):
    """
    Discover the Vivy Hub on the local network using zeroconf mDNS.
    Returns (host, port) or (None, None) if not found.
    """
    try:
        from zeroconf import ServiceBrowser, Zeroconf

        class _Listener:
            def __init__(self):
                self.found_host = None
                self.found_port = None
                self.event = threading.Event()

            def add_service(self, zc, type_, name):
                info = zc.get_service_info(type_, name)
                if info:
                    self.found_host = socket.inet_ntoa(info.addresses[0])
                    self.found_port = info.port
                    self.event.set()

            def remove_service(self, *args): pass
            def update_service(self, *args): pass

        zeroconf = Zeroconf()
        listener = _Listener()
        ServiceBrowser(zeroconf, "_vivy._tcp.local.", listener)
        found = listener.event.wait(timeout=timeout)
        zeroconf.close()
        if found:
            return listener.found_host, listener.found_port
    except ImportError:
        print("[VivyNode] zeroconf not installed. Falling back to manual IP entry.")
    except Exception as e:
        print(f"[VivyNode] mDNS discovery error: {e}")
    return None, None

def discover_hub_udp(timeout: float = 3.0):
    """Listen for UDP broadcasts from the Hub (VIVY_HUB:<IP>:<PORT>)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', 8766))
        sock.settimeout(timeout)
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                data, addr = sock.recvfrom(1024)
                msg = data.decode('utf-8', errors='ignore')
                if msg.startswith("VIVY_HUB:"):
                    parts = msg.split(":")
                    if len(parts) >= 3:
                        return parts[1], int(parts[2])
            except socket.timeout:
                pass
    except Exception as e:
        print(f"[VivyNode] UDP discovery error: {e}")
    finally:
        try:
            sock.close()
        except:
            pass
    return None, None


def get_hub_address() -> tuple:
    """
    Try cached endpoint, then UDP discovery, then mDNS discovery,
    then BT PAN gateway heuristic, then fall back to manual entry.
    """
    cached_host, cached_port = _get_cached_endpoint()
    if cached_host and cached_port:
        print(f"[VivyNode] Probing cached endpoint {cached_host}:{cached_port}...")
        try:
            with socket.create_connection((cached_host, cached_port), timeout=2.0):
                print(f"[VivyNode] ✅ Cached endpoint reachable.")
                return cached_host, cached_port
        except Exception:
            print("[VivyNode] Cached endpoint unreachable.")

    print("[VivyNode] Discovering Vivy Hub via UDP broadcast...")
    host, port = discover_hub_udp(timeout=4.0)
    if host and port:
        print(f"[VivyNode] ✅ Hub discovered via UDP at {host}:{port}")
        _save_cached_endpoint(host, port)
        return host, port

    print("[VivyNode] Discovering Vivy Hub via mDNS...")
    host, port = discover_hub_mdns(timeout=6.0)
    if host and port:
        print(f"[VivyNode] ✅ Hub discovered via mDNS at {host}:{port}")
        _save_cached_endpoint(host, port)
        return host, port

    print("[VivyNode] Checking for Bluetooth PAN Gateway...")
    gw = get_bt_pan_gateway()
    if gw:
        print(f"[VivyNode] Probing BT PAN Gateway {gw}:8800...")
        try:
            with socket.create_connection((gw, 8800), timeout=2.0):
                print(f"[VivyNode] ✅ Hub discovered via BT PAN at {gw}:8800")
                _save_cached_endpoint(gw, 8800)
                return gw, 8800
        except Exception:
            print("[VivyNode] BT PAN Gateway unreachable.")

    print("[VivyNode] Discovery timed out. Enter Hub address manually.")
    host = input("  Hub IP address (e.g. 192.168.1.100): ").strip()
    port_str = input("  Hub port [8800]: ").strip() or "8800"
    if host and port_str:
        _save_cached_endpoint(host, int(port_str))
        return host, int(port_str)
    return None, None


# ── PIN-based authentication ────────────────────────────────────────────────
def get_pin() -> str:
    """Prompt for the Hub PIN. On first run the Hub displays a PIN on the host screen."""
    return getpass.getpass("  Enter Hub PIN (shown on the Vivy host screen): ").strip()


def compute_hmac(secret: str, challenge: str) -> str:
    """Compute HMAC-SHA256 of the challenge using the PIN as secret."""
    return hmac.new(secret.encode(), challenge.encode(), hashlib.sha256).hexdigest()


# ── WebSocket Node Agent ──────────────────────────────────────────────────────
class VivyWindowsNodeAgent:
    def __init__(self, hub_host: str, hub_port: int):
        self.hub_host = hub_host
        self.hub_port = hub_port
        self.ws_url = f"ws://{hub_host}:{hub_port}"
        self.node_id = NODE_ID
        self.session_key = None
        self.api_port = None
        self._running = True
        self._ws = None
        self._hardware = detect_hardware()
        self._status = "connecting"
        self._latency_ms = 0.0

        print(f"[VivyNode] Node ID: {self.node_id}")
        print(f"[VivyNode] Hardware: {self._hardware.get('performance_class')} class | "
              f"CPU={self._hardware.get('cpu_cores')}c | "
              f"RAM={self._hardware.get('ram_mb')}MB | "
              f"GPU={'Yes' if self._hardware.get('gpu_available') else 'No'} "
              f"VRAM={self._hardware.get('vram_mb')}MB")

    def build_identity_payload(self) -> dict:
        return {
            "node_id": self.node_id,
            "platform": "windows",
            "app_version": NODE_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "capabilities": self._get_capability_list(),
            "resource_limits": {
                "max_fps": 30 if self._hardware.get("gpu_available") else 15,
            },
            "hardware": {
                "cpu_cores": self._hardware.get("cpu_cores", 1),
                "ram_mb": self._hardware.get("ram_mb", 1024),
                "vram_mb": self._hardware.get("vram_mb", 0),
                "gpu_available": self._hardware.get("gpu_available", False),
                "gpu_model": self._hardware.get("metadata", {}).get("gpu_model", "unknown"),
                "cpu_model": self._hardware.get("metadata", {}).get("cpu_model", "unknown"),
                "storage_mb": self._hardware.get("storage_mb", 0),
                "performance_class": self._hardware.get("performance_class", "medium"),
            },
            "sensors": {
                "camera": self._hardware.get("camera_available", False),
                "mic": self._hardware.get("mic_available", False),
                "speaker": self._hardware.get("speaker_available", False),
                "display": self._hardware.get("display_available", True),
                "gps": False,
                "bluetooth": self._hardware.get("bluetooth_available", False),
            },
            "runtimes": self._hardware.get("supported_runtimes", []),
            "security_version": "1.0",
        }

    def _get_capability_list(self) -> list:
        caps = []
        if self._hardware.get("camera_available"):
            caps.extend(["vision.stream", "vision.face", "vision.emotion", "vision.gaze"])
        if self._hardware.get("mic_available"):
            caps.extend(["audio.stream", "audio.stt"])
        if self._hardware.get("speaker_available"):
            caps.append("audio.tts")
        caps.append("display.avatar")
        if self._hardware.get("gpu_available") and self._hardware.get("vram_mb", 0) >= 8000:
            caps.extend(["voice.train", "voice.training_status"])
        return caps

    async def run(self):
        """Main reconnect loop with exponential backoff."""
        self._loop = asyncio.get_running_loop()
        backoff = 1.0
        while self._running:
            try:
                print(f"\n[VivyNode] Connecting to Hub at {self.ws_url} ...")
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=30) as ws:
                    self._ws = ws
                    self._status = "authenticating"
                    backoff = 1.0  # Reset on successful connection

                    authenticated = await self._authenticate(ws)
                    if not authenticated:
                        print("[VivyNode] Authentication failed. Retrying in 15s...")
                        await asyncio.sleep(15)
                        continue

                    self._status = "connected"
                    print(f"[VivyNode] ✅ Connected and authenticated. Session: {self.session_key[:8]}...")

                    # Start heartbeat in background
                    heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))
                    try:
                        await self._message_loop(ws)
                    finally:
                        heartbeat_task.cancel()

            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError) as e:
                self._status = "disconnected"
                print(f"[VivyNode] Connection lost: {e}. Retrying in {backoff:.0f}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
            except Exception as e:
                self._status = "error"
                print(f"[VivyNode] Unexpected error: {e}. Retrying in {backoff:.0f}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    async def _authenticate(self, ws) -> bool:
        """Complete the identity.request → pairing.challenge → pairing.response flow."""
        try:
            # Step 1: Send identity.request
            identity_payload = self.build_identity_payload()
            await ws.send(json.dumps({
                "type": "identity.request",
                "payload": identity_payload
            }))

            # Step 2: Receive pairing.challenge or identity.accept
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            msg = json.loads(raw)

            if msg.get("type") == "identity.accept":
                # Hub accepted without challenge (re-paired device)
                payload = msg.get("payload", {})
                self.session_key = payload.get("session_key", str(uuid.uuid4()))
                self.api_port = payload.get("api_port", 5000)
                return True

            if msg.get("type") == "pairing.challenge":
                # Need PIN
                challenge = msg.get("payload", {}).get("challenge", "")
                pin = get_pin()
                response = compute_hmac(pin, challenge)
                await ws.send(json.dumps({
                    "type": "pairing.response",
                    "payload": {
                        "node_id": self.node_id,
                        "challenge_response": response,
                    }
                }))

                # Step 3: Receive pairing.result or identity.accept
                raw2 = await asyncio.wait_for(ws.recv(), timeout=30)
                msg2 = json.loads(raw2)
                if msg2.get("type") in ("identity.accept", "pairing.success"):
                    payload = msg2.get("payload", {})
                    self.session_key = payload.get("session_key", str(uuid.uuid4()))
                    self.api_port = payload.get("api_port", 5000)
                    return True
                elif msg2.get("type") == "pairing.failed":
                    print(f"[VivyNode] Pairing failed: {msg2.get('payload', {}).get('reason', 'unknown')}")
                    return False

            if msg.get("type") == "protocol.update_required":
                print(f"[VivyNode] Hub requires a newer protocol version: {msg.get('payload', {})}")
                return False

            print(f"[VivyNode] Unexpected auth message: {msg.get('type')}")
            return False

        except asyncio.TimeoutError:
            print("[VivyNode] Authentication timed out.")
            return False
        except Exception as e:
            print(f"[VivyNode] Authentication error: {e}")
            return False

    async def _message_loop(self, ws):
        """Main receive loop for incoming Hub messages."""
        async for raw in ws:
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")
                if msg_type == "capability.result":
                    await self._handle_capability_result(msg)
                elif msg_type == "capability.error":
                    print(f"[VivyNode] Capability error: {msg.get('payload', {}).get('error')}")
                elif msg_type == "sync.events":
                    await self._handle_sync_events(msg)
                elif msg_type == "heartbeat.ack":
                    pass  # Expected
                else:
                    print(f"[VivyNode] Unhandled message type: {msg_type}")
            except json.JSONDecodeError as e:
                print(f"[VivyNode] JSON decode error: {e}")
            except Exception as e:
                print(f"[VivyNode] Message handling error: {e}")

    async def _handle_capability_result(self, msg: dict):
        """Route capability results to the local UI or audio output."""
        cap = msg.get("capability", "")
        payload = msg.get("payload", {})

        if cap == "audio.tts" and payload.get("audio_b64"):
            # Play received audio
            await self._play_audio(payload["audio_b64"])
        elif cap in ("conversation.chat",):
            text = payload.get("reply", payload.get("text", ""))
            if text:
                print(f"\n  Vivy: {text}\n")

    async def _play_audio(self, audio_b64: str):
        """Decode and play base64 WAV audio through the system speaker."""
        try:
            import pyaudio
            import wave
            import io
            data = base64.b64decode(audio_b64)
            buf = io.BytesIO(data)
            with wave.open(buf, "rb") as wf:
                pa = pyaudio.PyAudio()
                stream = pa.open(
                    format=pa.get_format_from_width(wf.getsampwidth()),
                    channels=wf.getnchannels(),
                    rate=wf.getframerate(),
                    output=True
                )
                chunk = 1024
                data = wf.readframes(chunk)
                while data:
                    stream.write(data)
                    data = wf.readframes(chunk)
                stream.stop_stream()
                stream.close()
                pa.terminate()
        except Exception as e:
            print(f"[VivyNode] Audio playback error: {e}")

    async def _handle_sync_events(self, msg: dict):
        """Process sync events pushed from the Hub (conversation continuity)."""
        events = msg.get("payload", {}).get("events", [])
        for ev in events:
            ev_type = ev.get("type", "")
            if ev_type == "conversation.message" and ev.get("payload", {}).get("role") == "assistant":
                text = ev.get("payload", {}).get("text", "")
                if text:
                    print(f"\n  Vivy (sync): {text}\n")

    async def _heartbeat_loop(self, ws):
        """Send periodic heartbeats to keep the Hub updated on resource state."""
        while self._running:
            try:
                import psutil
                cpu_pct = psutil.cpu_percent(interval=None)
                ram = psutil.virtual_memory()
                ram_pct = ram.percent

                t0 = time.time()
                await ws.ping()
                latency_ms = (time.time() - t0) * 1000
                self._latency_ms = round(latency_ms, 1)

                heartbeat = {
                    "type": "heartbeat",
                    "device_id": self.node_id,
                    "payload": {
                        "cpu_pct": round(cpu_pct, 1),
                        "ram_pct": round(ram_pct, 1),
                        "gpu_pct": 0.0,
                        "battery_pct": self._hardware.get("battery_pct", 100.0),
                        "thermal": "normal",
                        "latency_ms": self._latency_ms,
                    }
                }
                await ws.send(json.dumps(heartbeat))
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[VivyNode] Heartbeat error: {e}")
                break
            await asyncio.sleep(20)

    async def send_capability_request(self, capability_id: str, payload: dict = None):
        """Send a capability request to the Hub."""
        if not self._ws:
            print("[VivyNode] Not connected — cannot send capability request.")
            return
        msg = {
            "type": "capability.request",
            "device_id": self.node_id,
            "message_id": f"req_{uuid.uuid4().hex[:8]}",
            "capability": capability_id,
            "payload": payload or {},
        }
        if self.session_key:
            msg["payload"]["session_key"] = self.session_key
        await self._ws.send(json.dumps(msg))


# ── Node UI thread ─────────────────────────────────────────────────────────
def start_async_loop(agent: VivyWindowsNodeAgent):
    """Run the asyncio loop in a background thread."""
    try:
        asyncio.run(agent.run())
    except Exception as e:
        print(f"[VivyNode] Async loop stopped: {e}")

def main():
    print("\n" + "="*55)
    print("  Vivy AI — Windows Node")
    print("  One AI. Every device.")
    print("="*55 + "\n")

    hub_host, hub_port = get_hub_address()
    agent = VivyWindowsNodeAgent(hub_host, hub_port)

    # Start asyncio loop in background thread
    async_thread = threading.Thread(target=start_async_loop, args=(agent,), daemon=True)
    async_thread.start()

    # Start Tkinter UI on the main thread
    try:
        from vivy_windows_node.node_ui import run_ui
        run_ui(agent)
    except Exception as e:
        print(f"[VivyNode] Node UI error: {e}")

if __name__ == "__main__":
    main()
