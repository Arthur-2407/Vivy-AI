"""
perception/tests/test_perception_upgrades.py
============================================
Verification tests for the new perception upgrades:
- Active window process/executable metadata polling
- Rules-based application classification (VS Code, Chrome YouTube/GitHub tabs, VLC, etc.)
- Layout-preserving OCR
- Optimized rolling window audio chunk concatenation
- Temporal query trigger matching
"""

import os
import sys
import unittest
import numpy as np
import PIL.Image

# Ensure imports work from project root
_THIS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_THIS))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from perception.perception_manager import get_writer, get_reader
from perception.screen_pipeline import classify_app_with_os_metadata, _LegacyOCREngine
from conversation import is_perception_query_check, classify_message


class TestPerceptionUpgrades(unittest.TestCase):

    def test_active_process_name_in_state(self):
        """Verify that active process name flows through write -> read side state."""
        from perception.perception_manager import PerceptionManagerWriter, get_reader
        test_writer = PerceptionManagerWriter(start_threads=False)
        with test_writer._lock:
            test_writer._active_process_name = "test_app.exe"
            test_writer._active_window_title = "Test Window"
        test_writer._flush_to_disk()

        reader = get_reader()
        reader._cache = None  # Clear cache to force reading from disk
        state = reader.load_state()
        self.assertEqual(state.get("active_process_name"), "test_app.exe")

    def test_app_classification_with_os_metadata(self):
        """Verify app classification handles known executables, window titles and browser tabs correctly."""
        # 1. VS Code detection
        app, desc = classify_app_with_os_metadata(
            win_title="main.py - Vivy - Visual Studio Code",
            win_class="Chrome_WidgetWin_1",
            proc_name="code.exe",
            main_h=0, main_s=0, main_v=0,
            title_h=0, title_s=0, title_v=0
        )
        self.assertEqual(app, "Visual Studio Code")

        # 2. Browser with YouTube tab
        app, desc = classify_app_with_os_metadata(
            win_title="THE BEST Anime Opening - YouTube - Google Chrome",
            win_class="Chrome_WidgetWin_1",
            proc_name="chrome.exe",
            main_h=0, main_s=0, main_v=0,
            title_h=0, title_s=0, title_v=0
        )
        self.assertEqual(app, "Google Chrome (YouTube)")
        self.assertIn("YouTube", desc)

        # 3. Browser with GitHub tab
        app, desc = classify_app_with_os_metadata(
            win_title="VivyAI/core Pull Requests - GitHub - Microsoft Edge",
            win_class="Chrome_WidgetWin_1",
            proc_name="msedge.exe",
            main_h=0, main_s=0, main_v=0,
            title_h=0, title_s=0, title_v=0
        )
        self.assertEqual(app, "Microsoft Edge (GitHub)")

        # 4. Terminal detection
        app, desc = classify_app_with_os_metadata(
            win_title="Administrator: Windows PowerShell",
            win_class="ConsoleWindowClass",
            proc_name="powershell.exe",
            main_h=0, main_s=0, main_v=0,
            title_h=0, title_s=0, title_v=0
        )
        self.assertEqual(app, "Terminal / Console")

    def test_layout_preserving_ocr_output(self):
        """Verify that layout-preserving OCR plugin calls image_to_string and matches layout structure."""
        engine = _LegacyOCREngine()
        # Mock _init to true so it doesn't fail on missing binary check
        engine._available = True
        
        # We can mock pytesseract's image_to_string and image_to_data
        import pytesseract
        original_to_string = pytesseract.image_to_string
        original_to_data = pytesseract.image_to_data
        
        try:
            pytesseract.image_to_string = lambda img, config=None: "Layout\nPreserved\nColumns"
            pytesseract.image_to_data = lambda img, config=None, output_type=None: {
                'text': ['Word1'], 'conf': [95.0], 'left': [10], 'top': [20], 'width': [30], 'height': [15],
                'block_num': [1], 'par_num': [1], 'line_num': [1], 'word_num': [1]
            }

            img = PIL.Image.new("RGB", (100, 100))
            text, words = engine.extract_rich(img)

            self.assertEqual(text, "Layout\nPreserved\nColumns")
            self.assertEqual(len(words), 1)
            self.assertEqual(words[0]['text'], 'Word1')
            self.assertEqual(words[0]['conf'], 95.0)

        finally:
            pytesseract.image_to_string = original_to_string
            pytesseract.image_to_data = original_to_data

    def test_temporal_query_routing(self):
        """Verify that temporal query triggers are routed to the screen perception category."""
        # 1. classify_message check
        cats_1 = classify_message("what changed since a minute ago?")
        self.assertIn("screen", cats_1)

        cats_2 = classify_message("tell me recent changes on my screen")
        self.assertIn("screen", cats_2)

    def test_low_confidence_fallback(self):
        """Verify that low-confidence OCR yields the correct friendly fallback phrase."""
        from conversation import get_friendly_perception_fallback
        
        # State with low confidence
        mock_state = {
            "screen_sharing_active": True,
            "ocr_confidence": 0.45,
            "highlighted_region_text": "Sample text",
            "last_ocr_text": "Sample text"
        }
        
        # Highlight query
        res1 = get_friendly_perception_fallback(
            user="what word is highlighted?",
            perception_state=mock_state,
            wants_vision=True,
            wants_audio=False
        )
        self.assertEqual(res1, "I can see highlighted text, but it isn't clear enough for me to read accurately.")
        
        # General text query
        res2 = get_friendly_perception_fallback(
            user="what does the screen say?",
            perception_state=mock_state,
            wants_vision=True,
            wants_audio=False
        )
        self.assertEqual(res2, "I can see highlighted text, but it isn't clear enough for me to read accurately.")


if __name__ == "__main__":
    unittest.main()
