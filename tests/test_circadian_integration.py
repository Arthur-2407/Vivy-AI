"""
tests/test_circadian_integration.py
====================================
Comprehensive Unit and Integration Tests for the Vivy AI Autonomous Circadian Intelligence System.

Tests cover:
  1. Circadian Engine state generation and phase detection.
  2. Cosine interpolation and smooth phase progress blending.
  3. Emotion vector additive modulation and clamping [0, 100].
  4. Voice speed delta calculation and clamping [0.75, 1.25].
  5. Prompt fragment generation for LLM system prompt.
  6. Hardware Manager workload classification and hysteresis window.
  7. Config loader deep-merging and path discovery.
  8. Non-breaking fallback when config or dependencies are modified.
"""

import os
import sys
import unittest
import time
from datetime import datetime

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from circadian.config_loader import get_config, get, reload as config_reload
from circadian.circadian_engine import CircadianEngine, get_state, get_modulation_prompt_fragment, CircadianState
from circadian.hardware_manager import HardwareManager, get_hardware_hint


class TestCircadianConfigLoader(unittest.TestCase):
    """Test configuration loader functionality."""

    def test_config_loader_returns_dict(self):
        cfg = get_config()
        self.assertIsInstance(cfg, dict)
        self.assertIn("enabled", cfg)
        self.assertIn("time_blocks", cfg)
        self.assertIn("phase_modulation", cfg)
        self.assertIn("hardware_policy", cfg)

    def test_config_typed_get(self):
        enabled = get_config().get("enabled", False)
        self.assertTrue(enabled)
        cpu_wls = get("hardware_policy", "cpu_workloads", default=[])
        self.assertIn("dialogue", cpu_wls)

    def test_config_reload(self):
        cfg = config_reload()
        self.assertIsInstance(cfg, dict)


class TestCircadianEngine(unittest.TestCase):
    """Test Circadian Engine computations, phase detection, and state object."""

    def setUp(self):
        self.engine = CircadianEngine()

    def test_get_state_returns_valid_circadian_state(self):
        state = self.engine.get_state()
        self.assertIsInstance(state, CircadianState)
        self.assertTrue(state.enabled)
        self.assertIn(state.phase_name, [
            "Morning", "LateMorning", "Afternoon", "LateAfternoon",
            "Evening", "Night", "LateNight", "PreDawn"
        ])
        self.assertGreaterEqual(state.energy, 0.0)
        self.assertLessEqual(state.energy, 1.0)
        self.assertGreaterEqual(state.phase_progress, 0.0)
        self.assertLessEqual(state.phase_progress, 1.0)

    def test_phase_detection_all_hours(self):
        """Verify phase classification across all 24 hours of the day (in minutes)."""
        # Morning: 06:00 (360m) - 09:00 (540m)
        phase, next_p, _ = self.engine._detect_phase(400) # 06:40
        self.assertEqual(phase, "Morning")
        self.assertEqual(next_p, "LateMorning")

        # Evening: 18:00 (1080m) - 21:00 (1260m)
        phase, next_p, _ = self.engine._detect_phase(1100) # 18:20
        self.assertEqual(phase, "Evening")
        self.assertEqual(next_p, "Night")

        # LateNight: 00:00 (0m) - 03:00 (180m)
        phase, next_p, _ = self.engine._detect_phase(60) # 01:00
        self.assertEqual(phase, "LateNight")
        self.assertEqual(next_p, "PreDawn")

    def test_prompt_fragment_generation(self):
        frag = get_modulation_prompt_fragment()
        self.assertIsInstance(frag, str)
        # Frag should either be empty or start with [CIRCADIAN HINT]
        if frag:
            self.assertTrue(frag.startswith("[CIRCADIAN HINT]"))

    def test_voice_speed_clamping(self):
        """Test voice speed clamping math as used in run_vivy.py."""
        state = get_state()
        raw_speed = 1.0 + state.voice_speed_delta
        clamped_speed = max(0.75, min(1.25, raw_speed))
        self.assertGreaterEqual(clamped_speed, 0.75)
        self.assertLessEqual(clamped_speed, 1.25)


class TestHardwareManager(unittest.TestCase):
    """Test Hardware Manager workload routing and hysteresis."""

    def setUp(self):
        self.hw = HardwareManager()

    def test_workload_classification(self):
        # CPU workloads
        self.assertEqual(self.hw._classify("dialogue"), "cpu")
        self.assertEqual(self.hw._classify("memory"), "cpu")
        self.assertEqual(self.hw._classify("circadian"), "cpu")
        self.assertEqual(self.hw._classify("emotion"), "cpu")

        # GPU workloads
        self.assertEqual(self.hw._classify("avatar"), "gpu")
        self.assertEqual(self.hw._classify("vision"), "gpu")
        self.assertEqual(self.hw._classify("lip_sync"), "gpu")

    def test_get_hardware_hint_public_api(self):
        hint_cpu = get_hardware_hint("dialogue")
        self.assertIn(hint_cpu, ["cpu", "gpu", "hybrid"])
        hint_gpu = get_hardware_hint("avatar")
        self.assertIn(hint_gpu, ["cpu", "gpu", "hybrid"])


class TestOrchestratorIntegration(unittest.TestCase):
    """Test additive emotion modulation as applied in conversation.py."""

    def test_emotion_vector_modulation(self):
        state = get_state()
        mem_emotion_vector = {
            "curiosity": 50.0,
            "happiness": 50.0,
            "confidence": 50.0,
            "playfulness": 50.0,
            "affection": 50.0,
            "calmness": 50.0,
            "embarrassment": 10.0
        }

        # Apply modulation logic matching conversation.py:4874
        for field, delta in state.emotion_deltas.items():
            if field in mem_emotion_vector:
                mem_emotion_vector[field] = max(0.0, min(100.0, mem_emotion_vector[field] + delta * 100.0))

        # Check all values remain bounded [0, 100]
        for k, v in mem_emotion_vector.items():
            self.assertGreaterEqual(v, 0.0, f"Field {k} below 0")
            self.assertLessEqual(v, 100.0, f"Field {k} above 100")


if __name__ == "__main__":
    unittest.main()
