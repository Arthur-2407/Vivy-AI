"""
perception/tests/test_face_gaze_perception.py
===============================================
Automated Test Suite for Vivy AI Face & Gaze Perception System.
Tests:
  - Perception State Data Models
  - Event Bus Publishing and Subscribing
  - CPU/GPU Adaptive Hardware Scheduler
  - Camera Manager and Frame Ingestion
  - Frame Processing Scheduler
  - Face Detector, Tracker, Landmark Mesh
  - Gaze, Eye Contact, Blink & Head Pose Engine
  - Attention, Engagement & Presence Estimator
  - Presence State Machine Transitions
  - Emotion Vector Modulation
  - PerceptionManager Reader & Grounding Context Integration
"""

import os
import sys
import time
import unittest
import numpy as np

from perception.perception_state import (
    FaceData,
    BoundingBox,
    Point3D,
    HeadPose,
    EyeData,
    GazeData,
    AttentionData,
    HardwareSchedulerState,
    PerceptionSystemState,
)
from perception.perception_events import (
    get_event_hub,
    EVENT_PRESENCE_DETECTED,
    EVENT_PRESENCE_LOST,
    EVENT_USER_RETURNED,
)
from perception.hardware_scheduler import get_hardware_scheduler, PREF_AUTO, PREF_CPU, PREF_GPU
from perception.camera_manager import get_camera_manager
from perception.frame_scheduler import get_frame_scheduler
from perception.face_detector import FaceDetector
from perception.face_tracker import FaceTracker
from perception.landmark_detector import LandmarkDetector
from perception.gaze_detector import GazeDetector
from perception.attention_estimator import AttentionEstimator
from perception.presence_manager import PresenceManager
from perception.perception_manager import get_writer, get_reader
from emotion.emotion import modulate_emotion_with_perception


class TestFaceGazePerception(unittest.TestCase):

    def test_01_perception_state_data_models(self):
        """Verify data models and dictionary serialization."""
        bbox = BoundingBox(x=10, y=20, width=100, height=120)
        pt = Point3D(x=1.2, y=3.4, z=5.6)
        hp = HeadPose(yaw=5.0, pitch=-2.0, roll=0.0, orientation_label="Head Facing Vivy")
        face = FaceData(
            tracking_id=1,
            bbox=bbox,
            confidence=0.95,
            center_point=pt,
            distance_estimate=0.8,
            head_pose=hp,
            identity="User",
            is_primary=True,
        )

        face_dict = face.to_dict()
        self.assertEqual(face_dict["tracking_id"], 1)
        self.assertEqual(face_dict["bbox"]["x"], 10)
        self.assertEqual(face_dict["confidence"], 0.95)
        self.assertEqual(face_dict["head_pose"]["orientation_label"], "Head Facing Vivy")

    def test_02_perception_events_pub_sub(self):
        """Verify event bus pub-sub mechanism."""
        hub = get_event_hub()
        received_events = []

        def callback(event_type, payload):
            received_events.append((event_type, payload))

        hub.subscribe(EVENT_PRESENCE_DETECTED, callback)
        hub.publish(EVENT_PRESENCE_DETECTED, {"face_count": 1}, async_dispatch=False)

        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0][0], EVENT_PRESENCE_DETECTED)
        self.assertEqual(received_events[0][1]["face_count"], 1)

        hub.unsubscribe(EVENT_PRESENCE_DETECTED, callback)

    def test_03_hardware_scheduler_policy(self):
        """Verify adaptive hardware scheduler mode switching and task assignments."""
        hw = get_hardware_scheduler()

        # Test Avatar OFF Mode -> CPU preferred
        hw.update_avatar_state(False)
        hw.update_llm_state(False)

        assign_det = hw.get_assignment("face_detection")
        self.assertEqual(assign_det, "cpu")
        self.assertIn("Avatar OFF Mode", hw.get_state().mode)

        # Test User Preference override
        hw.set_user_preference(PREF_CPU)
        self.assertEqual(hw.get_assignment("face_detection"), "cpu")
        hw.set_user_preference(PREF_AUTO)

    def test_04_camera_manager_ingestion(self):
        """Verify CameraManager frame ingestion and active status."""
        from perception.camera_manager import set_camera_disabled
        set_camera_disabled(False)
        cam = get_camera_manager()
        # Synthetic base64 JPEG string header
        b64_dummy = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP"
        cam.ingest_external_frame(b64_dummy)

        self.assertTrue(cam.is_active())
        frame_b64, frame_t = cam.get_latest_frame()
        self.assertEqual(frame_b64, "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP")
        self.assertGreater(frame_t, 0.0)

    def test_05_face_detector_and_tracker(self):
        """Verify FaceDetector and FaceTracker with synthetic input image."""
        detector = FaceDetector()
        tracker = FaceTracker()

        # Create 300x300 RGB synthetic image with a clear face-like box
        img = np.zeros((300, 300, 3), dtype=np.uint8)
        img[50:200, 80:220] = [200, 180, 160] # flesh-tone rectangle

        faces = detector.detect_faces(img)
        # Even if neural detector returns 0 on synthetic box, detector object returns a list
        self.assertIsInstance(faces, list)

        # Test tracking logic with synthetic FaceData
        dummy_face = FaceData(
            tracking_id=1,
            bbox=BoundingBox(x=50, y=50, width=100, height=100),
            confidence=0.9,
            is_primary=True,
        )
        tracked = tracker.update([dummy_face])
        self.assertEqual(len(tracked), 1)
        self.assertEqual(tracked[0].tracking_id, 1)

    def test_06_landmark_detector_and_gaze_engine(self):
        """Verify LandmarkDetector and GazeDetector calculations."""
        landmarks = LandmarkDetector()
        gaze_engine = GazeDetector()

        face = FaceData(
            tracking_id=1,
            bbox=BoundingBox(x=50, y=50, width=100, height=100),
            confidence=0.9,
            head_pose=HeadPose(yaw=0.0, pitch=0.0, roll=0.0, orientation_label="Head Facing Vivy"),
            is_primary=True,
        )

        img = np.zeros((200, 200, 3), dtype=np.uint8)
        processed_faces = landmarks.process_landmarks(img, [face])
        self.assertEqual(len(processed_faces), 1)

        gaze_data = gaze_engine.estimate_gaze(processed_faces, 200, 200)
        self.assertIn(gaze_data.gaze_direction, ("Looking At Vivy", "Eyes Closed", "Looking At Screen", "Unknown"))
        self.assertGreaterEqual(gaze_data.eye_contact_score, 0.0)

    def test_07_attention_estimator_and_presence_manager(self):
        """Verify AttentionEstimator scores and PresenceManager state machine transitions."""
        attention_engine = AttentionEstimator()
        presence_engine = PresenceManager(missing_grace_seconds=0.1)

        face = FaceData(
            tracking_id=1,
            bbox=BoundingBox(x=50, y=50, width=100, height=100),
            confidence=0.95,
            head_pose=HeadPose(yaw=0.0, pitch=0.0, roll=0.0, orientation_label="Head Facing Vivy"),
            is_primary=True,
        )

        gaze = GazeData(gaze_direction="Looking At Vivy", eye_contact_score=0.9, eye_contact_strength="Strong")

        att_data, primary = attention_engine.estimate_attention([face], gaze, camera_active=True)
        self.assertGreaterEqual(att_data.attention_score, 70.0)
        self.assertGreaterEqual(att_data.presence_score, 80.0)
        self.assertIsNotNone(primary)

        # Test Presence State transitions
        p_state1 = presence_engine.update_presence([face], camera_active=True)
        self.assertIn(p_state1, ("User Present", "User Returned"))

        # Test User Missing after grace period
        time.sleep(0.15)
        p_state2 = presence_engine.update_presence([], camera_active=True)
        self.assertEqual(p_state2, "User Missing")

    def test_08_emotion_modulation(self):
        """Verify perception-driven emotion vector modulation."""
        base_emotion = "happy"
        perception_state = {
            "presence_state": "User Present",
            "gaze_direction": "Looking At Vivy",
            "eye_contact_score": 0.90,
            "attention_score": 95.0,
        }

        vector = modulate_emotion_with_perception(base_emotion, perception_state)
        self.assertEqual(vector["primary_label"], "happy")
        self.assertGreaterEqual(vector["confidence"], 80.0) # boosted by high eye contact
        self.assertGreaterEqual(vector["initiative"], 80.0)

    def test_09_perception_manager_reader_grounding_context(self):
        """Verify PerceptionManagerWriter and PerceptionManagerReader grounding context integration."""
        writer = get_writer()
        reader = get_reader()

        face_state = {
            "camera_active": True,
            "presence_state": "User Present",
            "face_count": 1,
            "gaze": {
                "gaze_direction": "Looking At Vivy",
                "eye_contact_score": 0.92,
                "eye_contact_strength": "Strong",
            },
            "attention": {
                "attention_score": 92.0,
                "engagement_score": 88.0,
                "presence_score": 95.0,
            },
            "primary_face": {
                "head_pose": {"orientation_label": "Head Facing Vivy"}
            },
            "hardware": {
                "backend": "CPU",
                "mode": "Avatar OFF Mode"
            }
        }

        writer.record_face_perception_state(face_state)
        writer._flush_to_disk()

        reader_state = reader.load_state(force_reload=True)
        self.assertEqual(reader_state.get("presence_state"), "User Present")
        self.assertEqual(reader_state.get("gaze_direction"), "Looking At Vivy")

        grounding_text = reader.build_grounding_context()
        self.assertIn("[User Presence & Gaze Perception State]", grounding_text)
        self.assertIn("User Present", grounding_text)
        self.assertIn("Looking At Vivy", grounding_text)


if __name__ == "__main__":
    unittest.main()
