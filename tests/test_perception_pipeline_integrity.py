"""
tests/test_perception_pipeline_integrity.py
=============================================
Vivy AI — Perception Pipeline Integrity Test Suite
Verifies all 8 perception capability scenarios and runtime synchronization.
"""

import os
import sys
import time
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from perception.perception_manager import get_writer, get_reader
from conversation import get_friendly_perception_fallback, score_response_rie


class TestPerceptionPipelineIntegrity(unittest.TestCase):

    def setUp(self):
        self.writer = get_writer()
        self.reader = get_reader()
        self.reader._cache = None
        self.reader._cache_file_mtime = 0.0
        # Reset state to clean baseline
        self.writer.record_camera_state(active=False, paused=False)
        self.writer.mark_screen_share_stopped()
        self.reader._cache = None
        self.reader._cache_file_mtime = 0.0

    def test_scenario_1_camera_off(self):
        """Test 1: Camera OFF -> 'I cannot currently see you.'"""
        self.writer.record_camera_state(active=False, paused=False)
        p_state = self.reader.load_state()
        self.assertFalse(p_state.get("camera_active", False))
        
        reply = get_friendly_perception_fallback("Can you see me?", p_state)
        self.assertIn("cannot", reply.lower())

    def test_scenario_2_camera_on_face_detected(self):
        """Test 2: Camera ON + Face detected -> 'Yes, I can currently see your face.'"""
        system_state = {
            "camera_active": True,
            "presence_state": "User Present",
            "face_count": 1,
            "primary_face": {"identity": "User"},
            "gaze": {"gaze_direction": "Looking At Vivy", "eye_contact_score": 0.95},
        }
        self.writer.record_face_perception_state(system_state)
        p_state = self.reader.load_state()
        
        self.assertTrue(p_state.get("camera_active"))
        self.assertTrue(p_state.get("face_detected"))
        
        reply = get_friendly_perception_fallback("Can you see my face?", p_state)
        self.assertIn("see your face", reply.lower())

    def test_scenario_3_camera_on_no_face(self):
        """Test 3: Camera ON + No face -> 'The camera is active, but I can't currently detect your face.'"""
        system_state = {
            "camera_active": True,
            "presence_state": "User Missing",
            "face_count": 0,
            "primary_face": None,
            "gaze": {"gaze_direction": "Unknown", "eye_contact_score": 0.0},
        }
        self.writer.record_face_perception_state(system_state)
        p_state = self.reader.load_state()
        
        self.assertTrue(p_state.get("camera_active"))
        self.assertFalse(p_state.get("face_detected"))
        
        reply = get_friendly_perception_fallback("Can you see my face?", p_state)
        self.assertIn("camera is active", reply.lower())
        self.assertIn("can't", reply.lower())

    def test_scenario_4_screen_share_on(self):
        """Test 4: Screen Share ON -> 'I can see your screen.'"""
        self.writer.mark_screen_share_started()
        self.writer.record_frame_arrival(app_type="VS Code", ocr_chars=100, has_ocr=True, ocr_text="def test(): pass")
        p_state = self.reader.load_state()
        
        self.assertTrue(p_state.get("screen_sharing_active"))
        
        reply = get_friendly_perception_fallback("Can you see my screen?", p_state, wants_vision=True, wants_audio=False)
        self.assertIn("see your screen", reply.lower())

    def test_scenario_5_camera_and_screen_on(self):
        """Test 5: Camera + Screen Share ON -> 'I can see both your screen and your face.'"""
        self.writer.mark_screen_share_started()
        system_state = {
            "camera_active": True,
            "presence_state": "User Present",
            "face_count": 1,
            "gaze": {"gaze_direction": "Looking At Vivy", "eye_contact_score": 0.9},
        }
        self.writer.record_face_perception_state(system_state)
        p_state = self.reader.load_state()
        
        self.assertTrue(p_state.get("camera_active"))
        self.assertTrue(p_state.get("screen_sharing_active"))
        
        reply = get_friendly_perception_fallback("Can you see me?", p_state)
        self.assertIn("both your screen and your face", reply.lower())

    def test_scenario_6_camera_disconnect_propagation(self):
        """Test 6: Camera disconnected during conversation -> Capability changes immediately."""
        self.writer.record_camera_state(active=True, paused=False)
        self.assertTrue(self.reader.is_camera_active())
        
        # Disconnect camera
        self.writer.record_camera_state(active=False, paused=False)
        self.assertFalse(self.reader.is_camera_active())
        
        p_state = self.reader.load_state()
        self.assertEqual(p_state.get("presence_state"), "Camera OFF")

    def test_scenario_7_reconnect_camera(self):
        """Test 7: Reconnect camera -> Capability restored automatically."""
        self.writer.record_camera_state(active=False, paused=False)
        self.assertFalse(self.reader.is_camera_active())
        
        # Reconnect camera
        self.writer.record_camera_state(active=True, paused=False)
        self.assertTrue(self.reader.is_camera_active())

    def test_scenario_8_rapid_switching(self):
        """Test 8: Rapid ON/OFF switching -> No stale state, realtime sync maintained."""
        for i in range(10):
            active = (i % 2 == 0)
            self.writer.record_camera_state(active=active, paused=False)
            self.writer._flush_to_disk()
            self.assertEqual(self.reader.is_camera_active(force_reload=True), active)

    def test_response_validation_guard(self):
        """Test Response Validation Guard rejects contradictory LLM answers."""
        # 1. Camera active + Face detected -> reject "I cannot see you"
        p_state_active = {"camera_active": True, "face_detected": True, "face_count": 1}
        _, valid_negation = score_response_rie("I cannot see you right now.", "Can you see me?", {}, ["general"], perception_state=p_state_active)
        self.assertFalse(valid_negation)

        # 2. Camera off -> reject "I can see your face"
        p_state_off = {"camera_active": False, "screen_sharing_active": False}
        _, valid_claim = score_response_rie("Yes, I can see your face clearly!", "Can you see me?", {}, ["general"], perception_state=p_state_off)
        self.assertFalse(valid_claim)


if __name__ == "__main__":
    unittest.main()
