import os
import sys
import time
import math
import unittest

# Ensure the root project directory is in the path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from perception.perception_manager import PerceptionManagerWriter, PerceptionManagerReader
from conversation import _pick_fallback

class TestPerceptionUpgrades(unittest.TestCase):

    def setUp(self):
        # Initialize a new writer with a local state path to avoid touching the actual state file
        self.test_state_path = os.path.join(BASE_DIR, "shared", "perception_state_test.json")
        self.writer = PerceptionManagerWriter(start_threads=False)
        self.writer._state_path = self.test_state_path
        self.reader = PerceptionManagerReader()
        self.reader._state_path = self.test_state_path

    def tearDown(self):
        if os.path.exists(self.test_state_path):
            try:
                os.remove(self.test_state_path)
            except Exception as _err:
                print(f"[test_perception_upgrades.py] Silenced exception: {_err}")

    def test_record_and_read_transcript(self):
        # 1. Record transcript
        test_text = "Hello Satyajeet, let's watch a movie"
        self.writer.record_screen_audio_transcript(test_text)
        
        # Mock recent audio chunk arrival
        self.writer._last_audio_time = time.time()
        self.writer._audio_active = True
        
        # Manually force state generation and check
        state = self.writer._build_state(time.time())
        self.assertEqual(state.get("screen_audio_transcript"), test_text)
        
        # Save state to disk and read back
        self.writer._flush_to_disk()
        read_state = self.reader.load_state()
        self.assertEqual(read_state.get("screen_audio_transcript"), test_text)
        
        # Verify snapshot retrieval
        snapshot = self.reader.get_live_perception_snapshot()
        self.assertEqual(snapshot.get("screen_audio_transcript"), test_text)

    def test_audio_transcript_decay(self):
        # 1. Record transcript
        self.writer.record_screen_audio_transcript("Decay me please")
        
        # Fake a stale timestamp for audio
        self.writer._audio_active = True
        self.writer._last_audio_time = time.time() - 30.0 # 30 seconds ago (AUDIO_STALE_SECONDS is 10s)
        
        state = self.writer._build_state(time.time())
        # Verify transcript decays to empty string
        self.assertEqual(state.get("screen_audio_transcript"), "")
        self.assertEqual(state.get("audio_active"), False)

    def test_dialogue_perception_triggers(self):
        # Verify that new triggers correctly select perception fallbacks
        from conversation import get_friendly_perception_fallback
        
        # Test query triggering
        queries_to_test = [
            "what word is highlighted?",
            "what does the screen say",
            "what is the movie saying right now?",
            "tell me the lyrics of the song",
            "what did it say?"
        ]
        
        # Mock perception state
        mock_state = {
            "screen_sharing_active": True,
            "audio_active": True,
            "last_ocr_text": "Code Highlights",
            "screen_audio_transcript": "We are watching a movie"
        }
        
        for q in queries_to_test:
            # _pick_fallback should route it to perception fallback since they match triggers
            fb = _pick_fallback(None, [], user_query=q, perception_state=mock_state)
            self.assertTrue(
                any(word in fb for word in ["read", "heard", "OCR", "lyrics", "transcribed", "highlighted", "screen", "visible"]),
                f"Query '{q}' failed to route to perception fallback, got: '{fb}'"
            )

if __name__ == "__main__":
    unittest.main()
