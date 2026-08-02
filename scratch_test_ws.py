import asyncio
import websockets
import json
import base64

async def simulate_unity():
    uri = "ws://127.0.0.1:8765"
    async with websockets.connect(uri) as websocket:
        print("Connected to WebSocket bridge.")
        
        # Send ready handshake
        await websocket.send(json.dumps({"type": "ready"}))
        print("Sent ready message.")
        
        # Create a small dummy 1x1 white JPEG image in base64
        dummy_jpeg_base64 = (
            "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP////////////////////////"
            "////////////////////////////////////////////////////////////"
            "//wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQAB"
            "PxA="
        )
        
        # Send frame payload
        frame_payload = json.dumps({
            "type": "frame",
            "data": dummy_jpeg_base64
        })
        await websocket.send(frame_payload)
        print("Sent dummy frame.")
        
        # Keep connection open for 15 seconds
        for i in range(15):
            await asyncio.sleep(1)
            print(f"Still connected... {i+1}s")

if __name__ == "__main__":
    asyncio.run(simulate_unity())
