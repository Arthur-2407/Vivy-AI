"""
Vivy Hub - Audio Adapter
Accepts audio.stream and audio.stt capability requests from nodes.
Decodes base64 PCM audio chunks, writes a temporary WAV file,
and submits it to the existing Whisper pipeline for transcription.
Results are returned as capability.result messages over the WebSocket.
Fault class: Recoverable.
"""
import base64
import os
import threading
import tempfile
import struct
import wave
from typing import Any, Dict, Optional, Callable


class AudioAdapter:
    """
    Processes audio.stream chunks and audio.stt requests from edge nodes.
    Uses the existing Whisper pipeline in whisper.cpp to perform transcription
    on-host, so no new STT infrastructure is needed.
    Fault class: Recoverable.
    """
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self._pending_chunks: Dict[str, bytes] = {}  # device_id → accumulated PCM bytes
        self._chunk_locks: Dict[str, threading.Lock] = {}

    @classmethod
    def get_instance(cls) -> "AudioAdapter":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def can_handle(self, capability_id: str) -> bool:
        return capability_id in ("audio.stream", "audio.stt", "audio.tts")

    def execute(
        self,
        capability_id: str,
        payload: Dict[str, Any],
        device_id: str = "unknown",
        result_callback: Optional[Callable[[Dict], None]] = None,
    ) -> Dict[str, Any]:
        """
        Handle an audio capability request.
        - audio.stream: accumulate PCM chunk
        - audio.stt: flush buffer → Whisper → return transcription
        - audio.tts: synthesize text → return base64 WAV
        """
        if capability_id == "audio.stream":
            return self._handle_stream_chunk(payload, device_id)
        elif capability_id == "audio.stt":
            return self._handle_stt(payload, device_id)
        elif capability_id == "audio.tts":
            return self._handle_tts(payload, device_id)
        return {"error": f"AudioAdapter cannot handle {capability_id}"}

    def _handle_stream_chunk(self, payload: Dict, device_id: str) -> Dict:
        """Accumulate a base64 PCM chunk from a node."""
        try:
            chunk_b64 = payload.get("audio_b64", "")
            if not chunk_b64:
                return {"error": "audio.stream: missing audio_b64 in payload"}
            pcm_bytes = base64.b64decode(chunk_b64)
            # End-of-stream marker triggers transcription
            is_final = payload.get("is_final", False)

            with self._get_chunk_lock(device_id):
                self._pending_chunks[device_id] = (
                    self._pending_chunks.get(device_id, b"") + pcm_bytes
                )

            if is_final:
                # Auto-trigger STT on final chunk
                return self._handle_stt({"sample_rate": payload.get("sample_rate", 16000)}, device_id)
            return {"status": "chunk_received", "bytes_buffered": len(self._pending_chunks.get(device_id, b""))}
        except Exception as e:
            return {"error": f"audio.stream error: {str(e)}"}

    def _handle_stt(self, payload: Dict, device_id: str) -> Dict:
        """Flush buffered audio, write WAV, and call Whisper for transcription."""
        try:
            with self._get_chunk_lock(device_id):
                pcm_bytes = self._pending_chunks.pop(device_id, b"")

            # If payload contains direct audio_b64 (single-shot STT without streaming)
            if not pcm_bytes:
                chunk_b64 = payload.get("audio_b64", "")
                if chunk_b64:
                    pcm_bytes = base64.b64decode(chunk_b64)

            if not pcm_bytes:
                return {"error": "audio.stt: no audio data — send audio.stream chunks first"}

            sample_rate = int(payload.get("sample_rate", 16000))
            tmp_wav = self._write_wav(pcm_bytes, sample_rate)
            try:
                text = self._transcribe(tmp_wav)
                return {"success": True, "text": text, "source": "hub_whisper", "device_id": device_id}
            finally:
                try:
                    os.remove(tmp_wav)
                except Exception:
                    pass
        except Exception as e:
            return {"error": f"audio.stt error: {str(e)}"}

    def _handle_tts(self, payload: Dict, device_id: str) -> Dict:
        """
        Synthesize text using the existing voice pipeline and return base64 WAV.
        Routes through voice.py (TTS) → voice_cloning.py (RVC) pipeline.
        """
        try:
            text = payload.get("text", "")
            if not text:
                return {"error": "audio.tts: missing text in payload"}
            # Try to use the existing voice pipeline
            try:
                import voice
                tmp_wav = tempfile.mktemp(suffix=".wav")
                voice.synthesize_to_file(text, tmp_wav)
                with open(tmp_wav, "rb") as f:
                    wav_b64 = base64.b64encode(f.read()).decode()
                try:
                    os.remove(tmp_wav)
                except Exception:
                    pass
                return {"success": True, "audio_b64": wav_b64, "format": "wav"}
            except AttributeError:
                # voice.py may not have synthesize_to_file — use shared TTS WAV path
                import voice as _voice
                _voice.speak(text)
                shared_wav = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared", "tts.wav")
                if os.path.exists(shared_wav):
                    with open(shared_wav, "rb") as f:
                        wav_b64 = base64.b64encode(f.read()).decode()
                    return {"success": True, "audio_b64": wav_b64, "format": "wav"}
                return {"error": "audio.tts: TTS synthesis did not produce a WAV file"}
        except Exception as e:
            return {"error": f"audio.tts error: {str(e)}"}

    def _write_wav(self, pcm_bytes: bytes, sample_rate: int) -> str:
        """Write 16-bit mono PCM bytes to a temporary WAV file."""
        tmp = tempfile.mktemp(suffix=".wav")
        with wave.open(tmp, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        return tmp

    def _transcribe(self, wav_path: str) -> str:
        """
        Submit a WAV file to the existing Whisper pipeline.
        Routes through mic_input.py transcribe_file if available,
        otherwise falls back to subprocess whisper.cpp.
        """
        # Attempt 1: Use mic_input module's transcription function
        try:
            from mic_input import transcribe_file as _transcribe_file
            return _transcribe_file(wav_path)
        except ImportError:
            pass
        except Exception as e:
            print(f"[AudioAdapter] mic_input.transcribe_file error: {e}")

        # Attempt 2: subprocess whisper.cpp
        try:
            import subprocess
            import glob
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            whisper_dir = os.path.join(base_dir, "whisper.cpp")
            whisper_exe = os.path.join(whisper_dir, "main.exe")
            model_dir = os.path.join(base_dir, "models")
            whisper_models = glob.glob(os.path.join(model_dir, "ggml-*.bin"))
            if os.path.exists(whisper_exe) and whisper_models:
                result = subprocess.run(
                    [whisper_exe, "-m", whisper_models[0], "-f", wav_path, "--output-txt", "--no-timestamps"],
                    capture_output=True, text=True, timeout=60
                )
                lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
                return " ".join(lines) if lines else ""
        except Exception as e:
            print(f"[AudioAdapter] whisper.cpp subprocess error: {e}")

        return "[transcription unavailable]"

    def _get_chunk_lock(self, device_id: str) -> threading.Lock:
        if device_id not in self._chunk_locks:
            self._chunk_locks[device_id] = threading.Lock()
        return self._chunk_locks[device_id]
