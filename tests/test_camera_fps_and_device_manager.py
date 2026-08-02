"""
tests/test_camera_fps_and_device_manager.py
=============================================
Automated test suite verifying Vivy AI camera performance & device manager fixes:
- Decoupled asynchronous perception worker execution
- High-speed camera frame ingestion throughput (30-45+ FPS)
- DirectShow lock-free device enumeration (/api/camera/devices)
- Manual control state sentinel checks (camera_disable.txt)
"""

import os
import sys
import time
import base64
import unittest
import numpy as np

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


class TestCameraFpsAndDeviceManager(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from perception.camera_manager import set_camera_disabled
        set_camera_disabled(False)

    @classmethod
    def tearDownClass(cls):
        from perception.camera_manager import get_camera_manager, set_camera_disabled
        cm = get_camera_manager()
        cm.stop_camera()
        set_camera_disabled(False)

    def test_01_asynchronous_perception_worker(self):
        """Verify CameraManager background perception worker thread initializes and runs asynchronously."""
        from perception.camera_manager import get_camera_manager
        cm = get_camera_manager()

        self.assertIsNotNone(cm)
        cm.start_camera()

        self.assertTrue(hasattr(cm, "_perception_worker_thread"))
        self.assertTrue(hasattr(cm, "_perception_worker_running"))
        self.assertTrue(cm._perception_worker_running)

    def test_02_high_fps_ingestion_throughput(self):
        """Verify frame ingestion throughput achieves 30-45+ FPS without blocking caller thread."""
        from perception.camera_manager import get_camera_manager
        cm = get_camera_manager()

        # Create a small valid synthetic JPEG base64 frame string
        import cv2
        img = np.full((120, 160, 3), 128, dtype=np.uint8)
        _, buf = cv2.imencode('.jpg', img)
        b64_str = base64.b64encode(buf.tobytes()).decode('ascii')

        start_t = time.time()
        num_frames = 40

        # Simulate high-rate frame ingestion (targeting 30-45 FPS throughput)
        for _ in range(num_frames):
            cm.ingest_external_frame(b64_str)

        elapsed = time.time() - start_t
        fps = num_frames / max(0.001, elapsed)

        print(f"\n[FPS Test] Ingested {num_frames} frames in {elapsed:.3f}s -> Throughput: {fps:.1f} FPS")

        # Ingestion must be fast and decoupled from ML inference (at least 30 FPS throughput)
        self.assertGreaterEqual(fps, 30.0, f"Frame ingestion throughput was {fps:.1f} FPS, expected >= 30 FPS")

    def test_03_device_enumeration_lock_safety(self):
        """Verify device enumeration avoids DirectShow driver collisions while capture is active."""
        from web_server import camera_devices, app

        with app.test_request_context('/api/camera/devices'):
            response = camera_devices()
            data = response.get_json()
            self.assertTrue(data.get("success"))
            self.assertIn("devices", data)
            self.assertIsInstance(data["devices"], list)
            self.assertGreaterEqual(len(data["devices"]), 1)

    def test_04_manual_camera_sentinel_toggle(self):
        """Verify camera sentinel (camera_disable.txt) cleanly prevents unprompted auto-activation."""
        from perception.camera_manager import get_camera_manager, set_camera_disabled, is_camera_disabled

        set_camera_disabled(True)
        self.assertTrue(is_camera_disabled())

        cm = get_camera_manager()
        active = cm.start_camera()
        self.assertFalse(active)
        self.assertFalse(cm.is_active())

        # Reset sentinel for normal operation
        set_camera_disabled(False)
        self.assertFalse(is_camera_disabled())


if __name__ == "__main__":
    unittest.main()
