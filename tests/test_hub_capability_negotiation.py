import unittest
from hub.execution_orchestrator import ExecutionOrchestrator
from hub.capability_router import CapabilityRouter
from hub.capability_manifest import CapabilityManifest, ExecutionMode, LatencyClass
from hub.device_registry import DeviceRegistry
from hub.device_identity import DeviceProfile, DeviceRole

class TestHubCapabilityNegotiation(unittest.TestCase):
    def setUp(self):
        self.orchestrator = ExecutionOrchestrator.get_instance()
        self.router = CapabilityRouter.get_instance()
        self.registry = DeviceRegistry.get_instance()
        
        # Clear registry for clean test
        self.registry._devices.clear()

        # Mock Primary Host (Laptop)
        self.host = DeviceProfile(
            device_id="laptop_01",
            device_type="server",
            role=DeviceRole.PRIMARY_HOST,
            gpu_available=True,
            ram_mb=16000
        )
        self.registry.register_device(self.host)
        
        # Mock Phone
        self.phone = DeviceProfile(
            device_id="phone_01",
            device_type="mobile",
            role=DeviceRole.CONSUMER_NODE,
            gpu_available=False,
            ram_mb=4000,
            camera_available=True
        )
        self.registry.register_device(self.phone)
        
        # Mock Heavy Capability
        self.manifest = CapabilityManifest(
            capability_id="vision.gaze",
            version="1.0",
            provider="vivy.core",
            execution_modes=[ExecutionMode.LOCAL, ExecutionMode.REMOTE],
            latency_class=LatencyClass.REALTIME,
            requirements={"gpu": "required", "ram_mb": 8000}
        )
        self.router.register_manifest(self.manifest)

    def test_remote_delegation(self):
        # Phone requests execution. Phone lacks GPU and RAM. Should delegate to remote.
        success, executor, mode, lease_id = self.orchestrator.request_execution("vision.gaze", "phone_01")
        self.assertTrue(success)
        self.assertEqual(mode, ExecutionMode.REMOTE)
        self.assertEqual(executor, "laptop_01")
        self.assertIsNotNone(lease_id)

    def test_local_execution(self):
        # Laptop requests execution. Laptop has GPU and RAM. Should execute locally.
        success, executor, mode, lease_id = self.orchestrator.request_execution("vision.gaze", "laptop_01")
        self.assertTrue(success)
        self.assertEqual(mode, ExecutionMode.LOCAL)
        self.assertEqual(executor, "laptop_01")
        self.assertIsNone(lease_id)

if __name__ == "__main__":
    unittest.main()
