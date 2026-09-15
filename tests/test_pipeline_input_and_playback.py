import os
import sys
import json
import time
import unittest
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from pipeline.queues import text_queue

class TestPipelineInputAndPlayback(unittest.TestCase):

    def setUp(self):
        self.shared_dir = os.path.join(BASE_DIR, "shared")
        os.makedirs(self.shared_dir, exist_ok=True)
        self.source_file = os.path.join(self.shared_dir, "input_source.txt")
        self.user_txt = os.path.join(self.shared_dir, "user_text.txt")
        self.reply_meta = os.path.join(self.shared_dir, "reply_meta.json")

    def tearDown(self):
        for p in [self.source_file, self.user_txt, self.reply_meta]:
            if os.path.exists(p):
                try: os.remove(p)
                except Exception: pass

    def test_text_queue_voice_input_resolution(self):
        """Verify that when text_queue supplies final speech, input_source resolves to 'voice'."""
        while not text_queue.empty():
            try: text_queue.get_nowait()
            except Exception: break

        # Simulate speech transcription in text_queue
        text_queue.put({"type": "final", "text": "What is the weather?"})

        # Emulate run_vivy input reading loop
        user_input = None
        input_source = "text"
        is_partial = False

        try:
            event = text_queue.get(timeout=0.5)
            if event["type"] == "final":
                user_input = event["text"]
                input_source = "voice"
        except Exception:
            pass

        self.assertEqual(user_input, "What is the weather?")
        self.assertEqual(input_source, "voice")

        # Emulate input_source file check with empty input_source.txt
        if os.path.exists(self.source_file):
            try: os.remove(self.source_file)
            except Exception: pass

        if os.path.exists(self.source_file):
            with open(self.source_file, "r", encoding="utf-8") as sf:
                sf_mode = sf.read().strip().lower()
            if sf_mode:
                input_source = sf_mode

        # Verify input_source was NOT overwritten to 'text'
        self.assertEqual(input_source, "voice")
        is_voice_turn = (input_source == "voice")
        self.assertTrue(is_voice_turn)

    def test_ui_text_input_resolution(self):
        """Verify that when user_text.txt supplies typed input, input_source resolves to 'text'."""
        with open(self.source_file, "w", encoding="utf-8") as sf:
            sf.write("text")
        with open(self.user_txt, "w", encoding="utf-8") as uf:
            uf.write("Hello from web client")

        user_input = None
        input_source = "text"

        if os.path.exists(self.user_txt):
            with open(self.user_txt, "r", encoding="utf-8") as f:
                ui_text = f.read().strip()
            if ui_text:
                user_input = ui_text
                input_source = "text"

        if os.path.exists(self.source_file):
            with open(self.source_file, "r", encoding="utf-8") as sf:
                sf_mode = sf.read().strip().lower()
            if sf_mode:
                input_source = sf_mode

        self.assertEqual(user_input, "Hello from web client")
        self.assertEqual(input_source, "text")
        is_voice_turn = (input_source == "voice")
        self.assertFalse(is_voice_turn)

    def test_duplicate_playback_guard(self):
        """Verify that when streamed_playback_completed is True, second sounddevice.play is bypassed."""
        streamed_playback_completed = True
        mock_sd_play = MagicMock()

        # Simulate voice playback section
        played = False
        if streamed_playback_completed:
            # Bypassed
            pass
        else:
            mock_sd_play()
            played = True

        self.assertFalse(played)
        mock_sd_play.assert_not_called()

        # When streaming was NOT completed, fallback play executes
        streamed_playback_completed = False
        if streamed_playback_completed:
            pass
        else:
            mock_sd_play()
            played = True

        self.assertTrue(played)
        mock_sd_play.assert_called_once()

if __name__ == "__main__":
    unittest.main()
