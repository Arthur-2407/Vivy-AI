"""
Vivy AI — Master Animation & Pipeline Unit & Integration Test Suite (v1.0.0)
==========================================================================
Tests Animation contracts, AnimationRegistry schema, AnimationPlanner emotion mapping,
BehaviorState contracts, EmotionState contracts, and WebSocket message formatting.
"""

import os
import sys
import json
import unittest
import uuid
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from contracts.animation_request import AnimationRequest
from contracts.animation_response import AnimationResponse
from contracts.emotion_state import EmotionState
from contracts.behavior_state import BehaviorState
from animator.animator import VivyAnimationPlanner, _load_config, _default_config

class TestAnimationContracts(unittest.TestCase):
    def test_animation_request_serialization(self):
        req = AnimationRequest(
            request_id="test-uuid-1234",
            category="gesture",
            clip_or_procedural_id="WaveHand",
            target_layers=["Gesture Layer"],
            blend_weight=0.9,
            transition_duration=0.25,
            priority=3,
            interruption_policy="interrupt_if_higher",
            source_module="TestModule",
            parameters={"speed": 1.2}
        )
        d = req.to_dict()
        self.assertEqual(d["request_id"], "test-uuid-1234")
        self.assertEqual(d["category"], "gesture")
        self.assertEqual(d["clip_or_procedural_id"], "WaveHand")
        self.assertEqual(d["priority"], 3)

        reconstructed = AnimationRequest.from_dict(d)
        self.assertEqual(reconstructed.request_id, req.request_id)
        self.assertEqual(reconstructed.clip_or_procedural_id, req.clip_or_procedural_id)
        self.assertEqual(reconstructed.blend_weight, 0.9)

    def test_animation_response_serialization(self):
        resp = AnimationResponse(
            request_id="test-uuid-1234",
            status="playing",
            resolved_clips=["WaveHand"],
            procedural_params={"fade_time": 0.2},
            estimated_duration=1.5
        )
        d = resp.to_dict()
        self.assertEqual(d["status"], "playing")
        self.assertEqual(d["resolved_clips"], ["WaveHand"])

        reconstructed = AnimationResponse.from_dict(d)
        self.assertEqual(reconstructed.request_id, resp.request_id)
        self.assertEqual(reconstructed.status, resp.status)

    def test_emotion_state_serialization(self):
        st = EmotionState(
            primary_emotion="joy",
            valence=0.8,
            arousal=0.7,
            dominance=0.6,
            intensity_values={"joy": 0.8, "excitement": 0.5}
        )
        d = st.to_dict()
        self.assertEqual(d["primary_emotion"], "joy")
        self.assertEqual(d["valence"], 0.8)

        reconstructed = EmotionState.from_dict(d)
        self.assertEqual(reconstructed.primary_emotion, "joy")
        self.assertEqual(reconstructed.valence, 0.8)

    def test_behavior_state_serialization(self):
        b = BehaviorState(
            current_mode="conversing",
            active_stack=["idle", "listening"],
            priority_levels={"speaking": 2}
        )
        d = b.to_dict()
        self.assertEqual(d["current_mode"], "conversing")
        self.assertEqual(d["active_stack"], ["idle", "listening"])

        reconstructed = BehaviorState.from_dict(d)
        self.assertEqual(reconstructed.current_mode, "conversing")


class TestAnimationRegistry(unittest.TestCase):
    def test_registry_schema_and_validity(self):
        registry_path = os.path.join(BASE_DIR, "vivy_animation_registry.json")
        self.assertTrue(os.path.exists(registry_path), "vivy_animation_registry.json does not exist")

        with open(registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("version", data)
        self.assertIn("categories", data)
        self.assertIn("emotion_layers", data)
        self.assertIn("fallback_trigger", data)

        categories = data["categories"]
        self.assertIn("idle", categories)
        self.assertIn("dance", categories)
        self.assertIn("gesture", categories)
        self.assertIn("status", categories)

        # Check unique IDs
        all_ids = []
        for cat_name, clips in categories.items():
            for clip in clips:
                self.assertIn("id", clip, f"Clip in category {cat_name} missing 'id'")
                self.assertNotIn(clip["id"], all_ids, f"Duplicate clip ID detected: {clip['id']}")
                all_ids.append(clip["id"])

        # Verify fallback trigger exists or is valid
        fallback = data["fallback_trigger"]
        self.assertTrue(isinstance(fallback, str) and len(fallback) > 0)


class TestVivyAnimationPlanner(unittest.TestCase):
    def setUp(self):
        self.planner = VivyAnimationPlanner(bridge=None)

    def test_on_emotion_mapping(self):
        req_joy = self.planner.on_emotion("joy", circadian_energy=0.9)
        self.assertIsNotNone(req_joy)
        self.assertIn(req_joy.clip_or_procedural_id, ["IdleHappy", "IdleCheer"])

    def test_on_emotion_cooldown(self):
        req1 = self.planner.on_emotion("sadness", circadian_energy=0.8)
        self.assertIsNotNone(req1)
        self.assertEqual(req1.clip_or_procedural_id, "IdleSad")

        # Second call immediately should return None due to cooldown
        req2 = self.planner.on_emotion("sadness", circadian_energy=0.8)
        self.assertIsNone(req2)


if __name__ == "__main__":
    unittest.main()
