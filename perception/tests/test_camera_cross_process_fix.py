"""
perception/tests/test_camera_cross_process_fix.py
==================================================
Verifies that external camera frame ingestion in web_server.py process
is correctly preserved and NOT overwritten by runner.py when local camera capture is idle.
"""

import os
import sys
import time
import unittest
import numpy as np

from perception.camera_manager import get_camera_manager
from perception.perception_manager import get_writer, get_reader
from perception.runner import get_perception_runner
from perception.face_detector import FaceDetector, FaceData, BoundingBox


class TestCameraCrossProcessFix(unittest.TestCase):

    def setUp(self):
        from perception.camera_manager import set_camera_disabled
        set_camera_disabled(False)
        self.writer = get_writer()
        self.reader = get_reader()
        self.runner = get_perception_runner()
        self.runner.stop()  # Stop any background thread from previous tests
        
        self.old_writer_path = self.writer._state_path
        self.old_reader_path = self.reader._state_path
        test_path = self.old_writer_path + ".test.json"
        self.writer._state_path = test_path
        self.reader._state_path = test_path

    def tearDown(self):
        self.writer._state_path = self.old_writer_path
        self.reader._state_path = self.old_reader_path
        try:
            if os.path.exists(self.writer._state_path + ".test.json"):
                os.remove(self.writer._state_path + ".test.json")
        except OSError:
            pass

    def test_shared_frame_and_state_preservation(self):
        writer = get_writer()
        reader = get_reader()
        cam = get_camera_manager()

        # 1. Simulate web_server.py receiving a camera frame and detecting a face
        face_state = {
            "camera_active": True,
            "presence_state": "User Present",
            "face_count": 1,
            "primary_face": {
                "tracking_id": 1,
                "bbox": {"x": 50, "y": 50, "width": 100, "height": 100},
                "confidence": 0.95,
                "head_pose": {"orientation_label": "Head Facing Vivy"}
            },
            "gaze": {"gaze_direction": "Looking At Vivy", "eye_contact_score": 0.92, "eye_contact_strength": "Strong"},
            "attention": {"attention_score": 90.0, "engagement_score": 85.0, "presence_score": 95.0},
            "hardware": {"backend": "CPU", "mode": "Live Perception Active"}
        }

        # Record active state as web_server.py would
        writer.record_face_perception_state(face_state)
        writer._flush_to_disk()

        # 2. Verify reader sees the active state
        st = reader.load_state(force_reload=True)
        self.assertTrue(st.get("camera_active"))
        self.assertEqual(st.get("face_count"), 1)
        self.assertEqual(st.get("presence_state"), "User Present")

        # 3. Simulate runner.py ticking when local camera returns img_np = None
        runner = get_perception_runner()
        runner._process_single_frame_sync()

        # 4. Verify runner.py yielded and DID NOT overwrite face_count to 0 or presence_state to User Missing / Camera OFF
        st_after = reader.load_state(force_reload=True)
        self.assertTrue(st_after.get("camera_active"))
        self.assertEqual(st_after.get("face_count"), 1)
        self.assertEqual(st_after.get("presence_state"), "User Present")

    def test_base64_decoding_with_padding_fix(self):
        detector = FaceDetector()
        # Unpadded base64 JPEG fragment
        unpadded_b64 = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP"
        img_np, h, w = detector._to_numpy_bgr(unpadded_b64)
        # Should decode gracefully or handle without raising Exception
        self.assertTrue(img_np is None or isinstance(img_np, np.ndarray))


if __name__ == "__main__":
    unittest.main()
