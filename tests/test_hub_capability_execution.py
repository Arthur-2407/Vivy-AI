import unittest
import asyncio
from hub.hub_manager import VivyHub
from hub.node.node_connection import NodeConnection
from hub.node.capability_client import CapabilityClient
from hub.device_identity import DeviceProfile, DeviceRole
from hub.capability_manifest import CapabilityManifest, ExecutionMode, LatencyClass

class TestHubCapabilityExecution(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hub = VivyHub.get_instance()
        self.hub._is_running = False
        if self.hub.ws_server._thread:
            self.hub.ws_server.stop()
        self.hub.start(disable_discovery=True, port=8801)
        await asyncio.sleep(0.5)

    async def asyncTearDown(self):
        self.hub.stop()
        await asyncio.sleep(0.2)

    async def test_end_to_end_gaze(self):
        print("--- Starting test_end_to_end_gaze ---")
        manifest = CapabilityManifest(
            capability_id="vision.gaze",
            version="1.0",
            provider="vivy.core",
            execution_modes=[ExecutionMode.LOCAL, ExecutionMode.REMOTE],
            latency_class=LatencyClass.REALTIME,
            requirements={"gpu": "required"}
        )
        self.hub.router.register_manifest(manifest)
        
        node_id = "test_phone_99"
        session_key = "sk_mock123"
        self.hub.pairing._active_sessions[node_id] = session_key 
        
        node_profile = DeviceProfile(device_id=node_id, device_type="mobile", role=DeviceRole.CONSUMER_NODE)
        self.hub.registry.register_device(node_profile)
        
        print("--- Connecting Node ---")
        conn = NodeConnection("127.0.0.1", 8801, node_id, session_key)
        await conn.connect()
        
        print("--- Requesting Capability ---")
        client = CapabilityClient(conn)
        result = await client.execute_remote("vision.gaze", {"image": "test"})
        
        print("--- Verifying Result ---")
        self.assertIn("gaze_x", result)
        self.assertEqual(result["faces_detected"], 0)
        
        await conn.close()
        print("--- Finished test_end_to_end_gaze ---")

if __name__ == "__main__":
    asyncio.run(unittest.main())
