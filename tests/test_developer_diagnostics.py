"""
tests/test_developer_diagnostics.py
====================================
Automated regression test suite for Developer Runtime Diagnostic Mode.
"""

import os
import sys
import time
import unittest

# Ensure local imports work
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from developer_diagnostic_manager import get_developer_diagnostic_manager, DeveloperDiagnosticManager


class TestDeveloperDiagnosticMode(unittest.TestCase):

    def setUp(self):
        self.ddm = get_developer_diagnostic_manager()
        # Reset state for predictable test runs
        self.ddm.toggle(enable=False)

    def test_default_disabled_state(self):
        """Verify Diagnostic Mode is disabled by default."""
        self.assertFalse(self.ddm.is_enabled())

    def test_toggle_state(self):
        """Verify mode toggling works as expected."""
        state1 = self.ddm.toggle(enable=True)
        self.assertTrue(state1)
        self.assertTrue(self.ddm.is_enabled())

        state2 = self.ddm.toggle(enable=False)
        self.assertFalse(state2)
        self.assertFalse(self.ddm.is_enabled())

    def test_zero_overhead_when_disabled(self):
        """Verify metrics buffers do not accumulate items when disabled."""
        self.ddm.toggle(enable=False)
        prev_count = len(self.ddm._frame_telemetry)

        self.ddm.record_frame(
            frame_num=100,
            camera_source="test_cam",
            resolution=(640, 480),
            latency_ms=12.5,
            fps=30.0,
            dropped_frames=0,
            detections={"face": {"count": 1}}
        )

        self.assertEqual(len(self.ddm._frame_telemetry), prev_count)

    def test_telemetry_recording_when_enabled(self):
        """Verify frame, websocket, and prompt records are stored when enabled."""
        self.ddm.toggle(enable=True)

        # 1. Record frame
        self.ddm.record_frame(
            frame_num=101,
            camera_source="test_cam",
            resolution=(640, 480),
            latency_ms=15.0,
            fps=30.0,
            dropped_frames=0,
            detections={"face": {"count": 1}}
        )
        self.assertGreater(len(self.ddm._frame_telemetry), 0)
        self.assertEqual(self.ddm._frame_telemetry[0]["frame_num"], 101)

        # 2. Record WS packet
        self.ddm.record_ws_packet(
            direction="OUTGOING",
            message_type="animation",
            payload_size=120,
            ser_time_ms=0.5,
            status="OK"
        )
        self.assertGreater(len(self.ddm._websocket_packets), 0)
        self.assertEqual(self.ddm._websocket_packets[0]["message_type"], "animation")

        # 3. Record Prompt Trace
        self.ddm.record_prompt_trace(
            user_query="What is in my hand?",
            camera_observations={"face": 1},
            vision_model_output={"caption": "holding coffee mug"},
            context_builder_output="user is holding a coffee mug",
            final_prompt_sent="Prompt: What is in my hand?",
            raw_llm_response="You are holding a coffee mug.",
            filtered_response="You are holding a coffee mug.",
            final_spoken_response="You are holding a coffee mug."
        )
        traces = self.ddm.get_prompt_traces()
        self.assertGreater(len(traces), 0)
        self.assertEqual(traces[0]["user_query"], "What is in my hand?")

    def test_fallback_detector_and_defect_flagging(self):
        """Verify automated defect detection when fallback executes during valid vision state."""
        self.ddm.toggle(enable=True)
        initial_defects = len(self.ddm.get_defects())

        # Test case: Fallback executed despite vision_was_valid=True -> Must flag defect
        self.ddm.record_fallback(
            trigger_phrase="I don't see anything in your hand.",
            file_path="conversation.py",
            class_name="Pipeline",
            method_name="_pick_fallback",
            line_num=4771,
            trigger_condition="is_perception=True",
            runtime_evidence={"camera": True, "faces": 1, "objects": 2},
            why_executed="RIE failed",
            vision_was_valid=True
        )

        defects = self.ddm.get_defects()
        self.assertEqual(len(defects), initial_defects + 1)
        self.assertTrue(defects[0]["is_defect"])
        self.assertIn("DEFECT-", defects[0]["defect_id"])

    def test_snapshot_retrieval(self):
        """Verify full diagnostic snapshot serialization."""
        self.ddm.toggle(enable=True)
        snapshot = self.ddm.get_snapshot()

        self.assertIn("enabled", snapshot)
        self.assertIn("stats", snapshot)
        self.assertIn("latest_frame", snapshot)
        self.assertIn("recent_packets", snapshot)
        self.assertIn("active_defects", snapshot)


if __name__ == "__main__":
    unittest.main()
