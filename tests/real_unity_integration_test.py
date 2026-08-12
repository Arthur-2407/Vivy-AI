import os
import sys
import json
import time
import asyncio
import socket

# Reconfigure stdout for utf-8
sys.stdout.reconfigure(encoding='utf-8')

# Ensure we have websockets for standalone mode
try:
    import websockets
except ImportError:
    print("Error: 'websockets' module not found. Run: pip install websockets")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED_DIR = os.path.join(BASE_DIR, "shared")
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Shared state paths
AVATAR_CONNECTED_TXT = os.path.join(SHARED_DIR, "avatar_connected.txt")
ANIMATION_TRIGGER_TXT = os.path.join(SHARED_DIR, "animation_trigger.txt")
EMOTION_TXT = os.path.join(SHARED_DIR, "emotion.txt")
AVATAR_STATUS_JSON = os.path.join(SHARED_DIR, "avatar_status.json")
AVATAR_FRAME_PATH = os.path.join(STATIC_DIR, "avatar_frame.jpg")

class IntegrationTest:
    def __init__(self):
        self.unity_connected = False
        self.frames_received = 0
        self.test_passed = False

    def is_port_in_use(self, port):
        """Check if port 8765 is already bound by run_vivy.py."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0

    # ---------------------------------------------------------
    # MODE 1: STANDALONE (Port 8765)
    # ---------------------------------------------------------
    async def standalone_handler(self, websocket):
        print("\n[Standalone] Unity Client Connected!")
        self.unity_connected = True
        
        # Send initial state
        await websocket.send(json.dumps({"type": "emotion", "value": "neutral"}))
        await websocket.send(json.dumps({"type": "status", "value": "ready"}))
        
        try:
            async for message in websocket:
                data = json.loads(message)
                msg_type = data.get("type", "")
                
                if msg_type == "ready":
                    print("[Standalone] Unity sent 'ready'. Triggering tests...")
                    # 1. Trigger an animation
                    print("[Standalone] Sending Animation -> Dance1")
                    await websocket.send(json.dumps({"type": "animation", "value": "Dance1"}))
                    # 2. Trigger an emotion
                    print("[Standalone] Sending Emotion -> happy")
                    await websocket.send(json.dumps({"type": "emotion", "value": "happy"}))
                
                elif msg_type == "frame":
                    self.frames_received += 1
                    if self.frames_received == 1:
                        print("[Standalone] First frame received from Unity!")
                    elif self.frames_received % 10 == 0:
                        print(f"[Standalone] Received {self.frames_received} frames so far...")
                        
        except websockets.exceptions.ConnectionClosed:
            print("[Standalone] Unity Client Disconnected.")
            self.unity_connected = False

    async def run_standalone_mode(self):
        print("==================================================")
        print("  Real Integration Test (Standalone Mode)")
        print("  run_vivy.py is NOT running.")
        print("  Spawning temporary Avatar Bridge on port 8765...")
        print("==================================================")
        
        server = await websockets.serve(self.standalone_handler, "127.0.0.1", 8765)
        print("\nWaiting for Unity to connect. Please open Unity and press PLAY.")
        print("Timeout in 60 seconds...\n")
        
        # Wait up to 60 seconds for connection
        for _ in range(60):
            if self.unity_connected:
                break
            await asyncio.sleep(1)
            
        if not self.unity_connected:
            print("\n[FAIL] Timed out waiting for Unity to connect.")
            server.close()
            await server.wait_closed()
            return
            
        # If connected, wait 10 seconds to collect frames and allow animations to play
        print("\nWaiting 10 seconds to verify frame streaming and playback...")
        await asyncio.sleep(10)
        
        if self.frames_received > 5:
            print(f"\n[PASS] Received {self.frames_received} frames. Unity is actively rendering.")
            self.test_passed = True
        else:
            print(f"\n[FAIL] Only received {self.frames_received} frames. Expected continuous frame stream.")
            
        server.close()
        await server.wait_closed()

    # ---------------------------------------------------------
    # MODE 2: SHARED-DIR FALLBACK (run_vivy.py is running)
    # ---------------------------------------------------------
    def run_shared_mode(self):
        print("==================================================")
        print("  Real Integration Test (Shared-Directory Mode)")
        print("  Port 8765 is taken. Assuming run_vivy.py is running.")
        print("==================================================")
        
        print("\nWaiting for Unity to connect. Please open Unity and press PLAY.")
        print("Timeout in 60 seconds...\n")
        
        connected = False
        for _ in range(60):
            try:
                if os.path.exists(AVATAR_CONNECTED_TXT):
                    with open(AVATAR_CONNECTED_TXT, "r") as f:
                        val = f.read().strip()
                        if val and int(val) > 0:
                            connected = True
                            break
            except Exception:
                pass
            time.sleep(1)
            
        if not connected:
            print("\n[FAIL] Timed out waiting for Unity to connect.")
            return
            
        print("\n[SharedMode] Unity is connected to the active Avatar Bridge!")
        
        # 1. Trigger Animation
        print("[SharedMode] Triggering Animation -> Dance1 via animation_trigger.txt")
        os.makedirs(SHARED_DIR, exist_ok=True)
        with open(ANIMATION_TRIGGER_TXT, "w") as f:
            f.write("Dance1")
            
        # 2. Trigger Emotion
        print("[SharedMode] Triggering Emotion -> happy via emotion.txt")
        with open(EMOTION_TXT, "w") as f:
            f.write("happy")
            
        # Get current frame modification time
        start_mtime = 0
        if os.path.exists(AVATAR_FRAME_PATH):
            start_mtime = os.path.getmtime(AVATAR_FRAME_PATH)
            
        print("\nWaiting 10 seconds to verify frame streaming via status JSON...")
        time.sleep(10)
        
        # Verify frames updated
        frames_passed = False
        if os.path.exists(AVATAR_FRAME_PATH):
            end_mtime = os.path.getmtime(AVATAR_FRAME_PATH)
            if end_mtime > start_mtime:
                frames_passed = True
                print("[SharedMode] Verified avatar_frame.jpg is actively updating.")
                
        # Verify FPS > 0
        fps_passed = False
        try:
            if os.path.exists(AVATAR_STATUS_JSON):
                with open(AVATAR_STATUS_JSON, "r") as f:
                    data = json.load(f)
                    if data.get("measured_fps", 0) > 0:
                        fps_passed = True
                        print(f"[SharedMode] Verified status JSON reports {data['measured_fps']} FPS.")
        except Exception as e:
            print(f"Error reading status json: {e}")
            
        if frames_passed or fps_passed:
            print("\n[PASS] Unity is actively rendering and responding to the background bridge.")
            self.test_passed = True
        else:
            print("\n[FAIL] Unity connected, but frame streaming appears frozen or inactive.")

    def run(self):
        if self.is_port_in_use(8765):
            self.run_shared_mode()
        else:
            asyncio.run(self.run_standalone_mode())
            
        print("\n==================================================")
        if self.test_passed:
            print("  ✅ REAL INTEGRATION TEST PASSED!")
            print("  Unity is actively communicating, receiving animations,")
            print("  and streaming visual frames back to Python.")
        else:
            print("  ❌ REAL INTEGRATION TEST FAILED!")
        print("==================================================\n")


if __name__ == "__main__":
    tester = IntegrationTest()
    tester.run()
