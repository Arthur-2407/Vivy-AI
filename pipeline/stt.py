import os
import subprocess
from abc import ABC, abstractmethod

class STTBackend(ABC):
    @abstractmethod
    def transcribe(self, wav_path: str) -> str:
        pass

class WhisperCLIBackend(STTBackend):
    def __init__(self, model_path: str, whisper_exe: str):
        self.model_path = model_path
        self.whisper_exe = whisper_exe

    def transcribe(self, wav_path: str) -> str:
        if not os.path.exists(self.whisper_exe):
            print(f"[STT] Missing whisper CLI at {self.whisper_exe}")
            return ""
        
        cmd = [
            self.whisper_exe,
            "-m", self.model_path,
            "-f", wav_path,
            "--no-prints",
            "-l", "auto"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            if result.returncode == 0:
                out = result.stdout.strip()
                # Remove [00:00.000 --> 00:00.000] tags if present
                import re
                clean = re.sub(r'\[\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}\.\d{3}\]', '', out).strip()
                return clean
            else:
                print(f"[STT] Whisper CLI failed: {result.stderr}")
        except Exception as e:
            print(f"[STT] Whisper CLI execution error: {e}")
        return ""

class FasterWhisperBackend(STTBackend):
    def __init__(self, model_size="tiny", device="cpu", compute_type="int8"):
        print(f"[STT] Loading faster-whisper model ({model_size}) on {device}...")
        try:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
            print("[STT] faster-whisper loaded successfully.")
        except Exception as e:
            print(f"[STT] Failed to load faster-whisper: {e}")
            self.model = None

    def transcribe(self, wav_path: str) -> str:
        if self.model is None:
            return ""
        try:
            segments, _ = self.model.transcribe(wav_path, beam_size=5, vad_filter=True)
            text = " ".join([segment.text for segment in segments]).strip()
            return text
        except Exception as e:
            print(f"[STT] faster-whisper error: {e}")
            return ""
