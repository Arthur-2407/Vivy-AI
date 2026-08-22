import unittest
import asyncio
from hub.hub_manager import VivyHub
from hub.node.node_connection import NodeConnection
from hub.device_identity import DeviceProfile, DeviceRole

class TestHubNodeConnection(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hub = VivyHub.get_instance()
        self.hub._is_running = False
        if self.hub.ws_server._thread:
            self.hub.ws_server.stop()
        self.hub.start(disable_discovery=True, port=8799)
        await asyncio.sleep(0.5)

    async def asyncTearDown(self):
        self.hub.stop()
        await asyncio.sleep(0.2)

    async def test_node_connection_lifecycle(self):
        print("--- Starting test_node_connection_lifecycle ---")
        node_id = "tablet_node_02"
        session_key = "sk_mock456"
        self.hub.pairing._active_sessions[node_id] = session_key
        
        node_profile = DeviceProfile(device_id=node_id, device_type="tablet", role=DeviceRole.CONSUMER_NODE)
        self.hub.registry.register_device(node_profile)
        
        print("--- Connecting Node Lifecycle ---")
        conn = NodeConnection("127.0.0.1", 8799, node_id, session_key)
        await conn.connect()
        self.assertIsNotNone(conn.websocket)
        
        await conn.close()
        print("--- Finished test_node_connection_lifecycle ---")

    async def test_invalid_auth(self):
        print("--- Starting test_invalid_auth ---")
        conn = NodeConnection("127.0.0.1", 8799, "hacker_node", "invalid_key")
        with self.assertRaises(Exception):
            await conn.connect()
        print("--- Finished test_invalid_auth ---")

if __name__ == "__main__":
    asyncio.run(unittest.main())
