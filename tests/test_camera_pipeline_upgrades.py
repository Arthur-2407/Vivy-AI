"""
tests/test_camera_pipeline_upgrades.py
=======================================
Automated test suite verifying Vivy AI camera pre/post-processing pipeline upgrades:
- Adaptive camera frame pre-processing (CLAHE contrast & denoising)
- MediaPipe Hand tracking & hand-held object detection in ObjectDetector
- Hand state and held objects IPC state recording in PerceptionManager
- Live Perception Snapshot context injection formatting
- Conversation message classification for camera holding queries
"""

import os
import sys
import unittest
import numpy as np

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


class TestCameraPipelineUpgrades(unittest.TestCase):

    def test_01_camera_frame_preprocessing(self):
        """Test CameraManager.preprocess_camera_frame with synthetic image array."""
        from perception.camera_manager import get_camera_manager
        cm = get_camera_manager()

        # Create a synthetic 640x480 BGR image array
        synthetic_img = np.zeros((480, 640, 3), dtype=np.uint8)
        # Add gradient to simulate varying contrast
        synthetic_img[:, :] = np.linspace(20, 200, 640, dtype=np.uint8)[None, :, None]

        processed = cm.preprocess_camera_frame(synthetic_img)
        self.assertIsNotNone(processed)
        self.assertEqual(processed.shape, (480, 640, 3))
        self.assertEqual(processed.dtype, np.uint8)

    def test_02_object_and_hand_detector(self):
        """Test ObjectDetector initialization, MediaPipe Hands tracking, and hand state output."""
        from perception.object_detector import ObjectDetector, ObjectData, HandData

        detector = ObjectDetector()
        self.assertIsNotNone(detector)
        backend = detector.get_backend_name()
        self.assertTrue(len(backend) > 0)

        # Create a synthetic image for detection run
        test_img = np.full((480, 640, 3), 128, dtype=np.uint8)
        objects = detector.detect_objects(test_img)
        self.assertIsInstance(objects, list)

        hand_state = detector.get_hand_state()
        self.assertIsInstance(hand_state, dict)
        self.assertIn("hands_tracked", hand_state)
        self.assertIn("holding_detected", hand_state)

    def test_03_perception_manager_hand_ipc(self):
        """Test PerceptionManagerWriter and Reader for hand_state and held_objects state IPC."""
        from perception.perception_manager import get_writer, get_reader

        writer = get_writer()
        reader = get_reader()

        test_hand_state = {
            "hands_tracked": 1,
            "hands": [
                {
                    "hand_label": "Right",
                    "confidence": 0.95,
                    "holding_item": True,
                    "gesture": "Closed Fist / Holding"
                }
            ],
            "holding_detected": True,
            "holding_summary": "holding an item"
        }
        test_held_objects = [
            {
                "tracking_id": 1,
                "label": "item held in right hand",
                "confidence": 0.88,
                "category": "held_item",
                "validation_state": "hand_held"
            }
        ]

        writer.record_hand_perception_state(test_hand_state, test_held_objects)
        writer.record_camera_vlm_caption("User is holding a black smartphone in their right hand.")

        state = reader.load_state(force_reload=True)
        self.assertIn("hand_state", state)
        self.assertIn("held_objects", state)
        self.assertIn("camera_vlm_caption", state)
        self.assertEqual(state["camera_vlm_caption"], "User is holding a black smartphone in their right hand.")

    def test_04_context_injector_live_snapshot(self):
        """Test context_injector._build_live_snapshot output formatting for camera & hand context."""
        from perception.context_injector import _build_live_snapshot
        from perception.perception_manager import get_writer

        writer = get_writer()
        writer.record_camera_state(active=True, paused=False)
        writer.record_hand_perception_state(
            {
                "hands_tracked": 1,
                "hands": [{"hand_label": "Right", "gesture": "Holding", "holding_item": True}],
                "holding_detected": True
            },
            [{"label": "book or object", "confidence": 0.9}]
        )
        writer.record_camera_vlm_caption("User holding a blue book in front of camera.")

        snapshot = _build_live_snapshot(wants_vision=True, wants_audio=False)
        self.assertTrue(len(snapshot) > 0)
        self.assertIn("User Camera Status", snapshot)
        self.assertIn("Hand Tracking Status", snapshot)

    def test_05_conversation_classification_for_camera_queries(self):
        """Test conversation.classify_message categorizing camera holding queries."""
        from conversation import classify_message

        cats_holding = classify_message("what am i holding in my hand right now?")
        self.assertIn("camera_query", cats_holding)
        self.assertIn("screen", cats_holding)

        cats_see = classify_message("can u see me?")
        self.assertIn("camera_query", cats_see)
        self.assertIn("screen", cats_see)


if __name__ == "__main__":
    unittest.main()
