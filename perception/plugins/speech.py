"""
perception/plugins/speech.py
============================
Pluggable speech recognition adapter for Whisper and other speech engines.
"""

import logging
import os
import subprocess
from typing import Dict, Any, List

from perception.plugins.interfaces import BaseSpeechPlugin
from perception.model_router import ModelRouter

logger = logging.getLogger(__name__)


class WhisperCppSpeechPlugin(BaseSpeechPlugin):
    """
    Speech transcription plugin using whisper.cpp command-line tool.
    """

    def __init__(self, whisper_path: str = None, model_path: str = None):
        from perception.config_loader import get, get_absolute_path
        
        # Read from configuration
        self._whisper_path = whisper_path or get_absolute_path(get("paths", "whisper_dir", default="whisper.cpp/whisper-cli.exe"))
        if not os.path.exists(self._whisper_path):
            # Try fallback directory
            self._whisper_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "whisper.cpp", "whisper-cli.exe")
            
        self._model_path = model_path or get_absolute_path(get("models", "whisper", default="models/ggml-small.bin"))
        self._threads = str(get("pipeline", "whisper_threads", default=2))

    @property
    def name(self) -> str:
        return "whisper_cpp"

    def is_available(self) -> bool:
        return os.path.exists(self._whisper_path) and os.path.exists(self._model_path)

    def transcribe(self, audio_path: str) -> Dict[str, Any]:
        """Runs the whisper.cpp CLI subprocess to transcribe the audio file."""
        if not self.is_available():
            logger.warning(f"[WhisperCpp] CLI tool or model file not found. Whisper path: {self._whisper_path}")
            return {"text": "", "confidence": 0.0, "timestamps": [], "speaker_id": "speaker_0"}

        # Acquire global whisper lock: only ONE whisper-cli instance allowed system-wide
        try:
            from mic_input import _whisper_lock
        except ImportError:
            import threading
            _whisper_lock = threading.RLock()

        if not _whisper_lock.acquire(timeout=6.0):
            logger.info("[WhisperCpp] Another whisper transcription is in progress system-wide. Skipping duplicate invocation.")
            return {"text": "", "confidence": 0.0, "timestamps": [], "speaker_id": "speaker_0"}

        try:
            import re
            from resource_manager import get_resource_manager
            logger.info(f"[WhisperCpp] Transcribing with auto language detection: {audio_path}")
            result = subprocess.run(
                [
                    self._whisper_path,
                    "-m", self._model_path,
                    "-f", audio_path,
                    "-t", self._threads,
                    "-nt",
                    "-np",
                    "-l", "auto",
                    "--prompt", "Vivy",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            text = result.stdout.strip()
            # Simple timestamps parsing (e.g. Qwen/Whisper outputs "[00:00:00.000 --> 00:00:02.000] text")
            timestamps: List[Dict[str, Any]] = []
            
            # Simple heuristic confidence score based on output length and subprocess success
            confidence = 0.95 if result.returncode == 0 and text else 0.0
            
            detected_lang = "en"
            combo_log = f"{result.stderr}\n{result.stdout}"
            m_lang = re.search(r"detecting language:\s*([a-z]{2,3})\s*(?:\(p\s*=\s*([0-9.]+)\))?", combo_log, re.IGNORECASE)
            if not m_lang:
                m_lang = re.search(r"lang(?:uage)?\s*[:=]\s*([a-z]{2,3})", combo_log, re.IGNORECASE)
            if not m_lang:
                m_lang = re.search(r"^\s*\[([a-z]{2,3})\]", text, re.IGNORECASE)
            if m_lang:
                detected_lang = m_lang.group(1).lower()
                if len(m_lang.groups()) >= 2 and m_lang.group(2):
                    try:
                        confidence = float(m_lang.group(2))
                    except (ValueError, TypeError):
                        pass

            return {
                "text": text,
                "confidence": confidence,
                "language": detected_lang,
                "timestamps": timestamps,
                "speaker_id": "speaker_0"  # default session speaker ID
            }
        except Exception as e:
            logger.error(f"[WhisperCpp] Subprocess execution failed: {e}")
            return {"text": "", "confidence": 0.0, "timestamps": [], "speaker_id": "speaker_0"}
        finally:
            _whisper_lock.release()


# Register Speech Plugin with ModelRouter
ModelRouter.register_plugin("speech", "whisper_cpp", WhisperCppSpeechPlugin)


class FasterWhisperSpeechPlugin(BaseSpeechPlugin):
    """
    Speech transcription plugin using faster-whisper (CTranslate2).
    Keeps model loaded in VRAM/RAM for instant inference without subprocess overhead.
    """

    def __init__(self, model_size: str = "small", device: str = "auto"):
        self._model_size = model_size
        self._device = device
        self._model = None
        self._available = False
        
        try:
            from faster_whisper import WhisperModel
            import torch
            
            # Resolve device (GPU if available, else CPU)
            compute_type = "float16"
            if self._device == "auto":
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
                compute_type = "float16" if self._device == "cuda" else "int8"
                
            self._model = WhisperModel(self._model_size, device=self._device, compute_type=compute_type)
            self._available = True
            logger.info(f"[FasterWhisper] Model '{self._model_size}' loaded on {self._device} ({compute_type}).")
        except ImportError:
            logger.warning("[FasterWhisper] 'faster-whisper' package not installed. Skipping plugin.")
        except Exception as e:
            logger.error(f"[FasterWhisper] Initialization failed: {e}")

    @property
    def name(self) -> str:
        return "faster_whisper"

    def is_available(self) -> bool:
        return self._available and self._model is not None

    def transcribe(self, audio_path: str) -> Dict[str, Any]:
        """Runs inference directly in-process via faster-whisper."""
        if not self.is_available():
            return {"text": "", "confidence": 0.0, "timestamps": [], "speaker_id": "speaker_0"}

        try:
            logger.info(f"[FasterWhisper] Transcribing: {audio_path}")
            segments, info = self._model.transcribe(
                audio_path,
                beam_size=5,
                initial_prompt="Vivy",
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 400},
                condition_on_previous_text=False
            )
            
            text_chunks = []
            timestamps = []
            for segment in segments:
                text_chunks.append(segment.text)
                timestamps.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text
                })
                
            full_text = " ".join(text_chunks).strip()
            detected_lang = getattr(info, 'language', 'en')
            try:
                import os
                shared_lang = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared", "detected_language.txt")
                os.makedirs(os.path.dirname(shared_lang), exist_ok=True)
                with open(shared_lang, "w", encoding="utf-8") as lf:
                    lf.write(str(detected_lang))
            except Exception as _err:
                logger.warning(f"[FasterWhisper] Error writing detected language metadata: {_err}")
            
            return {
                "text": full_text,
                "confidence": getattr(info, 'language_probability', 0.95),
                "language": detected_lang,
                "timestamps": timestamps,
                "speaker_id": "speaker_0"
            }
        except Exception as e:
            logger.error(f"[FasterWhisper] Transcription failed: {e}")
            return {"text": "", "confidence": 0.0, "timestamps": [], "speaker_id": "speaker_0"}

ModelRouter.register_plugin("speech", "faster_whisper", FasterWhisperSpeechPlugin)
