"""
Vivy Hub - Node Agent (Entry Point)
Simulates a lightweight client running on an Edge Device (e.g. Phone).
"""
import asyncio
import sys
from hub.node.node_connection import NodeConnection
from hub.node.capability_client import CapabilityClient

async def main():
    print("=== Vivy Node Agent Started ===")
    
    # In reality, mDNS discovery would find the IP/port, and PairingManager would provide the key.
    # For simulation, we assume local host and a pre-shared test key that the test suite sets up.
    host = "127.0.0.1"
    port = 8766
    device_id = "phone_node_01"
    session_key = "sk_test_key"
    
    connection = NodeConnection(host, port, device_id, session_key)
    try:
        await connection.connect()
    except Exception as e:
        print(f"Could not connect to Vivy Hub at {host}:{port}: {e}")
        sys.exit(1)
        
    client = CapabilityClient(connection)
    
    print("\n[Node] Capturing mock camera frame for vision.gaze...")
    mock_frame_payload = {"image_bytes": "base64_encoded_mock_data"}
    
    try:
        result = await client.execute_remote("vision.gaze", mock_frame_payload)
        print("\n[Node] Received Gaze Result from Hub:")
        print(f"       Gaze X: {result.get('gaze_x')}")
        print(f"       Gaze Y: {result.get('gaze_y')}")
        print(f"       Confidence: {result.get('confidence')}")
    except Exception as e:
        print(f"\n[Node] Capability request failed: {e}")
        
    print("\n=== Vivy Node Agent Shutting Down ===")
    await connection.close()

if __name__ == "__main__":
    asyncio.run(main())
