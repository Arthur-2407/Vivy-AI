import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from mic_input import run_whisper
from run_vivy import is_blank_or_noise, stop_indicator
import web_server

class TestPipelineChatConnection(unittest.TestCase):

    def setUp(self):
        self.shared_dir = os.path.join(BASE_DIR, "shared")
        os.makedirs(self.shared_dir, exist_ok=True)
        self.user_txt = os.path.join(self.shared_dir, "user_text.txt")
        self.input_source = os.path.join(self.shared_dir, "input_source.txt")

    def tearDown(self):
        # Clean up test artifacts
        for p in [self.user_txt, self.input_source]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception as _err:
                    print(f"[test_pipeline_chat_connection.py] Silenced exception: {_err}")

    def test_api_send_queues_message(self):
        test_user_txt = os.path.join(self.shared_dir, "test_user_text.txt")
        with patch.object(web_server, "USER_TXT", test_user_txt):
            with web_server.app.test_client() as client:
                resp = client.post("/api/send", json={"text": "hello from web client"})
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertTrue(data.get("success"))

                # Verify files written
                with open(test_user_txt, "r", encoding="utf-8") as f:
                    user_text_val = f.read().strip()
                self.assertEqual(user_text_val, "hello from web client")

                with open(self.input_source, "r", encoding="utf-8") as f:
                    source_val = f.read().strip()
                self.assertEqual(source_val, "text")
            if os.path.exists(test_user_txt):
                try: os.remove(test_user_txt)
                except Exception: pass



    @patch("perception.model_router.ModelRouter.get_speech_plugin")
    def test_mic_input_preserves_web_chat_text(self, mock_plugin_getter):
        mock_plugin = MagicMock()
        mock_plugin.is_available.return_value = True
        mock_plugin.transcribe.return_value = {"text": "Transcribed voice text"}
        mock_plugin_getter.return_value = mock_plugin

        # 1. Simulate web server writing chat text
        with open(self.input_source, "w", encoding="utf-8") as f:
            f.write("text")
        with open(self.user_txt, "w", encoding="utf-8") as f:
            f.write("User typed chat message")

        # 2. Simulate mic_input run_whisper completing with non-empty transcript
        dummy_wav = os.path.join(BASE_DIR, "recordings", "dummy_test.wav")

        # Mock run_whisper writing
        res = run_whisper(dummy_wav, output_txt_path=self.user_txt)

        # 3. Verify user_txt WAS NOT overwritten by mic_input
        with open(self.user_txt, "r", encoding="utf-8") as f:
            content_after = f.read().strip()

        self.assertEqual(content_after, "User typed chat message")

    def test_noise_filtering(self):
        self.assertTrue(is_blank_or_noise(""))
        self.assertTrue(is_blank_or_noise("   "))
        self.assertTrue(is_blank_or_noise("[blank_audio]"))
        self.assertTrue(is_blank_or_noise("[music]"))
        # Verify acoustic hallucination and repetition guard (e.g., Kannada script repetition loop 'ಸಿರಿಲಿಲಿಲಿಲಿಲಿ')
        self.assertTrue(is_blank_or_noise("ಸಿರಿಲಿಲಿಲಿಲಿಲಿ"))
        self.assertTrue(is_blank_or_noise("............"))
        self.assertTrue(is_blank_or_noise("yeah yeah yeah yeah yeah"))
        self.assertFalse(is_blank_or_noise("Hello Vivy how are you"))
        self.assertFalse(is_blank_or_noise("Can you help me with Python?"))
        self.assertFalse(is_blank_or_noise("नमस्ते विवी आप कैसी हैं"))

    def test_stop_indicator_flushes(self):
        # Ensure stop_indicator runs without exception
        try:
            stop_indicator()
            stop_indicator("Done test")
        except Exception as e:
            self.fail(f"stop_indicator raised exception: {e}")

if __name__ == "__main__":
    unittest.main()
