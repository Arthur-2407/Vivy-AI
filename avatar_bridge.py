"""
Vivy Avatar Bridge — WebSocket Server
======================================
Bridges Vivy's Python AI pipeline to the MateEngine Unity avatar runtime.

Communication:
  Python (this server) → Unity (WebSocket client)
  ws://127.0.0.1:8765

This module:
  - Monitors shared/emotion.txt, shared/status.txt, shared/reply_text.txt
  - Pushes state changes to all connected Unity clients via WebSocket
  - Accepts interaction events from Unity (headpat, click, etc.)
  - Can be imported by run_vivy.py for direct push calls

No existing pipeline files are modified by this module.
"""

import os
import sys
import json
import time
import asyncio
import threading
import base64
from resource_manager import get_resource_manager

# Reconfigure stdout/stderr to use utf-8 to avoid encoding errors with emojis or symbols on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Try to import websockets
try:
    import websockets
    import websockets.server
except ImportError:
    print("[AvatarBridge] ERROR: websockets not installed. Run: venv_avatar\\Scripts\\pip install websockets")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(BASE_DIR, "shared")

EMOTION_TXT = os.path.join(SHARED_DIR, "emotion.txt")
STATUS_TXT = os.path.join(SHARED_DIR, "status.txt")
REPLY_TXT = os.path.join(SHARED_DIR, "reply_text.txt")
AVATAR_CONNECTED_TXT = os.path.join(SHARED_DIR, "avatar_connected.txt")
AVATAR_STATUS_JSON = os.path.join(SHARED_DIR, "avatar_status.json")
AVATAR_FRAME_PATH = os.path.join(BASE_DIR, "static", "avatar_frame.jpg")
LOAD_AVATAR_TXT = os.path.join(SHARED_DIR, "load_avatar.txt")
# Sentinel: animation trigger from VivyAnimationPlanner (via run_vivy.py _SentinelBridge)
ANIMATION_TRIGGER_TXT = os.path.join(SHARED_DIR, "animation_trigger.txt")
# Sentinel: lip sync trigger written immediately before sd.play() for timing accuracy
LIP_SYNC_TRIGGER_TXT  = os.path.join(SHARED_DIR, "lip_sync_trigger.txt")
VIEWPORT_TXT = os.path.join(SHARED_DIR, "viewport.txt")
WEB_INTERACTION_TXT = os.path.join(SHARED_DIR, "web_interaction.txt")
# Sentinel: Circadian Intelligence System state (written by run_vivy.py after each reply)
CIRCADIAN_STATE_JSON = os.path.join(SHARED_DIR, "circadian_state.json")
EMOTION_STATE_JSON = os.path.join(SHARED_DIR, "emotion_state.json")

import mmap
import struct

# Initialize named shared memory block (2MB) for passing frame bytes in RAM
try:
    _shmem = mmap.mmap(-1, 2 * 1024 * 1024, tagname="VivyAvatarFrame")
except Exception as e:
    print(f"[AvatarBridge] WARNING: Failed to create shared memory block: {e}")
    _shmem = None

_frame_count = 0
_frame_fps_window_start = 0.0  # For FPS measurement window
_frame_fps_window_count = 0    # Frames in current FPS window
_current_measured_fps = 0.0
_last_frame_timestamp = 0.0

# Connected clients state
_connected_clients = set()
_unity_clients = set()
_lock = threading.Lock()
_event_loop = None

# Shared file state monitors
_last_emotion = ""
_last_status = ""
_last_reply_mtime = 0.0
_last_load_avatar_mtime = 0.0

def _update_avatar_status_file():
    """Write dynamic telemetry & status payload to avatar_status.json for Flask API."""
    try:
        os.makedirs(SHARED_DIR, exist_ok=True)
        is_streaming_active = (time.time() - _last_frame_timestamp < 5.0) if _last_frame_timestamp > 0 else False
        count = len(_unity_clients) if _unity_clients else (1 if is_streaming_active else (len(_connected_clients) if is_streaming_active else 0))
        status_label = "STREAMING" if (count > 0 or is_streaming_active) else "STANDBY"
        root_cause = (
            f"Connected to {count} MateEngine Unity client(s)"
            if (count > 0 or is_streaming_active) else
            "WebSocket server listening on ws://127.0.0.1:8765; waiting for MateEngine client to connect"
        )
        
        payload = {
            "status": status_label,
            "connected": (count > 0 or is_streaming_active),
            "client_count": count,
            "measured_fps": round(_current_measured_fps, 1),
            "last_frame_timestamp": _last_frame_timestamp,
            "root_cause": root_cause,
            "reconnect_active": True,
            "timestamp": time.time()
        }
        tmp_path = AVATAR_STATUS_JSON + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_path, AVATAR_STATUS_JSON)
    except Exception as e:
        print(f"[AvatarBridge] Error updating status file: {e}")


def _save_avatar_frame(base64_str):
    """Decode incoming base64 frame from Unity and save to static/avatar_frame.jpg."""
    global _frame_count, _frame_fps_window_count, _frame_fps_window_start, _current_measured_fps, _last_frame_timestamp
    try:
        img_data = base64.b64decode(base64_str)
        _last_frame_timestamp = time.time()
        
        # Save to shared memory (RAM) instantly
        if _shmem is not None:
            try:
                _shmem.seek(0)
                _shmem.write(struct.pack("<II", len(img_data), _frame_count))
                _shmem.write(img_data)
                _shmem.flush()
            except Exception as e:
                print(f"[AvatarBridge] Error writing to shared memory: {e}")
        
        # Throttle saving to disk: only write once every 30 frames and do it asynchronously
        # to avoid blocking the main WebSocket loop thread.
        if _frame_count % 30 == 0:
            def _write_disk_async():
                try:
                    os.makedirs(os.path.dirname(AVATAR_FRAME_PATH), exist_ok=True)
                    temp_path = AVATAR_FRAME_PATH + ".tmp"
                    with open(temp_path, "wb") as f:
                        f.write(img_data)
                    os.replace(temp_path, AVATAR_FRAME_PATH)
                except Exception as de:
                    print(f"[AvatarBridge] Background write to disk failed: {de}")
            threading.Thread(target=_write_disk_async, daemon=True).start()
            
        _frame_count += 1
        _frame_fps_window_count += 1

        now = time.time()
        if _frame_fps_window_start == 0.0:
            _frame_fps_window_start = now

        # Log FPS every 30 frames (or every ~5 seconds at 5 FPS)
        window_elapsed = now - _frame_fps_window_start
        if _frame_fps_window_count >= 30 and window_elapsed > 0:
            _current_measured_fps = _frame_fps_window_count / window_elapsed
            # Silenced telemetry logs to prevent console flooding
            _frame_fps_window_start = now
            _frame_fps_window_count = 0
            _update_avatar_status_file()
        elif _frame_count % 10 == 0:
            pass # Silenced frame logs
    except Exception as e:
        print(f"[AvatarBridge] Error saving avatar frame: {e}")


def _update_connected_file():
    """Write current connection count to avatar_connected.txt for Flask app status checks."""
    try:
        os.makedirs(SHARED_DIR, exist_ok=True)
        tmp = AVATAR_CONNECTED_TXT + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(str(len(_connected_clients)))
        os.replace(tmp, AVATAR_CONNECTED_TXT)
        _update_avatar_status_file()
    except Exception as e:
        print(f"[AvatarBridge] Error updating connection file: {e}")


# =====================================================
# WEBSOCKET SERVER HANDLER
# =====================================================
async def _handle_client(websocket):
    """Handle a single client connection (Unity or Browser)."""
    client_addr = websocket.remote_address
    print(f"[AvatarBridge] Client connected: {client_addr}")

    with _lock:
        _connected_clients.add(websocket)
        _update_connected_file()

    try:
        # Send current state on connect
        current_emotion = _read_file(EMOTION_TXT) or "neutral"
        current_status = _read_file(STATUS_TXT) or "ready"
        await websocket.send(json.dumps({"type": "emotion", "value": current_emotion}))
        await websocket.send(json.dumps({"type": "status", "value": current_status}))

        # Send current viewport size on connect if available
        viewport_val = _read_file(VIEWPORT_TXT)
        if viewport_val and "," in viewport_val:
            try:
                w, h = map(int, viewport_val.split(","))
                await websocket.send(json.dumps({"type": "resize", "width": w, "height": h}))
                print(f"[AvatarBridge] Sent initial viewport size to client on connection: {w}x{h}")
            except Exception as ve:
                print(f"[AvatarBridge] Failed to send initial resize on connect: {ve}")

        # Listen for messages from Unity or Browser
        async for message in websocket:
            try:
                t_start = time.time()
                data = json.loads(message)
                deser_time = (time.time() - t_start) * 1000.0
                msg_type = data.get("type", "")

                # Developer Diagnostic Mode Hook (Phase 4 Instrumentation)
                try:
                    from developer_diagnostic_manager import get_developer_diagnostic_manager
                    ddm = get_developer_diagnostic_manager()
                    if ddm.is_enabled():
                        ddm.record_ws_packet(
                            direction="INCOMING",
                            message_type=msg_type,
                            payload_size=len(message),
                            deser_time_ms=deser_time,
                            status="OK",
                            data_preview={"type": msg_type, "value": str(data.get("value") or data.get("text", ""))[:40]}
                        )
                except Exception as _err:
                    print(f"[avatar_bridge.py] Silenced exception: {_err}")

                # Broadcast browser-originated commands directly to Unity (and other clients)
                if msg_type in ("camera", "lookAt", "interaction", "emotion", "resize", "load_avatar", "speak", "sync_pose"):
                    await _broadcast(data, exclude_ws=websocket)

                elif msg_type == "ready":
                    with _lock:
                        _unity_clients.add(websocket)
                        _update_connected_file()
                    print(f"[AvatarBridge] Unity client is ready: {client_addr}")

                elif msg_type == "frame":
                    if websocket not in _unity_clients:
                        with _lock:
                            _unity_clients.add(websocket)
                            _update_connected_file()
                    frame_data = data.get("data", "")
                    if frame_data:
                        _save_avatar_frame(frame_data)

                else:
                    # Avoid spamming console with frame logs, only log unknown non-frame types
                    print(f"[AvatarBridge] Unknown message: {msg_type}")

            except json.JSONDecodeError:
                print(f"[AvatarBridge] Invalid JSON: {message}")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        with _lock:
            _connected_clients.discard(websocket)
            _unity_clients.discard(websocket)
            _update_connected_file()
        print(f"[AvatarBridge] Client disconnected: {client_addr}")


# =====================================================
# BROADCAST HELPERS
# =====================================================
async def _broadcast(message_dict, exclude_ws=None):
    """Send a JSON message to all connected clients, optionally excluding one."""
    if not _connected_clients:
        return

    t_start = time.time()
    msg = json.dumps(message_dict)
    ser_time = (time.time() - t_start) * 1000.0
    msg_type = message_dict.get("type", "unknown")

    # Developer Diagnostic Mode Hook (Phase 4 & 5 Instrumentation)
    try:
        from developer_diagnostic_manager import get_developer_diagnostic_manager
        ddm = get_developer_diagnostic_manager()
        if ddm.is_enabled():
            ddm.record_ws_packet(
                direction="OUTGOING",
                message_type=msg_type,
                payload_size=len(msg),
                ser_time_ms=ser_time,
                status="OK",
                data_preview={"type": msg_type, "value": str(message_dict.get("value") or message_dict.get("text", ""))[:40]}
            )
            if msg_type in ("animation", "emotion", "speak", "emotion_state"):
                ddm.record_animation(
                    current_anim=str(message_dict.get("value", "Idle")),
                    prev_anim="",
                    next_anim="",
                    animator_state="Playing",
                    animator_layer=0,
                    blend_weight=1.0,
                    transition_progress=1.0,
                    queue=[],
                    interruptions=0
                )
    except Exception as _err:
        print(f"[avatar_bridge.py] Silenced exception: {_err}")

    with _lock:
        clients = list(_connected_clients)

    disconnected = []
    for ws in clients:
        if ws == exclude_ws:
            continue
        try:
            await ws.send(msg)
        except websockets.exceptions.ConnectionClosed:
            disconnected.append(ws)

    if disconnected:
        with _lock:
            for ws in disconnected:
                _connected_clients.discard(ws)
            _update_connected_file()


def push_emotion(emotion_label):
    """Push an emotion change to Unity. Called from run_vivy.py."""
    _schedule_broadcast({"type": "emotion", "value": emotion_label})


def push_status(status):
    """Push a pipeline status change to Unity. Called from run_vivy.py."""
    _schedule_broadcast({"type": "status", "value": status})


def push_speak(text):
    """Push speak text to Unity for lip sync. Called from run_vivy.py."""
    _schedule_broadcast({"type": "speak", "text": text})


def push_animation(animation_name):
    """Push an animation trigger to Unity."""
    _schedule_broadcast({"type": "animation", "value": animation_name})

def push_sync_pose(bones):
    """Push a full set of bones for direct animation via sync_pose."""
    _schedule_broadcast({"type": "sync_pose", "bones": bones})

def push_blendshape(name, weight):
    """Push a blendshape weight to Unity."""
    _schedule_broadcast({"type": "blendshape", "name": name, "weight": weight})


def push_look_at(x, y):
    """Push a look-at target to Unity."""
    _schedule_broadcast({"type": "lookAt", "x": x, "y": y})


def push_load_avatar(avatar_path):
    """Push a load avatar command to Unity."""
    _schedule_broadcast({"type": "load_avatar", "value": avatar_path})


def _schedule_broadcast(message_dict):
    """Thread-safe: schedule a broadcast on the event loop."""
    if _event_loop and _event_loop.is_running():
        asyncio.run_coroutine_threadsafe(_broadcast(message_dict), _event_loop)


def is_connected():
    """Return True if at least one Unity client is connected."""
    with _lock:
        return len(_connected_clients) > 0


def get_client_count():
    """Return the number of connected Unity clients."""
    with _lock:
        return len(_connected_clients)


# =====================================================
# FILE MONITORING (polls shared/ for state changes)
# =====================================================
def _read_file(path):
    """Read a small text file, return stripped content or empty string."""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception as _err:
        print(f"[avatar_bridge.py] Silenced exception: {_err}")
    return ""


async def _monitor_shared_files():
    """Background coroutine: polls shared files for changes and pushes to Unity."""
    global _last_emotion, _last_status, _last_reply_mtime, _last_load_avatar_mtime

    # New: mtime trackers for sentinel files
    _last_animation_trigger_mtime = 0.0
    _last_lip_sync_trigger_mtime  = 0.0
    _last_viewport_mtime          = 0.0
    _last_web_interaction_mtime   = 0.0
    _last_circadian_state_mtime   = 0.0

    while True:
        try:
            # Monitor emotion changes
            current_emotion = _read_file(EMOTION_TXT) or "neutral"
            if current_emotion != _last_emotion:
                _last_emotion = current_emotion
                await _broadcast({"type": "emotion", "value": current_emotion})

            # Monitor structured emotion_state.json contract changes
            if os.path.exists(EMOTION_STATE_JSON):
                mtime = os.path.getmtime(EMOTION_STATE_JSON)
                if mtime > getattr(_monitor_shared_files, "_last_emotion_state_mtime", 0.0):
                    _monitor_shared_files._last_emotion_state_mtime = mtime
                    try:
                        with open(EMOTION_STATE_JSON, "r", encoding="utf-8") as _esf:
                            _es_data = json.load(_esf)
                        await _broadcast({
                            "type": "emotion_state",
                            "data": _es_data
                        })
                    except Exception as _ese:
                        print(f"[AvatarBridge] Failed to parse emotion_state.json: {_ese}")

            # Monitor status changes
            current_status = _read_file(STATUS_TXT) or "ready"
            if current_status != _last_status:
                _last_status = current_status
                await _broadcast({"type": "status", "value": current_status})

            # Monitor reply text changes (for lip sync)
            if os.path.exists(REPLY_TXT):
                mtime = os.path.getmtime(REPLY_TXT)
                if mtime > _last_reply_mtime:
                    _last_reply_mtime = mtime
                    text = _read_file(REPLY_TXT)
                    if text:
                        await _broadcast({"type": "speak", "text": text})

            # Monitor load avatar command changes
            if os.path.exists(LOAD_AVATAR_TXT):
                mtime = os.path.getmtime(LOAD_AVATAR_TXT)
                if mtime > _last_load_avatar_mtime:
                    _last_load_avatar_mtime = mtime
                    avatar_val = _read_file(LOAD_AVATAR_TXT)
                    if avatar_val:
                        await _broadcast({"type": "load_avatar", "value": avatar_val})

            # Monitor animation_trigger.txt — written by VivyAnimationPlanner
            # Forwards the trigger name to Unity as an "animation" message.
            if os.path.exists(ANIMATION_TRIGGER_TXT):
                mtime = os.path.getmtime(ANIMATION_TRIGGER_TXT)
                if mtime > _last_animation_trigger_mtime:
                    _last_animation_trigger_mtime = mtime
                    trigger_val = _read_file(ANIMATION_TRIGGER_TXT)
                    if trigger_val:
                        await _broadcast({"type": "animation", "value": trigger_val})

            # Monitor lip_sync_trigger.txt — written by run_vivy.py immediately
            # before sd.play() for accurate audio-aligned lip sync.
            # This takes priority over the reply_text.txt monitor for voice turns:
            # the reply_text.txt monitor still handles text-only (dashboard) turns.
            if os.path.exists(LIP_SYNC_TRIGGER_TXT):
                mtime = os.path.getmtime(LIP_SYNC_TRIGGER_TXT)
                if mtime > _last_lip_sync_trigger_mtime:
                    _last_lip_sync_trigger_mtime = mtime
                    lip_text = _read_file(LIP_SYNC_TRIGGER_TXT)
                    if lip_text:
                        await _broadcast({"type": "speak", "text": lip_text})

            # Monitor viewport.txt — written by web_server.py
            if os.path.exists(VIEWPORT_TXT):
                mtime = os.path.getmtime(VIEWPORT_TXT)
                if mtime > _last_viewport_mtime:
                    _last_viewport_mtime = mtime
                    val = _read_file(VIEWPORT_TXT)
                    if val and "," in val:
                        try:
                            w, h = map(int, val.split(","))
                            await _broadcast({"type": "resize", "width": w, "height": h})
                        except Exception as _err:
                            print(f"[avatar_bridge.py] Silenced exception: {_err}")

            # Monitor web_interaction.txt — written by web_server.py
            if os.path.exists(WEB_INTERACTION_TXT):
                mtime = os.path.getmtime(WEB_INTERACTION_TXT)
                if mtime > _last_web_interaction_mtime:
                    _last_web_interaction_mtime = mtime
                    val = _read_file(WEB_INTERACTION_TXT)
                    if val:
                        try:
                            cmd_data = json.loads(val)
                            await _broadcast(cmd_data)
                        except Exception as e:
                            print(f"[AvatarBridge] Failed to parse web command: {e}")

            # Monitor circadian_state.json — written by run_vivy.py after each reply
            # Pushes circadian energy and phase to Unity for avatar modulation.
            if os.path.exists(CIRCADIAN_STATE_JSON):
                mtime = os.path.getmtime(CIRCADIAN_STATE_JSON)
                if mtime > _last_circadian_state_mtime:
                    _last_circadian_state_mtime = mtime
                    try:
                        with open(CIRCADIAN_STATE_JSON, "r", encoding="utf-8") as _csf:
                            _cs_data = json.loads(_csf.read())
                        await _broadcast({
                            "type":          "circadian",
                            "phase":         _cs_data.get("phase", "Afternoon"),
                            "energy":        _cs_data.get("avatar_energy", 0.70),
                            "sleep_mode":    _cs_data.get("sleep_mode", False),
                            "hardware_hint": _cs_data.get("hardware_hint", "gpu"),
                        })
                    except Exception as _ce:
                        print(f"[AvatarBridge] Failed to parse circadian_state.json: {_ce}")

            # Monitor perception_state.json for real-time Avatar Eye Synchronization & LookAt tracking
            perception_state_file = os.path.join(SHARED_DIR, "perception_state.json")
            if os.path.exists(perception_state_file):
                pm_mtime = os.path.getmtime(perception_state_file)
                if pm_mtime > getattr(_monitor_shared_files, "_last_perception_state_mtime", 0.0):
                    _monitor_shared_files._last_perception_state_mtime = pm_mtime
                    try:
                        with open(perception_state_file, "r", encoding="utf-8") as _psf:
                            _ps_data = json.load(_psf)
                        gaze_info = _ps_data.get("face_perception_data", {}).get("gaze", {})
                        pupil_target = gaze_info.get("pupil_target", {})
                        target_x = pupil_target.get("x", 0.5)
                        target_y = pupil_target.get("y", 0.5)
                        if target_x is not None and target_y is not None:
                            if target_x <= 0.01 and target_y <= 0.01:
                                target_x, target_y = 0.5, 0.5
                            await _broadcast({
                                "type": "lookAt",
                                "x": target_x,
                                "y": target_y,
                                "eye_contact_score": gaze_info.get("eye_contact_score", 1.0)
                            })
                    except Exception as _err:
                        print(f"[avatar_bridge.py] Silenced exception: {_err}")


        except Exception as e:
            print(f"[AvatarBridge] Monitor error: {e}")

        await asyncio.sleep(0.05)


# =====================================================
# SERVER STARTUP
# =====================================================
async def _run_server():
    """Main async entry point: start WebSocket server + file monitor."""
    global _event_loop
    _event_loop = asyncio.get_running_loop()

    # Initialize connection status file to 0 on startup
    _update_connected_file()

    print("[AvatarBridge] Starting WebSocket server on ws://127.0.0.1:8765 ...")

    # Start file monitor as background task
    monitor_task = asyncio.create_task(_monitor_shared_files())

    async with websockets.serve(_handle_client, "127.0.0.1", 8765):
        print("[AvatarBridge] WebSocket server is READY. Waiting for Unity client...")
        await asyncio.Future()  # Run forever


def start_server_blocking():
    """Start the avatar bridge server (blocking call). Use for standalone mode."""
    try:
        asyncio.run(_run_server())
    except KeyboardInterrupt:
        print("\n[AvatarBridge] Shutting down.")


def start_server_thread():
    """Start the avatar bridge server in a background daemon thread.
    Use when importing from run_vivy.py."""
    global _event_loop

    def _thread_target():
        asyncio.run(_run_server())

    t = threading.Thread(target=_thread_target, daemon=True, name="AvatarBridge")
    get_resource_manager().register_thread(t, name="AvatarBridge")
    t.start()
    # Give the event loop a moment to initialize
    time.sleep(0.5)
    return t


# =====================================================
# STANDALONE ENTRY POINT
# =====================================================
if __name__ == "__main__":
    print("=" * 52)
    print("  Vivy Avatar Bridge — WebSocket Server")
    print("  Connects Vivy AI Pipeline -> Unity Avatar Runtime")
    print("  ws://127.0.0.1:8765")
    print("=" * 52)
    start_server_blocking()
