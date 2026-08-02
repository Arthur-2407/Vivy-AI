"""
Vivy AI - ML Voice Service Facade
Exposes isolated Voice Synthesis capabilities running explicitly on GPU (XTTS/Tacotron).
"""
import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from voice import VivyVoice

def synthesize_speech(text: str, output_path: str = "output.wav") -> bool:
    """
    Synthesizes speech from text.
    The underlying engine uses XTTS-v2 or Tacotron via GPU automatically.
    """
    try:
        voice = VivyVoice.get_instance()
        voice.speak(text, wait=True)
        return True
    except Exception as e:
        print(f"[Voice API] Speech synthesis failed: {e}")
        return False
