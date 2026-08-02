import os
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image

from perception.event_memory import make_event
from perception.perception_manager import WorldState
from perception.screen_pipeline import classify_app_with_os_metadata
from perception.fusion_engine import FusionEngine


class TestPerceptionProvenance(unittest.TestCase):

    def test_structured_event_creation(self):
        """Verify that make_event sets source, confidence, scope, and metadata correctly."""
        event = make_event(
            source="screen_capture",
            semantic="User is watching a video",
            importance=0.8,
            confidence=0.92,
            scope="shared_screen",
            metadata={"test_key": "test_val"}
        )
        self.assertEqual(event["source"], "screen_capture")
        self.assertEqual(event["confidence"], 0.92)
        self.assertEqual(event["scope"], "shared_screen")
        self.assertEqual(event["semantic"], "User is watching a video")
        self.assertEqual(event["importance"], 0.8)
        self.assertEqual(event["metadata"]["test_key"], "test_val")

    def test_window_conflict_resolution_generic(self):
        """Verify that classify_app_with_os_metadata falls back properly when active window is Vivy."""
        # Visual title of browser in OCR
        ocr_text = "Watch Oshi no Ko Online Free - Microsoft Edge\nSome other page content"
        
        # OS Foreground active window points to Vivy dashboard
        win_title = "Microsoft Edge - Vivy AI Core Neural Interface"
        win_class = "Chrome_WidgetWin_1"
        proc_name = "msedge.exe"

        # Run classification
        app_type, env_detail = classify_app_with_os_metadata(
            win_title, win_class, proc_name,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            ocr_text=ocr_text
        )

        # It should resolve the conflict by preferring the OCR-extracted shared browser window title!
        self.assertIn("Microsoft Edge", app_type)
        self.assertIn("Watch Oshi no Ko Online Free", app_type)
        self.assertNotIn("Vivy AI", app_type)

    def test_world_state_boundaries(self):
        """Verify that WorldState compiles sensor fields into structured boundaries."""
        sensor_state = {
            "screen_sharing_active": True,
            "current_app_type": "Microsoft Edge - Watch Oshi no Ko",
            "vision_latest_caption": "A browser showing anime",
            "vision_confidence": 0.88,
            "last_ocr_text": "Oshi no Ko Season 3",
            "ocr_confidence": 0.95,
            "audio_active": True,
            "audio_event_type": "music",
            "audio_event_description": "Background music playing",
            "active_window_title": "Microsoft Edge - Vivy AI Core Neural Interface"
        }
        world = WorldState(sensor_state, memory_context="Some historical context")
        d = world.to_dict()

        # Check visual boundaries
        self.assertEqual(d["visual"]["source"], "screen_capture")
        self.assertTrue(d["visual"]["active"])
        self.assertEqual(d["visual"]["app_type"], "Microsoft Edge - Watch Oshi no Ko")
        self.assertEqual(d["visual"]["vlm_caption"], "A browser showing anime")
        self.assertEqual(d["visual"]["confidence"], 0.88)

        # Check OCR boundaries
        self.assertEqual(d["ocr"]["source"], "screen_ocr")
        self.assertEqual(d["ocr"]["text"], "Oshi no Ko Season 3")
        self.assertEqual(d["ocr"]["confidence"], 0.95)

        # Check OS boundaries
        self.assertEqual(d["os"]["source"], "window_manager")
        self.assertEqual(d["os"]["foreground_window"], "Microsoft Edge - Vivy AI Core Neural Interface")

        # Check memory
        self.assertEqual(d["memory_context"], "Some historical context")

    @patch("requests.post")
    def test_runner_http_forwarding(self, mock_post):
        """Verify that FusionEngine forwards events via HTTP when running in runner role."""
        # Set environment role
        os.environ["VIVY_PROCESS_ROLE"] = "runner"
        try:
            # Mock success response
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp

            engine = FusionEngine()
            engine._enqueue("screen", {"test": "data"})

            # Joining target threads isn't required since _enqueue starts a background daemon thread.
            # We can wait a tiny bit and assert mock_post was called.
            import time
            time.sleep(0.1)

            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "http://127.0.0.1:8080/api/perception/push")
            self.assertEqual(kwargs["json"]["source"], "screen")
            self.assertEqual(kwargs["json"]["data"]["test"], "data")
        finally:
            os.environ.pop("VIVY_PROCESS_ROLE", None)


if __name__ == "__main__":
    unittest.main()
