import asyncio
import base64
import json
import time
import uuid
import cv2
import websockets
from zeroconf import Zeroconf, ServiceBrowser

# --- Configuration ---
DEVICE_ID = "physical_node_" + str(uuid.uuid4())[:8]
HUB_SERVICE_TYPE = "_vivy._tcp.local."
CAPABILITY = "vision.gaze"
FPS_TARGET = 2

class NodeClient:
    def __init__(self):
        self.hub_address = None
        self.hub_port = None
        self.zeroconf = Zeroconf()
        self.websocket = None
        self.running = True
        self.session_id = None
        
    def remove_service(self, zeroconf, type, name):
        pass

    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        if info:
            self.hub_address = ".".join(str(i) for i in info.addresses[0])
            self.hub_port = info.port
            print(f"[Discovery] Found Vivy Hub at ws://{self.hub_address}:{self.hub_port}")

    def update_service(self, zeroconf, type, name):
        pass

    async def connect_and_pair(self):
        print(f"[Node] Discovering Hub via mDNS ({HUB_SERVICE_TYPE})...")
        browser = ServiceBrowser(self.zeroconf, HUB_SERVICE_TYPE, self)
        
        while not self.hub_address:
            await asyncio.sleep(0.1)
            
        uri = f"ws://{self.hub_address}:{self.hub_port}"
        print(f"[Node] Connecting to {uri}")
        
        try:
            self.websocket = await websockets.connect(uri)
            print("[Node] Connected!")
            
            # Step 1: Send identify request
            identify_req = {
                "protocol": "vivy",
                "version": "1",
                "message_id": str(uuid.uuid4()),
                "type": "identity.request",
                "device_id": DEVICE_ID,
                "payload": {
                    "device_type": "node_prototype",
                    "hardware": ["camera"]
                }
            }
            await self.websocket.send(json.dumps(identify_req))
            
            resp_str = await self.websocket.recv()
            resp = json.loads(resp_str)
            
            if resp.get("type") == "pairing.challenge":
                print("\n[Node] HUB REQUIRES PAIRING.")
                print(f"Please check the Hub UI (run_vivy.py) for the PIN for device '{DEVICE_ID}'.")
                pin = input("Enter PIN: ").strip()
                
                pair_req = {
                    "protocol": "vivy",
                    "version": "1",
                    "message_id": str(uuid.uuid4()),
                    "type": "pairing.response",
                    "device_id": DEVICE_ID,
                    "payload": {"pin": pin}
                }
                await self.websocket.send(json.dumps(pair_req))
                resp_str = await self.websocket.recv()
                resp = json.loads(resp_str)
            
            if resp.get("type") == "identity.accept":
                self.session_id = resp.get("session_id")
                print(f"[Node] Authenticated! Session ID: {self.session_id}")
                return True
            else:
                print(f"[Node] Authentication failed: {resp}")
                return False
                
        except Exception as e:
            print(f"[Node] Connection error: {e}")
            return False

    async def capture_and_send_loop(self):
        print("[Node] Opening camera...")
        cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            print("[Node] Failed to open camera.")
            return

        print("[Node] Camera opened. Starting frame transmission...")
        
        while self.running:
            ret, frame = cap.read()
            if not ret:
                print("[Node] Failed to grab frame.")
                await asyncio.sleep(1)
                continue
                
            # Resize and encode to JPEG
            frame = cv2.resize(frame, (640, 480))
            # Flip horizontally for selfie view
            frame = cv2.flip(frame, 1)
            
            ret_encode, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if ret_encode:
                b64_str = base64.b64encode(buf.tobytes()).decode('ascii')
                
                # Send capability request
                req_id = str(uuid.uuid4())
                req = {
                    "protocol": "vivy",
                    "version": "1",
                    "message_id": req_id,
                    "type": "capability.request",
                    "device_id": DEVICE_ID,
                    "session_id": self.session_id,
                    "capability": CAPABILITY,
                    "payload": {
                        "image": b64_str
                    }
                }
                
                start_t = time.time()
                await self.websocket.send(json.dumps(req))
                
                try:
                    # Wait for response
                    resp_str = await asyncio.wait_for(self.websocket.recv(), timeout=2.0)
                    resp = json.loads(resp_str)
                    
                    if resp.get("type") == "capability.result" and resp.get("request_id") == req_id:
                        gaze = resp.get("payload", {})
                        latency = (time.time() - start_t) * 1000
                        print(f"[{latency:.1f}ms] Faces: {gaze.get('faces_detected', 0)} | "
                              f"Gaze: ({gaze.get('gaze_x', 0):.2f}, {gaze.get('gaze_y', 0):.2f}) | "
                              f"Direction: {gaze.get('gaze_direction', 'Unknown')} | "
                              f"Node: {resp.get('execution_node')} | Lease: {resp.get('lease_id')[:8] if resp.get('lease_id') else 'None'}")
                    else:
                        print(f"[Node] Received unexpected msg: {resp.get('type')} (Error: {resp.get('payload', {}).get('error')})")
                except asyncio.TimeoutError:
                    print("[Node] Request timed out.")
                except websockets.exceptions.ConnectionClosed:
                    print("[Node] Connection closed by Hub.")
                    break
                    
            await asyncio.sleep(1.0 / FPS_TARGET)
            
        cap.release()

async def main():
    client = NodeClient()
    if await client.connect_and_pair():
        await client.capture_and_send_loop()
        
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Node] Terminating.")
