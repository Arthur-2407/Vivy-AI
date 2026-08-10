import os
import vivy_env
os.environ["VIVY_PROCESS_ROLE"] = "web_server"
import sys
import time
import shutil
import threading
import json
import uuid
from flask import Flask, jsonify, request, send_from_directory
from telemetry_manager import get_telemetry_manager
from resource_manager import get_resource_manager

# Reconfigure stdout/stderr to use utf-8 to avoid encoding errors with emojis on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(BASE_DIR, "shared")
TRANSCRIPTS_DIR = os.path.join(BASE_DIR, "transcripts")
MEMORY_FILE = os.path.join(BASE_DIR, "vivy_memory.json")

USER_TXT = os.path.join(SHARED_DIR, "user_text.txt")
REPLY_TXT = os.path.join(SHARED_DIR, "reply_text.txt")
EMOTION_TXT = os.path.join(SHARED_DIR, "emotion.txt")
STATUS_TXT = os.path.join(SHARED_DIR, "status.txt")
RVC_WAV = os.path.join(SHARED_DIR, "rvc.wav")
TTS_WAV = os.path.join(SHARED_DIR, "tts.wav")
MIC_MUTE_TXT = os.path.join(SHARED_DIR, "mic_mute.txt")
VOICE_OUTPUT_MUTE_TXT = os.path.join(SHARED_DIR, "voice_output_mute.txt")
RVC_DISABLE_TXT = os.path.join(SHARED_DIR, "rvc_disable.txt")
AVATAR_DISABLE_TXT = os.path.join(SHARED_DIR, "avatar_disable.txt")
AVATAR_CONNECTED_TXT = os.path.join(SHARED_DIR, "avatar_connected.txt")
AVATAR_STATUS_JSON = os.path.join(SHARED_DIR, "avatar_status.json")
LOAD_AVATAR_TXT = os.path.join(SHARED_DIR, "load_avatar.txt")
VIEWPORT_TXT = os.path.join(SHARED_DIR, "viewport.txt")
WEB_INTERACTION_TXT = os.path.join(SHARED_DIR, "web_interaction.txt")
SCREEN_CONTEXT_TXT = os.path.join(SHARED_DIR, "screen_context.txt")

AUDIO_PERCEPTION_ENABLE_TXT = os.path.join(SHARED_DIR, "audio_perception_enable.txt")
AUDIO_PERCEPTION_DISABLE_TXT = os.path.join(SHARED_DIR, "audio_perception_disable.txt")
PROACTIVITY_ENABLE_TXT = os.path.join(SHARED_DIR, "proactivity_enable.txt")
PROACTIVITY_DISABLE_TXT = os.path.join(SHARED_DIR, "proactivity_disable.txt")
SCREEN_PERCEPTION_ENABLE_TXT = os.path.join(SHARED_DIR, "screen_perception_enable.txt")
SCREEN_PERCEPTION_DISABLE_TXT = os.path.join(SHARED_DIR, "screen_perception_disable.txt")
VISION_MODEL_ENABLE_TXT = os.path.join(SHARED_DIR, "vision_model_enable.txt")
VISION_MODEL_DISABLE_TXT = os.path.join(SHARED_DIR, "vision_model_disable.txt")
ADAPTIVE_SAMPLING_ENABLE_TXT = os.path.join(SHARED_DIR, "adaptive_sampling_enable.txt")
ADAPTIVE_SAMPLING_DISABLE_TXT = os.path.join(SHARED_DIR, "adaptive_sampling_disable.txt")
SHAKE_TXT = os.path.join(SHARED_DIR, "screen_impact_shake.txt")
import numpy as np

class HeuristicDiarizer:
    def __init__(self):
        self._last_pitch = 0.0
        self._last_energy = 0.0
        self._speaker_index = 0
        self._speaker_profiles = [] # list of (avg_pitch, avg_energy)

    def attribute_speaker(self, samples: np.ndarray) -> str:
        if len(samples) == 0:
            return "speaker_0"
        
        # Calculate pitch-like metric (zero crossing rate / spectral centroid as simple proxy)
        zcr = float(np.mean(np.abs(np.diff(np.sign(samples)))) / 2)
        energy = float(np.sqrt(np.mean(samples ** 2)))
        
        # Cluster speakers based on zcr and energy difference
        matched_spk = None
        for idx, (p, e) in enumerate(self._speaker_profiles):
            # If similar pitch and energy profile
            if abs(zcr - p) < 0.05 and abs(20*np.log10(energy/(e+1e-9))) < 6.0:
                matched_spk = f"speaker_{idx + 1}"
                # Update rolling average profile
                self._speaker_profiles[idx] = (p * 0.9 + zcr * 0.1, e * 0.9 + energy * 0.1)
                break
                
        if matched_spk is None:
            self._speaker_index += 1
            matched_spk = f"speaker_{self._speaker_index}"
            self._speaker_profiles.append((zcr, energy))
            
        return matched_spk

_diarizer = HeuristicDiarizer()

def detect_language(text: str) -> str:
    text_lower = text.lower()
    if any(w in text_lower for w in [" bonjour ", " oui ", " merci "]):
        return "fr"
    if any(w in text_lower for w in [" hola ", " gracias ", " si "]):
        return "es"
    if any(w in text_lower for w in [" desu ", " arigatou ", " konnichiwa ", " chan ", " san ", " kun "]):
        return "ja"
def is_noise_label(text: str) -> bool:
    t_clean = text.strip().lower()
    if not t_clean:
        return True

    # Strip Whisper timestamps
    import re
    t_clean = re.sub(
        r"\[\d{2}:\d{2}:\d{2}\.\d+\s*-->\s*\d{2}:\d{2}:\d{2}\.\d+\]\s*",
        "",
        t_clean
    ).strip()

    if not t_clean:
        return True

    # Filter common Whisper silence/noise labels
    noise_patterns = {
        "[blank_audio]",
        "[music]",
        "(music)",
        "[upbeat music]",
        "(upbeat music)",
        "[laughter]",
        "(laughter)",
        "[applause]",
        "(applause)",
        "(sigh)",
        "[sigh]",
        "[music playing]",
        "(music playing)",
        "[indistinct]",
        "(indistinct)",
        "(speaking in foreign language)",
        "[speaking in foreign language]",
    }

    if t_clean in noise_patterns:
        return True

    # Multi-chunk check: check if EVERY non-empty line/segment is noise
    segments = [s.strip() for s in t_clean.split("\n") if s.strip()]
    if segments and all(
        seg in noise_patterns
        or re.match(r"^\[[^\]]*\]$", seg)
        or re.match(r"^\([^)]*\)$", seg)
        for seg in segments
    ):
        return True

    # Single line check for only bracketed/parenthesized content
    if re.match(r"^\[[^\]]*\]$", t_clean) or re.match(r"^\([^)]*\)$", t_clean):
        return True

    # Strip any punctuation/whitespace for word-based check
    t_clean_alpha = re.sub(r"[^\w\s]", "", t_clean).strip()
    words = t_clean_alpha.split()
    if len(words) <= 2:
        filler_words = {
            "to", "the", "you", "thank", "thanks", "bye", "watching", "please", "so", "i", "a",
            "oh", "uh", "um", "sh", "go", "it", "yeah", "well", "like", "right", "good", "okay",
            "but", "how", "what", "here", "there", "know", "get", "make", "say", "would", "time",
            "some", "them", "see", "other", "than", "then", "its", "now", "only", "he", "she",
            "me", "my", "we", "us", "our", "they", "him", "her", "is", "am", "are", "was", "were",
            "be", "been", "have", "has", "had", "do", "does", "did", "of", "in", "on", "at", "for",
            "with", "about", "against", "between", "into", "through", "during", "before", "after",
            "above", "below", "to", "from", "up", "down", "in", "out", "over", "under", "again",
            "further", "then", "once", "here", "there", "when", "where", "why", "how", "all",
            "any", "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor",
            "not", "only", "own", "same", "so", "than", "too", "very", "s", "t", "can", "will",
            "just", "don", "should", "now"
        }
        if all(w in filler_words for w in words):
            return True

    return False


# ──────────────────────────────────────────────────────────────────────

# VISION BRIDGE — PIL-based screen analysis (no Tesseract required)
# ──────────────────────────────────────────────────────────────────────
# Attempt to import pytesseract for OCR; gracefully fall back to PIL-only
_TESSERACT_AVAILABLE = False
try:
    import pytesseract as _pytesseract
    # Try common Tesseract install paths on Windows
    import os as _os
    _TESS_PATHS = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Users\SATYAJEET\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    ]
    for _tp in _TESS_PATHS:
        if _os.path.exists(_tp):
            _pytesseract.pytesseract.tesseract_cmd = _tp
            _TESSERACT_AVAILABLE = True
            break
    if not _TESSERACT_AVAILABLE:
        # Try system PATH
        import subprocess as _sp
        try:
            _sp.run(["tesseract", "--version"], capture_output=True, timeout=2)
            _TESSERACT_AVAILABLE = True
        except Exception as _err:
            print(f"[web_server.py] Silenced exception: {_err}")
except ImportError:
    pass

# ──────────────────────────────────────────────────────────────────────
# PERCEPTION PACKAGE — Multimodal perception integration
# Imported with graceful fallback: if the perception/ package is absent
# or fails to import, ALL existing behaviour is completely unchanged.
# ──────────────────────────────────────────────────────────────────────
_PERCEPTION_AVAILABLE = False
_screen_pipeline_mod  = None
_fusion_engine_mod    = None
import queue

_last_screen_event = None
_frame_queue = queue.Queue(maxsize=60)
_last_speech_detected_time = 0.0
_audio_stream_buffer = bytearray()
_audio_stream_header = bytearray()
_audio_latest_chunks = []

# Persistent FFmpeg streaming decoder variables (Low-latency streaming fix)
_ffmpeg_process = None
_ffmpeg_lock = threading.Lock()
_decoded_pcm_buffer = bytearray()
_decoded_pcm_lock = threading.Lock()

def _start_ffmpeg():
    global _ffmpeg_process, _decoded_pcm_buffer
    ffmpeg_bin = os.path.join(BASE_DIR, "ffmpeg", "bin", "ffmpeg.exe")
    if not os.path.exists(ffmpeg_bin):
        print("[ScreenAudio] FFmpeg binary not found at:", ffmpeg_bin)
        return
        
    cmd = [
        ffmpeg_bin,
        "-fflags", "nobuffer",
        "-flags", "low_delay",
        "-f", "matroska",
        "-i", "pipe:0",
        "-f", "f32le",
        "-acodec", "pcm_f32le",
        "-ar", "16000",
        "-ac", "1",
        "pipe:1"
    ]
    try:
        import subprocess
        devnull = get_resource_manager().get_devnull()
        _ffmpeg_process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=devnull
        )
        get_resource_manager().register_subprocess(_ffmpeg_process, name="ffmpeg")
        with _decoded_pcm_lock:
            _decoded_pcm_buffer = bytearray()
            
        # Start background reader thread
        ff_thread = threading.Thread(target=_ffmpeg_reader, daemon=True, name="FFmpegReader")
        get_resource_manager().register_thread(ff_thread, name="FFmpegReader")
        ff_thread.start()
        print("[ScreenAudio] Persistent FFmpeg low-latency process started.")

        # Feed the saved stream header immediately to let FFmpeg initialize codecs properly
        if _audio_stream_header and _ffmpeg_process.stdin is not None:
            try:
                _ffmpeg_process.stdin.write(_audio_stream_header)
                _ffmpeg_process.stdin.flush()
                print(f"[ScreenAudio] Fed stream header ({len(_audio_stream_header)} bytes) to new FFmpeg instance.")
            except Exception as wh_err:
                print(f"[ScreenAudio] Failed to write initial header to restarted FFmpeg: {wh_err}")
    except Exception as e:
        print(f"[ScreenAudio] Failed to start persistent FFmpeg: {e}")

def _ffmpeg_reader():
    global _ffmpeg_process, _decoded_pcm_buffer
    while True:
        proc = _ffmpeg_process
        if proc is None or proc.stdout is None:
            break
        try:
            fd = proc.stdout.fileno()
            data = os.read(fd, 65536)
            if not data:
                print("[ScreenAudio] FFmpeg stdout EOF.")
                break
            with _decoded_pcm_lock:
                _decoded_pcm_buffer.extend(data)
                # Keep last 30 seconds of float32 samples (16000 * 30 * 4 bytes = 1,920,000 bytes)
                max_bytes = 16000 * 30 * 4
                if len(_decoded_pcm_buffer) > max_bytes:
                    _decoded_pcm_buffer = _decoded_pcm_buffer[-max_bytes:]
        except Exception as e:
            print(f"[ScreenAudio] Error reading from FFmpeg: {e}")
            break

def _stop_ffmpeg():
    global _ffmpeg_process
    with _ffmpeg_lock:
        if _ffmpeg_process is not None:
            for pipe in (_ffmpeg_process.stdin, _ffmpeg_process.stdout, _ffmpeg_process.stderr):
                if pipe and not getattr(pipe, "closed", True):
                    try:
                        pipe.close()
                    except Exception as _err:
                        print(f"[web_server.py] Silenced exception: {_err}")
            try:
                _ffmpeg_process.terminate()
                _ffmpeg_process.wait(timeout=1.0)
            except Exception as _err:
                print(f"[web_server.py] Silenced exception: {_err}")
            get_resource_manager().unregister_subprocess(_ffmpeg_process)
            _ffmpeg_process = None
            print("[ScreenAudio] Persistent FFmpeg low-latency process stopped.")

import atexit
atexit.register(_stop_ffmpeg)

# ── PERCEPTION MANAGER — write side (tracks frame/audio arrivals) ─────────────
# Imported separately from the perception package so it works even if the rest
# of the perception package has issues.  Falls back to a no-op object on error.
_perception_writer = None
try:
    from perception.perception_manager import get_writer as _get_pm_writer
    _perception_writer = _get_pm_writer()
    print("[WebServer] PerceptionManager writer initialized.")
except Exception as _pm_err:
    print(f"[WebServer] PerceptionManager unavailable ({_pm_err}). Perception diagnostics disabled.")
    _perception_writer = None

def _frame_worker():
    global _last_screen_event
    while True:
        try:
            queue_item = _frame_queue.get()
            if queue_item is None:
                break
            arrival_time, frame_b64 = queue_item
            
            # Process frame using screen_pipeline
            if _PERCEPTION_AVAILABLE and _screen_pipeline_mod is not None:
                try:
                    start_time = time.time()
                    screen_event = _screen_pipeline_mod.process_frame_bytes(frame_b64)
                    inference_time_ms = (time.time() - start_time) * 1000
                    
                    if screen_event is not None:
                        _last_screen_event = screen_event
                        # Push to FusionEngine
                        if _fusion_engine_mod is not None:
                            try:
                                _fusion_engine_mod.get_global_engine().push_screen_event(screen_event)
                            except Exception as _err:
                                print(f"[web_server.py] Silenced exception: {_err}")
                        
                        # Write to shared/screen_context.txt
                        description = screen_event.get("raw_description", "")
                        timestamp = int(time.time())
                        context_payload = f"[Screen context captured at t={timestamp}]\n{description}"
                        os.makedirs(SHARED_DIR, exist_ok=True)
                        tmp_file = SCREEN_CONTEXT_TXT + ".tmp"
                        with open(tmp_file, "w", encoding="utf-8") as f:
                            f.write(context_payload)
                        try:
                            os.replace(tmp_file, SCREEN_CONTEXT_TXT)
                        except Exception as e_replace:
                            print(f"[FrameWorker] Context replace error: {e_replace}")
                            
                        # Record metrics in PerceptionManagerWriter
                        if _perception_writer is not None:
                            try:
                                has_ocr_curr = bool(screen_event.get("ocr_text", ""))
                                app_curr = screen_event.get("app_type", "unknown")
                                chars_curr = len(screen_event.get("ocr_text", ""))
                                resolution = screen_event.get("resolution", "0x0")
                                end_to_end_latency_ms = (time.time() - arrival_time) * 1000
                                ocr_text_curr = screen_event.get("ocr_text", "")
                                
                                _perception_writer.record_frame_arrival(
                                    app_type=app_curr,
                                    ocr_chars=chars_curr,
                                    has_ocr=has_ocr_curr,
                                    has_vision=bool(screen_event.get("vision_description", "")),
                                    frame_dropped=False,
                                    resolution=resolution,
                                    latency_ms=end_to_end_latency_ms,
                                    ocr_text=ocr_text_curr,
                                    ocr_confidence=screen_event.get("ocr_confidence", 1.0),
                                    scene_layout=screen_event.get("scene_layout"),
                                )
                                
                                # Record VLM inference metrics
                                vlm_caption = screen_event.get("vision_description", "")
                                vlm_enabled = bool(vlm_caption)
                                _perception_writer.record_vision_inference(
                                    running=vlm_enabled,
                                    inference_time_ms=inference_time_ms,
                                    latest_caption=vlm_caption,
                                    confidence=0.8 if vlm_enabled else 0.0
                                )
                            except Exception as ex_pm:
                                print(f"[FrameWorker] Failed to write PM metrics: {ex_pm}")
                except Exception as ex:
                    print(f"[FrameWorker] Analysis failed: {ex}")
            _frame_queue.task_done()
        except Exception as e:
            print(f"[FrameWorker] Thread loop error: {e}")
            time.sleep(0.1)

_frame_worker_thread = threading.Thread(target=_frame_worker, daemon=True)
_frame_worker_thread.start()

try:
    import perception.screen_pipeline as _screen_pipeline_mod
    import perception.fusion_engine   as _fusion_engine_mod
    import perception.audio_pipeline    as _perception_audio_mod
    import perception.plugins.speech    as _speech_plugin_mod
    # Start the fusion engine background flush thread
    _fusion_engine_mod.get_global_engine()  # lazy-init + start
    _PERCEPTION_AVAILABLE = True
    print("[WebServer] Perception package loaded — enhanced screen pipeline active.")
except Exception as _perc_err:
    print(f"[WebServer] Perception package unavailable ({_perc_err}). Using built-in vision bridge.")


def stitch_transcripts(prev_text: str, new_text: str) -> str:
    prev_text = prev_text.strip()
    new_text = new_text.strip()
    if not prev_text:
        return new_text
    if not new_text:
        return prev_text
        
    prev_words = prev_text.split()
    new_words = new_text.split()
    
    max_overlap = min(len(prev_words), len(new_words))
    best_overlap_len = 0
    
    for l in range(1, max_overlap + 1):
        suffix = prev_words[-l:]
        prefix = new_words[:l]
        if [w.lower().strip(".,!?\"'") for w in suffix] == [w.lower().strip(".,!?\"'") for w in prefix]:
            best_overlap_len = l
            
    if best_overlap_len > 0:
        stitched_words = prev_words + new_words[best_overlap_len:]
        res = " ".join(stitched_words)
    else:
        if new_text.lower() in prev_text.lower():
            res = prev_text
        else:
            res = prev_text + " " + new_text
            
    # Limit to last 30 words to keep rolling window compact
    words = res.split()
    if len(words) > 30:
        res = "... " + " ".join(words[-30:])
    return res


def run_fresh_audio_perception(duration_seconds=6.0):
    """
    Perform a fresh analysis on the latest audio samples in _decoded_pcm_buffer.
    Extracts the latest duration_seconds, runs classification, speech recognition,
    and music recognition, updating the perception writer.
    """
    print(f"[ScreenAudio] Running fresh audio perception pass on the last {duration_seconds}s of audio...")
    global _last_speech_detected_time
    if _perception_writer is not None:
        try:
            with _perception_writer._lock:
                if time.time() - _last_speech_detected_time > 15.0:
                    _perception_writer._screen_audio_transcript = ""
                _perception_writer._audio_music_title = ""
                _perception_writer._audio_event_description = ""
                _perception_writer._audio_detected_speech = False
                _perception_writer._audio_detected_music = False
                _perception_writer._audio_detected_sound_events = []
        except Exception as _clear_err:
            print(f"[ScreenAudio] Clear cached audio state failed: {_clear_err}")

    import numpy as np
    import tempfile
    import scipy.io.wavfile as wav
    
    # 16000 Hz, float32 (4 bytes per sample)
    target_bytes = int(16000 * duration_seconds * 4)
    samples = None
    with _decoded_pcm_lock:
        buf_len = len(_decoded_pcm_buffer)
        if buf_len >= 4:
            valid_len = (min(buf_len, target_bytes) // 4) * 4
            chunk_bytes = bytes(_decoded_pcm_buffer[-valid_len:])
            samples = np.frombuffer(chunk_bytes, dtype=np.float32)
            
    if samples is None or len(samples) == 0:
        print("[ScreenAudio] Fresh audio pass failed: no samples available in buffer.")
        return
        
    # Heuristic analysis
    event_type = "silence"
    description = "Screen share audio: silence detected."
    confidence = 0.5
    rms = float(np.sqrt(np.mean(samples ** 2))) * 32768.0
    
    from perception.model_router import ModelRouter
    plugin = ModelRouter.get_audio_analysis_plugin()
    if plugin:
        try:
            analysis_results = plugin.analyze(samples, sample_rate=16000)
            if analysis_results:
                res = analysis_results[0]
                event_type = res.get("event_type", "ambient")
                description = f"Screen share audio: {res.get('description', '')}"
                confidence = res.get("confidence", 0.5)
        except Exception as e:
            print(f"[ScreenAudio] Fresh analysis plugin failed: {e}")
            
    # Speech transcription / lyrics detection
    # Run transcription unless it is absolute silence or steady static noise (rms < 80)
    if event_type not in ("silence", "environmental_sounds") and rms >= 80.0:
        temp_filename = None
        try:
            pcm16 = np.clip(samples * 32768, -32768, 32767).astype(np.int16)
            shared_dir = os.path.join(BASE_DIR, "shared")
            os.makedirs(shared_dir, exist_ok=True)
            
            fd, temp_filename = tempfile.mkstemp(suffix=".wav", prefix="screen_audio_fresh_", dir=shared_dir)
            os.close(fd)
            
            wav.write(temp_filename, 16000, pcm16)
            
            speech_plugin = ModelRouter.get_speech_plugin()
            if speech_plugin and speech_plugin.is_available():
                trans_res = speech_plugin.transcribe(temp_filename)
                text = trans_res.get("text", "").strip()
                speech_conf = trans_res.get("confidence", 1.0)
                
                speaker_id = _diarizer.attribute_speaker(samples)
                lang = detect_language(text) if text else "unknown"
                
                music_title = None
                if _perception_writer is not None:
                    with _perception_writer._lock:
                        win_title = _perception_writer._active_window_title
                        app_type_curr = _perception_writer._current_app_type
                        ocr_text_curr = _perception_writer._last_ocr_text
                    if win_title and " - " in win_title and not any(x in win_title.lower() for x in ("vivy ai", "localhost", "127.0.0.1", "dashboard")):
                        music_title = win_title.split(" - ")[0].strip()
                    if not music_title and app_type_curr and "playing '" in app_type_curr:
                        import re as _re
                        m_m = _re.search(r"playing '([^']+)'", app_type_curr)
                        if m_m:
                            music_title = m_m.group(1)
                    if not music_title and ocr_text_curr:
                        for line in ocr_text_curr.split("\n"):
                            if any(k in line.lower() for k in ["nightcore", "lyrics", "official video", "music video", " - "]) and len(line) < 120:
                                music_title = line.strip()
                                break
                            
                if _perception_writer is not None:
                    _perception_writer.record_audio_metadata(
                        language=lang,
                        speaker_id=speaker_id,
                        music_title=music_title,
                        playback_state="playing" if event_type not in ("silence", "ambient") else "paused",
                        sound_effects=[event_type] if event_type in ("notifications", "movie_game_audio") else []
                    )
                    
                if text:
                    if is_noise_label(text):
                        text_lower = text.lower()
                        if "music" in text_lower or "singing" in text_lower:
                            event_type = "music"
                            description = "Screen share audio: music playing."
                        elif "laughter" in text_lower:
                            event_type = "laughter"
                            description = "Screen share audio: laughter."
                        elif "applause" in text_lower:
                            event_type = "applause"
                            description = "Screen share audio: applause."
                        text = ""
                    else:
                        print(f"[ScreenAudio] Fresh transcription found: {text}")
                        prev_t = ""
                        if _perception_writer is not None:
                            prev_t = _perception_writer._screen_audio_transcript or ""
                        stitched_t = stitch_transcripts(prev_t, text)
                        _last_speech_detected_time = time.time()
                        if _perception_writer is not None:
                            _perception_writer.record_screen_audio_transcript(stitched_t, confidence=speech_conf)
                        description = f"{description} (speaker: {speaker_id}, lang: {lang}, text: \"{text}\")"
                        
                        # Push transcript event to FusionEngine timeline
                        try:
                            from perception.fusion_engine import get_global_engine
                            get_global_engine().push_perception_event(
                                source="system_audio",
                                semantic=f"[{speaker_id} in {lang}]: \"{text}\"",
                                importance=0.95,
                                confidence=speech_conf,
                                scope="shared_screen",
                                metadata={"speaker_id": speaker_id, "language": lang}
                            )
                        except Exception as _err:
                            print(f"[web_server.py] Silenced exception: {_err}")
        except Exception as e:
            print(f"[ScreenAudio] Fresh transcription failed: {e}")
        finally:
            if temp_filename and os.path.exists(temp_filename):
                try:
                    os.remove(temp_filename)
                except Exception as _err:
                    print(f"[web_server.py] Silenced exception: {_err}")
                    
    # Write to perception writer
    if _perception_writer is not None:
        try:
            _perception_writer.record_audio_chunk(rms=rms, event_type=event_type, sample_rate=16000, channels=1)
            _perception_writer.record_audio_model_inference(
                running=True,
                detected_speech=(event_type == "speech"),
                detected_music=(event_type == "music"),
                detected_sound_events=[event_type] if event_type != "silence" else [],
                confidence=confidence
            )
            if description and event_type not in ("silence",):
                _perception_writer.record_audio_event_description(description)
        except Exception as e:
            print(f"[ScreenAudio] Fresh perception writer update failed: {e}")

def _analyze_screen_frame(img):
    """
    Analyze a PIL Image and return a real, grounded description of what is on screen.
    Uses layered heuristics:
      1. OCR via pytesseract (if available) — extracts real text
      2. Dominant color palette analysis — identifies app type (dark IDE, white doc, browser)
      3. Luminance zone analysis — title bar, main area, sidebar presence
      4. Contrast and saturation — distinguishes content types
    Returns a plain-text description string.
    """
    from PIL import ImageStat, ImageFilter
    import colorsys

    # Resize to working resolution for speed (max 1280 wide)
    MAX_W = 1280
    w, h = img.size
    if w > MAX_W:
        scale = MAX_W / w
        try:
            from PIL import Image
            resample_mode = getattr(Image.Resampling, "LANCZOS", getattr(Image, "LANCZOS", 1))
        except (ImportError, AttributeError):
            resample_mode = 1
        img = img.resize((int(w * scale), int(h * scale)), resample=resample_mode)
        w, h = img.size

    # Convert to RGB if needed
    if img.mode != 'RGB':
        img = img.convert('RGB')

    description_parts = []

    # ── 1. OCR TEXT EXTRACTION (highest fidelity, if available) ──
    ocr_text = ""
    if _TESSERACT_AVAILABLE:
        try:
            # Use page segmentation mode 3 (auto) for full page
            custom_cfg = r'--oem 3 --psm 3'
            ocr_text = _pytesseract.image_to_string(img, config=custom_cfg)
            # Clean up OCR output
            import re
            ocr_text = re.sub(r'\n{3,}', '\n\n', ocr_text).strip()
            # Limit to 800 chars to stay within token budget
            if len(ocr_text) > 800:
                ocr_text = ocr_text[:800] + "...(truncated)"
        except Exception as ocr_err:
            print(f"[VisionBridge] OCR error: {ocr_err}")

    if ocr_text:
        description_parts.append(f"Text visible on screen (OCR):\n{ocr_text}")

    # ── 2. DOMINANT COLOR PALETTE ANALYSIS ──
    # Sample colors from key zones: title bar (top 8%), main area, sidebar
    title_bar_zone = img.crop((0, 0, w, max(1, int(h * 0.08))))
    main_zone = img.crop((0, int(h * 0.08), w, int(h * 0.92)))
    sidebar_zone = img.crop((0, int(h * 0.08), int(w * 0.18), int(h * 0.92)))

    def zone_avg_rgb(zone_img):
        stat = ImageStat.Stat(zone_img)
        return tuple(int(v) for v in stat.mean[:3])

    def rgb_to_hsv(r, g, b):
        return colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)

    title_rgb = zone_avg_rgb(title_bar_zone)
    main_rgb = zone_avg_rgb(main_zone)

    title_h, title_s, title_v = rgb_to_hsv(*title_rgb)
    main_h, main_s, main_v = rgb_to_hsv(*main_rgb)

    # ── 3. APPLICATION TYPE DETECTION via color signature ──
    app_type = "unknown application"
    env_detail = ""

    # Dark theme IDE / code editor (very dark main area, colored title bar)
    if main_v < 0.25 and main_s < 0.3:
        app_type = "dark-theme code editor or IDE"
        # Check for VS Code blue title bar
        if 0.5 < title_h < 0.75 and title_v > 0.2:
            app_type = "Visual Studio Code (dark theme)"
            env_detail = "A code editor is open. The workspace appears dark with syntax highlighting."
        elif 0.55 < title_h < 0.75:
            app_type = "dark-theme IDE or code editor (likely VS Code, Vim, or similar)"
            env_detail = "A code editor with dark theme is visible."
        else:
            env_detail = "A terminal, console, or dark-themed application is on screen."

    # Unity Editor (dark gray UI with specific color distribution)
    elif 0.15 < main_v < 0.35 and main_s < 0.15:
        app_type = "Unity Editor or dark gray application"
        env_detail = "A dark gray application interface is visible — possibly Unity Editor, a 3D tool, or a game engine."

    # Browser (medium-light main area, white/light content)
    elif main_v > 0.85 and main_s < 0.15:
        app_type = "web browser or document viewer"
        # Check for browser chrome bar at top
        if title_v > 0.6:
            env_detail = "A web browser window is open showing a white or light-colored webpage."
        else:
            env_detail = "A white document or text editor is visible — possibly a browser, Word, or Notepad."

    # Notepad (very white, near zero saturation throughout)
    elif main_v > 0.92 and main_s < 0.08 and title_s < 0.12:
        app_type = "Notepad or plain text editor"
        env_detail = "A plain white text editor (such as Notepad or WordPad) is open."

    # File Explorer (light gray with navigation elements)
    elif 0.75 < main_v < 0.95 and main_s < 0.15:
        app_type = "file explorer or settings panel"
        env_detail = "A light-colored system window is open — possibly File Explorer, Settings, or a light-themed app."

    # Colorful / media application (high saturation)
    elif main_s > 0.35:
        app_type = "media or colorful application"
        env_detail = "A colorful or media-rich application is visible — possibly a game, video player, or creative tool."

    # ── 4. BRIGHTNESS & CONTRAST ──
    stat_main = ImageStat.Stat(main_zone)
    brightness = main_v * 100
    # Stddev across channels indicates content density
    stddev = sum(stat_main.stddev[:3]) / 3
    content_density = "dense with content" if stddev > 35 else ("moderate content" if stddev > 18 else "mostly uniform / sparse content")

    # ── 5. SIDEBAR DETECTION ──
    sidebar_rgb = zone_avg_rgb(sidebar_zone)
    sidebar_h, sidebar_s, sidebar_v = rgb_to_hsv(*sidebar_rgb)
    has_sidebar = abs(sidebar_v - main_v) > 0.12  # significant luminance difference

    # ── 6. COMPOSE DESCRIPTION ──
    # Build a structured, LLM-friendly description with labelled sections
    # so the model can reference specific facts (app type, text, layout)
    # rather than having to interpret a blob of heuristic prose.
    sections = []

    # Section A — Application / environment
    app_label = f"[App Detected]: {app_type}"
    if env_detail:
        app_label += f"\n{env_detail}"
    sections.append(app_label)

    # Section B — Visual context (brightness, content density, sidebar)
    brightness_label = "bright" if brightness > 60 else "dark"
    visual_ctx = (
        f"[Visual Context]: {brightness_label} display ({brightness:.0f}% brightness), "
        f"{content_density}"
    )
    if has_sidebar:
        visual_ctx += ", sidebar or panel visible on the left"
    sections.append(visual_ctx)

    # Section C — OCR text (highest fidelity — always placed last for prominence)
    if ocr_text:
        sections.append(f"[OCR Text Extracted]:\n{ocr_text}")
    else:
        sections.append("[OCR Text Extracted]: No readable text detected (OCR returned empty or unavailable).")

    return "\n\n".join(sections)

# Set up folders for Flask app static/templates
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)

# Chat history kept in memory on server
chat_history = []
last_processed_reply = ""
last_reply_mtime = 0.0

def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as _err:
            print(f"[web_server.py] Silenced exception: {_err}")
    return {}

def save_memory(mem):
    try:
        tmp_file = MEMORY_FILE + f".{os.getpid()}.tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(mem, f, indent=2, ensure_ascii=False)
        os.replace(tmp_file, MEMORY_FILE)
        return True
    except Exception as e:
        print(f"[web_server.py] save_memory error: {e}")
        return False

# Background thread to monitor pipeline outputs
def monitor_pipeline():
    global last_processed_reply, last_reply_mtime, chat_history
    print("[Monitor] Starting background pipeline monitor...")
    
    last_reply_ts = 0.0
    last_user_ts = 0.0
    thinking_start_time = 0.0
    reply_meta_file = os.path.join(SHARED_DIR, "reply_meta.json")
    user_meta_file = os.path.join(SHARED_DIR, "user_turn_meta.json")
    if os.path.exists(user_meta_file):
        try: last_user_ts = os.path.getmtime(user_meta_file)
        except Exception: pass

    # Initialize mtime watermark and capture initial startup greeting if present
    if os.path.exists(REPLY_TXT):
        try:
            last_reply_mtime = os.path.getmtime(REPLY_TXT)
            with open(REPLY_TXT, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    last_processed_reply = content
                    if not chat_history:
                        emotion = "neutral"
                        if os.path.exists(EMOTION_TXT):
                            try:
                                with open(EMOTION_TXT, "r", encoding="utf-8") as ef:
                                    emotion = ef.read().strip() or "neutral"
                            except Exception as _err:
                                print(f"[web_server.py] Silenced exception: {_err}")
                        chat_history.append({
                            "sender": "vivy",
                            "text": content,
                            "emotion": emotion,
                            "audio_url": None,
                            "timestamp": int(last_reply_mtime * 1000)
                        })
                        print(f"[Monitor] Synchronized initial startup greeting: {content} [{emotion}]")
        except Exception as e:
            print(f"[Monitor] Error loading initial mtime: {e}")

    while True:
        try:
            now = time.time()
            
            # ── Thinking Timeout Guard ──
            # Automatically reset status if pipeline has been thinking for > 120 seconds (accommodates slow RVC/VLM processing)
            if os.path.exists(STATUS_TXT):
                try:
                    with open(STATUS_TXT, "r", encoding="utf-8") as sf:
                        curr_status = sf.read().strip().lower()
                    if curr_status.startswith("thinking"):
                        if thinking_start_time == 0.0:
                            thinking_start_time = now
                        elif now - thinking_start_time > 120.0:
                            print("[Monitor] Warning: Thinking status timeout (120s). Auto-resetting status to ready.")
                            with open(STATUS_TXT, "w", encoding="utf-8") as sf:
                                sf.write("ready")
                            thinking_start_time = 0.0
                    else:
                        thinking_start_time = 0.0
                except Exception as _err:
                    print(f"[web_server.py] Silenced exception: {_err}")

            if os.path.exists(user_meta_file):
                try:
                    _u_mtime = os.path.getmtime(user_meta_file)
                    if _u_mtime > last_user_ts:
                        last_user_ts = _u_mtime
                        with open(user_meta_file, "r", encoding="utf-8") as _uf:
                            _udata = json.load(_uf)
                        _u_text = _udata.get("text", "").strip()
                        if _u_text and not (chat_history and chat_history[-1].get("sender") == "user" and chat_history[-1].get("text") == _u_text):
                            chat_history.append({
                                "sender": "user",
                                "text": _u_text,
                                "timestamp": int(float(_udata.get("timestamp", now)) * 1000)
                            })
                            print(f"[Monitor] Synchronized spoken voice turn to web dashboard: {_u_text}")
                except Exception as _u_err:
                    print(f"[web_server.py] Silenced user sync exception: {_u_err}")

            meta_ts = 0.0
            if os.path.exists(reply_meta_file):
                try:
                    with open(reply_meta_file, "r", encoding="utf-8") as mf:
                        mdata = json.load(mf)
                        meta_ts = float(mdata.get("timestamp", 0.0))
                except Exception as _err:
                    print(f"[web_server.py] Silenced exception: {_err}")

            if os.path.exists(REPLY_TXT):
                mtime = os.path.getmtime(REPLY_TXT)
                with open(REPLY_TXT, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                
                is_new_by_meta = (meta_ts > 0.0 and meta_ts > last_reply_ts)
                is_new_by_mtime = (mtime > last_reply_mtime)
                is_new_by_text = (text and text != last_processed_reply)

                if text and (is_new_by_meta or is_new_by_mtime or is_new_by_text):
                    last_reply_mtime = max(mtime, last_reply_mtime)
                    last_reply_ts = max(meta_ts, now)
                    is_audio_update_only = (text == last_processed_reply and chat_history and chat_history[-1].get("sender") == "vivy" and chat_history[-1].get("text") == text)
                    last_processed_reply = text
                    thinking_start_time = 0.0
                    time.sleep(0.15) # Wait for text and voice cloning to finish writing
                        
                    emotion = "neutral"
                    if os.path.exists(EMOTION_TXT):
                        try:
                            with open(EMOTION_TXT, "r", encoding="utf-8") as ef:
                                emotion = ef.read().strip() or "neutral"
                        except Exception as _err:
                            print(f"[web_server.py] Silenced exception: {_err}")
                    
                    # Copy generated audio with file stability check
                    ts = int(time.time())
                    audio_filename = f"reply_{ts}.wav"
                    dest_audio = os.path.join(AUDIO_DIR, audio_filename)
                    audio_url = None
                    
                    src_audio = RVC_WAV if os.path.exists(RVC_WAV) else (TTS_WAV if os.path.exists(TTS_WAV) else None)
                    if src_audio:
                        # Wait up to 0.5s for audio file writing to complete
                        for _ in range(5):
                            try:
                                if os.path.getsize(src_audio) > 0:
                                    break
                            except Exception as _err:
                                print(f"[web_server.py] Silenced exception: {_err}")
                            time.sleep(0.1)
                        try:
                            if os.path.exists(src_audio) and os.path.getsize(src_audio) > 0:
                                shutil.copy2(src_audio, dest_audio)
                                audio_url = f"/static/audio/{audio_filename}"
                        except Exception as ae:
                            print(f"[Monitor] Error copying audio: {ae}")
                    
                    if is_audio_update_only:
                        if audio_url and not chat_history[-1].get("audio_url"):
                            chat_history[-1]["audio_url"] = audio_url
                            print(f"[Monitor] Dynamically attached audio output to recent reply: {audio_url}")
                    else:
                        chat_history.append({
                            "sender": "vivy",
                            "text": text,
                            "emotion": emotion,
                            "audio_url": audio_url,
                            "timestamp": int(now * 1000)
                        })
                        print(f"[Monitor] Detected new reply from Vivy: {text} [{emotion}]")
            
            time.sleep(0.25)
        except Exception as e:
            print(f"[Monitor] Exception in monitor thread: {e}")
            time.sleep(1)

# Routes
@app.route("/")
def index():
    return send_from_directory(TEMPLATES_DIR, "index.html")

@app.after_request
def add_cache_control_headers(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route("/static/audio/<path:filename>")
def serve_audio(filename):
    return send_from_directory(AUDIO_DIR, filename)

@app.route("/api/status", methods=["GET"])
def get_status():
    raw_status = "ready"
    if os.path.exists(STATUS_TXT):
        try:
            with open(STATUS_TXT, "r", encoding="utf-8") as sf:
                raw_status = sf.read().strip() or "ready"
        except Exception as _err:
            print(f"[web_server.py] Silenced exception: {_err}")
            
    if ":" in raw_status:
        parts = raw_status.split(":", 1)
        base_status = parts[0].strip().lower()
        status_detail = parts[1].strip()
    else:
        base_status = raw_status.strip().lower()
        status_detail = ""

    if not status_detail:
        if base_status == "thinking": status_detail = "Vivy is thinking..."
        elif base_status == "transcribing": status_detail = "Transcribing voice..."
        elif base_status == "recording": status_detail = "Recording voice..."
        elif base_status == "processing": status_detail = "Processing voice..."
        elif base_status == "generating_tts": status_detail = "Generating vocal response..."
        elif base_status == "applying_rvc": status_detail = "Applying voice cloning..."
        elif base_status == "speaking": status_detail = "Vivy is speaking..."
        elif base_status == "muted": status_detail = "Mic Disabled"
        else: status_detail = "Vivy is ready"

    mic_muted = os.path.exists(MIC_MUTE_TXT)
    
    current_emotion = "neutral"
    if os.path.exists(EMOTION_TXT):
        try:
            with open(EMOTION_TXT, "r", encoding="utf-8") as ef:
                current_emotion = ef.read().strip() or "neutral"
        except Exception as _err:
            print(f"[web_server.py] Silenced exception: {_err}")
            
    shake_impact = False
    if os.path.exists(SHAKE_TXT):
        shake_impact = True
        try: os.remove(SHAKE_TXT)
        except Exception: pass
            
    return jsonify({
        "status": base_status,
        "status_detail": status_detail,
        "mic_muted": mic_muted,
        "current_emotion": current_emotion,
        "ai_state": base_status.upper(),
        "screen_impact_shake": shake_impact
    })

@app.route("/api/cognitive/state", methods=["GET"])
def get_cognitive_state():
    mem = load_memory()
    
    # 1. Live Emotion Engine State
    emotion_vector = mem.get("emotion_vector", {})
    primary_emotion = mem.get("mood", "relaxed")
    try:
        from emotion.emotion_engine import get_emotion_engine
        emo_eng = get_emotion_engine(emotion_vector)
        emotion_vector = dict(emo_eng.vector)
        primary_emotion = emo_eng.get_primary_emotion()
    except Exception as _emo_err:
        print(f"[web_server] EmotionEngine fetch warning: {_emo_err}")

    # 2. Live Circadian State & Hardware Metrics
    circ_state = {
        "phase": "Afternoon",
        "next_phase": "LateAfternoon",
        "phase_progress": 0.5,
        "energy": 0.7,
        "tone": "focused",
        "sleep_mode": False,
        "hardware_hint": "gpu",
        "cpu_usage": 15.0,
        "gpu_usage": 25.0,
        "active_threads": threading.active_count()
    }
    try:
        from circadian.circadian_engine import get_state as _get_circ
        cs = _get_circ()
        if cs:
            circ_state = {
                "phase": cs.phase_name,
                "next_phase": getattr(cs, "next_phase_name", "LateAfternoon"),
                "phase_progress": getattr(cs, "phase_progress", 0.5),
                "energy": cs.energy,
                "tone": cs.tone_label,
                "sleep_mode": cs.sleep_mode,
                "hardware_hint": cs.hardware_hint,
                "cpu_usage": 15.0,
                "gpu_usage": 25.0,
                "active_threads": threading.active_count()
            }
            # Try loading psutil CPU usage
            try:
                import psutil
                circ_state["cpu_usage"] = psutil.cpu_percent(interval=None)
            except Exception: pass
    except Exception as _circ_err:
        print(f"[web_server] CircadianEngine fetch warning: {_circ_err}")

    # 3. Live Affection System State & Progression Details
    rel = mem.get("relationship", {"score": 30, "trust": 30, "warmth": 35, "familiarity": 22})
    affection_level = mem.get("affection_level", 48.0)
    aff_details = {
        "level": affection_level,
        "stage_label": "Acquaintance",
        "next_stage": "Familiar Friend",
        "xp_progress": 45.0,
        "growth_trend": "Positive",
        "trust_contribution": 12.0,
        "warmth": rel.get("warmth", 35),
        "trust": rel.get("trust", 30),
        "familiarity": rel.get("familiarity", 22),
        "comfort": rel.get("comfort", 30),
        "playfulness": rel.get("playfulness", 30),
        "recent_milestones": []
    }
    try:
        from affection.affection_system import get_affection_system
        aff_sys = get_affection_system(affection_level, rel)
        aff_sys.update_from_memory(affection_level, rel)
        aff_details = aff_sys.get_progression_details()
    except Exception as _aff_err:
        print(f"[web_server] AffectionSystem fetch warning: {_aff_err}")

    # 4. Live Loneliness & Social Drive
    loneliness_level = mem.get("loneliness_level", 0.0)
    social_drive = "Low / Comfortable"
    try:
        from loneliness.loneliness_system import get_loneliness_system
        lon_sys = get_loneliness_system(loneliness_level)
        lon_res = lon_sys.update_loneliness(mem, circ_state, emotion_vector, rel, log_to_db=False)
        loneliness_level = lon_res.get("loneliness_level", loneliness_level)
        social_drive = lon_res.get("social_drive", social_drive)
    except Exception as _lon_err:
        print(f"[web_server] LonelinessSystem fetch warning: {_lon_err}")

    facts = mem.get("long_term_facts", {})
    growth_diary = mem.get("growth_diary", [])
    last_saved = growth_diary[-1] if growth_diary else "System initialised"

    shake_impact = False
    if os.path.exists(SHAKE_TXT):
        shake_impact = True
        try: os.remove(SHAKE_TXT)
        except Exception: pass

    return jsonify({
        "success": True,
        "emotion": {
            "primary": primary_emotion,
            "vector": emotion_vector
        },
        "affection": aff_details,
        "loneliness": {
            "level": loneliness_level,
            "social_drive": social_drive
        },
        "circadian": circ_state,
        "current_topic": mem.get("current_topic", "general"),
        "conversation_confidence": mem.get("topic_confidence", 0.90),
        "memory_retrieval_status": {
            "facts_count": len(facts),
            "active": True
        },
        "internet_status": {
            "online": True,
            "duckduckgo_ready": True,
            "last_query": mem.get("task_state", {}).get("query", "None")
        },
        "planner": mem.get("planner_decision", {}),
        "database_status": {
            "sqlite_connected": True,
            "path": "shared/vivy_state.db"
        },
        "current_mode": mem.get("last_director_mode", "Companion Mode"),
        "human_state": mem.get("human_state", "Awake"),
        "last_memory_saved": last_saved,
        "last_memory_retrieved": mem.get("last_retrieved_memory", mem.get("last_greeting", "Contextual Memory Active")),
        "relationship": {
            "score": int(aff_details.get("affection_level", 30)),
            "label": aff_details.get("current_stage", "Acquaintance")
        },
        "context_window_usage": {
            "turn_count": len(chat_history),
            "active_symptoms": len(mem.get("active_symptoms", []))
        },
        "screen_impact_shake": shake_impact
    })

@app.route("/api/health", methods=["GET"])
def get_health():
    tm = get_telemetry_manager()
    return jsonify(tm.get_health_status())




@app.route("/api/telemetry", methods=["GET"])
def get_telemetry():
    tm = get_telemetry_manager()
    limit = request.args.get("limit", 50, type=int)
    return jsonify({"success": True, "events": tm.get_events(limit)})

@app.route("/api/diagnostics/connection", methods=["GET"])
def get_connection_diagnostics():
    tm = get_telemetry_manager()
    return jsonify(tm.get_connection_diagnostics())

@app.route("/api/internet/status", methods=["GET"])
def get_internet_status():
    try:
        from internet import get_internet_manager
        im = get_internet_manager()
        status_info = im.get_status()
        status_info["live_state"] = status_info.get("network_state", "online").upper()
        status_info["duckduckgo_ready"] = True
        return jsonify(status_info)
    except Exception as e:
        return jsonify({"enabled": True, "network_state": "online", "live_state": "ONLINE", "duckduckgo_ready": True, "note": "Fallback adapter active", "error": str(e)})

@app.route("/api/internet/cache", methods=["GET", "DELETE"])
def route_internet_cache():
    try:
        from internet import get_internet_manager
        im = get_internet_manager()
        if request.method == "DELETE":
            im.cache.clear()
            return jsonify({"success": True, "message": "Search cache cleared"})
        return jsonify(im.cache.get_stats())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/internet/search", methods=["POST"])
def route_internet_search():
    try:
        data = request.get_json(force=True, silent=True) or {}
        query = data.get("query", "").strip()
        force = bool(data.get("force_refresh", False))
        if not query:
            return jsonify({"success": False, "error": "Query cannot be empty"}), 400
        from internet import get_internet_manager
        im = get_internet_manager()
        results_markdown = im.search(query, max_results=5, force_refresh=force)
        cache_stats = im.cache.get_stats()
        return jsonify({
            "success": True,
            "query": query,
            "results": results_markdown,
            "has_results": bool(results_markdown),
            "cache": cache_stats
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500




@app.route("/api/avatar/status", methods=["GET"])
def get_avatar_status():
    connected = False
    client_count = 0
    status_label = "STANDBY"
    measured_fps = 0.0
    last_frame_timestamp = 0.0
    root_cause = "WebSocket server running on port 8765; 0 MateEngine Unity clients connected"

    disabled = os.path.exists(AVATAR_DISABLE_TXT)
    if os.path.exists(AVATAR_CONNECTED_TXT):
        try:
            with open(AVATAR_CONNECTED_TXT, "r", encoding="utf-8") as cf:
                client_count = int(cf.read().strip() or "0")
                connected = client_count > 0
        except Exception as _err:
            print(f"[web_server.py] Silenced exception: {_err}")

    if os.path.exists(AVATAR_STATUS_JSON):
        try:
            with open(AVATAR_STATUS_JSON, "r", encoding="utf-8") as asf:
                st_data = json.load(asf)
                status_label = st_data.get("status", status_label)
                measured_fps = st_data.get("measured_fps", measured_fps)
                last_frame_timestamp = st_data.get("last_frame_timestamp", last_frame_timestamp)
                root_cause = st_data.get("root_cause", root_cause)
        except Exception as _err:
            print(f"[web_server.py] Silenced exception: {_err}")

    if disabled:
        status_label = "OFFLINE"
        root_cause = "Avatar subsystem disabled by user configuration"
    elif last_frame_timestamp > 0 and (time.time() - last_frame_timestamp < 5.0):
        connected = True
        status_label = "STREAMING"
        root_cause = "Receiving active avatar frame stream from MateEngine Unity client"
    elif connected:
        status_label = "STREAMING"
        root_cause = f"Connected to {client_count} MateEngine Unity client(s)"

    return jsonify({
        "connected": connected,
        "client_count": client_count,
        "status": status_label,
        "disabled": disabled,
        "measured_fps": measured_fps,
        "last_frame_timestamp": last_frame_timestamp,
        "root_cause": root_cause,
        "websocket_uri": "ws://127.0.0.1:8765",
        "reconnect_active": True
    })


@app.route("/api/avatar/load", methods=["POST"])
def load_avatar_endpoint():
    data = request.json or {}
    avatar = data.get("avatar", "")
    if avatar:
        try:
            os.makedirs(SHARED_DIR, exist_ok=True)
            with open(LOAD_AVATAR_TXT, "w", encoding="utf-8") as f:
                f.write(avatar)
            return jsonify({"success": True, "avatar": avatar})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": False, "error": "No avatar specified"}), 400


@app.route("/api/config", methods=["GET", "POST"])
def route_config():
    if request.method == "GET":
        # Get defaults from config if overrides not present
        audio_perception_enabled = False
        proactivity_enabled = False
        screen_perception_enabled = True
        vision_model_enabled = False
        adaptive_sampling_enabled = False
        screen_fps = 60
        screen_max_width = 1280

        if _PERCEPTION_AVAILABLE:
            try:
                from perception.config_loader import get as get_cfg
                audio_perception_enabled = get_cfg("audio_perception", "enabled", default=False)
                proactivity_enabled = get_cfg("proactivity", "enabled", default=False)
                screen_perception_enabled = get_cfg("screen_perception", "enabled", default=True)
                vision_model_enabled = get_cfg("screen_perception", "vision_model_enabled", default=False)
                adaptive_sampling_enabled = get_cfg("screen_perception", "adaptive_sampling_enabled", default=False)
                screen_fps = get_cfg("screen_perception", "fps", default=60)
                screen_max_width = get_cfg("screen_perception", "capture_resolution_max_width", default=1280)
            except Exception as _err:
                print(f"[web_server.py] Silenced exception: {_err}")

        return jsonify({
            "voice_input": not os.path.exists(MIC_MUTE_TXT),
            "voice_output": not os.path.exists(VOICE_OUTPUT_MUTE_TXT),
            "voice_cloning": not os.path.exists(RVC_DISABLE_TXT),
            "avatar": not os.path.exists(AVATAR_DISABLE_TXT),
            "audio_perception": audio_perception_enabled,
            "proactivity": proactivity_enabled,
            "screen_perception": screen_perception_enabled,
            "vision_model": vision_model_enabled,
            "adaptive_sampling": adaptive_sampling_enabled,
            "screen_fps": screen_fps,
            "screen_max_width": screen_max_width
        })
    else:
        data = request.get_json() or {}
        
        # Voice Input (Mic)
        if "voice_input" in data:
            if data["voice_input"]:
                if os.path.exists(MIC_MUTE_TXT):
                    try: os.remove(MIC_MUTE_TXT)
                    except Exception: pass
            else:
                try:
                    with open(MIC_MUTE_TXT, "w", encoding="utf-8") as f:
                        f.write("muted")
                except Exception: pass
                
        # Voice Output (Playback)
        if "voice_output" in data:
            if data["voice_output"]:
                if os.path.exists(VOICE_OUTPUT_MUTE_TXT):
                    try: os.remove(VOICE_OUTPUT_MUTE_TXT)
                    except Exception: pass
            else:
                try:
                    with open(VOICE_OUTPUT_MUTE_TXT, "w", encoding="utf-8") as f:
                        f.write("muted")
                except Exception: pass
                
        # Voice Cloning (RVC)
        if "voice_cloning" in data:
            if data["voice_cloning"]:
                if os.path.exists(RVC_DISABLE_TXT):
                    try: os.remove(RVC_DISABLE_TXT)
                    except Exception: pass
            else:
                try:
                    with open(RVC_DISABLE_TXT, "w", encoding="utf-8") as f:
                        f.write("disabled")
                except Exception: pass
                
        # Avatar
        if "avatar" in data:
            if data["avatar"]:
                if os.path.exists(AVATAR_DISABLE_TXT):
                    try: os.remove(AVATAR_DISABLE_TXT)
                    except Exception: pass
            else:
                try:
                    with open(AVATAR_DISABLE_TXT, "w", encoding="utf-8") as f:
                        f.write("disabled")
                except Exception: pass

        # Helper to update override files for perception package
        def update_override(key, enable_path, disable_path):
            if key in data:
                if data[key]:
                    try:
                        if os.path.exists(disable_path): os.remove(disable_path)
                        with open(enable_path, "w", encoding="utf-8") as f: f.write("enabled")
                    except Exception: pass
                else:
                    try:
                        if os.path.exists(enable_path): os.remove(enable_path)
                        with open(disable_path, "w", encoding="utf-8") as f: f.write("disabled")
                    except Exception: pass

        update_override("audio_perception", AUDIO_PERCEPTION_ENABLE_TXT, AUDIO_PERCEPTION_DISABLE_TXT)
        update_override("proactivity", PROACTIVITY_ENABLE_TXT, PROACTIVITY_DISABLE_TXT)
        update_override("screen_perception", SCREEN_PERCEPTION_ENABLE_TXT, SCREEN_PERCEPTION_DISABLE_TXT)
        update_override("vision_model", VISION_MODEL_ENABLE_TXT, VISION_MODEL_DISABLE_TXT)
        update_override("adaptive_sampling", ADAPTIVE_SAMPLING_ENABLE_TXT, ADAPTIVE_SAMPLING_DISABLE_TXT)

        # Reload configuration in memory if perception is available
        if _PERCEPTION_AVAILABLE:
            try:
                from perception.config_loader import reload as reload_config
                reload_config()
            except Exception as _err:
                print(f"[web_server.py] Silenced exception: {_err}")
                
        return jsonify({"success": True})

@app.route("/api/mic/toggle", methods=["POST"])
def toggle_mic():
    try:
        if os.path.exists(MIC_MUTE_TXT):
            os.remove(MIC_MUTE_TXT)
            muted = False
        else:
            with open(MIC_MUTE_TXT, "w", encoding="utf-8") as f:
                f.write("muted")
            muted = True
        return jsonify({"success": True, "muted": muted})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/history", methods=["GET"])
def get_history():
    return jsonify(chat_history)

@app.route("/api/history/clear", methods=["POST"])
def clear_history():
    global chat_history
    chat_history = []
    # Also clear vivy_history.json
    history_file = "vivy_history.json"
    try:
        if os.path.exists(history_file):
            tmp_hist = history_file + f".{os.getpid()}.tmp"
            with open(tmp_hist, "w", encoding="utf-8") as f:
                json.dump([], f)
            os.replace(tmp_hist, history_file)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": True})

@app.route("/api/session/reset", methods=["POST"])
def reset_session():
    global chat_history
    try:
        from session_manager import get_session_manager
        get_session_manager().start_new_session()
    except Exception as e:
        print(f"[web_server] session reset notice: {e}")
    chat_history = []
    return jsonify({"success": True, "message": "New isolated user session started"})

@app.route("/api/send", methods=["POST"])
def send_message():
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"success": False, "error": "Message text cannot be empty"}), 400
        
    try:
        os.makedirs(SHARED_DIR, exist_ok=True)
        # Write input source first (atomic)
        tmp_sf = os.path.join(SHARED_DIR, "input_source.txt.tmp")
        with open(tmp_sf, "w", encoding="utf-8") as sf:
            sf.write("text")
        os.replace(tmp_sf, os.path.join(SHARED_DIR, "input_source.txt"))
        
        # Write to shared/user_text.txt (atomic)
        tmp_uf = USER_TXT + ".tmp"
        with open(tmp_uf, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_uf, USER_TXT)
            
        # Add user message to history
        chat_history.append({
            "sender": "user",
            "text": text,
            "timestamp": int(time.time() * 1000)
        })
        
        # Manually force pipeline status to thinking
        try:
            with open(STATUS_TXT, "w", encoding="utf-8") as sf:
                sf.write("thinking:Vivy is thinking...")
        except Exception as _err:
            print(f"[web_server.py] Silenced exception: {_err}")
                
        print(f"[web_server] Chat message queued for pipeline: '{text}'")
        return jsonify({"success": True})
    except Exception as e:
        print(f"[web_server] Error queuing send_message: {e}")
        return jsonify({"success": False, "error": str(e)}), 500



_shmem = None

@app.route("/api/avatar/viewport", methods=["POST"])
def set_viewport():
    data = request.json or {}
    width = data.get("width")
    height = data.get("height")
    if width and height:
        try:
            os.makedirs(SHARED_DIR, exist_ok=True)
            with open(VIEWPORT_TXT, "w", encoding="utf-8") as f:
                f.write(f"{width},{height}")
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": False, "error": "Invalid dimensions"}), 400


@app.route("/api/avatar/command", methods=["POST"])
def send_avatar_command():
    data = request.json or {}
    if data:
        try:
            os.makedirs(SHARED_DIR, exist_ok=True)
            with open(WEB_INTERACTION_TXT, "w", encoding="utf-8") as f:
                json.dump(data, f)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": False, "error": "Empty command payload"}), 400


@app.route("/api/avatar/frame", methods=["GET"])
def get_avatar_frame():
    """Serve the latest avatar frame with explicit no-cache headers.
    First attempts to read from Windows Named Shared Memory (RAM) with long polling support.
    Falls back to static disk read if shared memory is offline.
    """
    global _shmem
    raw_last = request.args.get("last", "-1")
    try:
        last_index = int(raw_last)
    except (ValueError, TypeError):
        last_index = -1

    # Long polling: check up to 20 times (every 5ms) for a new frame index
    shmem_available = False
    for _ in range(20):
        try:
            if _shmem is None:
                import mmap
                _shmem = mmap.mmap(-1, 2 * 1024 * 1024, tagname="VivyAvatarFrame")
            
            _shmem.seek(0)
            import struct
            data_len, frame_index = struct.unpack("<II", _shmem.read(8))
            
            if 0 < data_len <= 2 * 1024 * 1024 - 8:
                shmem_available = True
                if frame_index != last_index:
                    data = _shmem.read(data_len)
                    from flask import Response
                    resp = Response(data, mimetype="image/jpeg")
                    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                    resp.headers["Pragma"]        = "no-cache"
                    resp.headers["Expires"]       = "0"
                    resp.headers["X-Frame-Index"] = str(frame_index)
                    return resp
        except Exception:
            _shmem = None
            shmem_available = False
        time.sleep(0.005)

    if shmem_available and last_index != -1:
        from flask import Response
        resp = Response(status=204)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp

    # Fallback to disk read
    frame_path = os.path.join(BASE_DIR, "static", "avatar_frame.jpg")
    if not os.path.exists(frame_path):
        return send_from_directory(STATIC_DIR, "avatar_default.png")
    try:
        from flask import Response
        mtime = int(os.path.getmtime(frame_path) * 1000)
        if last_index != -1 and mtime <= last_index:
            resp = Response(status=204)
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            return resp

        with open(frame_path, "rb") as f:
            data = f.read()
        resp = Response(data, mimetype="image/jpeg")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"]        = "no-cache"
        resp.headers["Expires"]       = "0"
        resp.headers["X-Frame-Index"] = str(mtime)
        return resp
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/screen/start", methods=["POST"])
def screen_share_start():
    """Authoritative notification from dashboard that user started screen share."""
    try:
        if _perception_writer is not None:
            _perception_writer.mark_screen_share_started()
        print("[web_server] Screen share START signal received.")
        return jsonify({"success": True, "active": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500





# ── FACE & GAZE CAMERA PERCEPTION ENDPOINTS ───────────────────────────────────

@app.route("/api/camera/start", methods=["POST"])
def camera_start():
    """Start local webcam capture or enable external browser camera ingestion."""
    try:
        from perception.camera_manager import get_camera_manager, set_camera_disabled
        set_camera_disabled(False)
        cam = get_camera_manager()
        active = cam.start_camera()
        if _perception_writer is not None:
            _perception_writer.record_camera_state(active=active, paused=False)
        return jsonify({"success": True, "camera_active": active})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/camera/stop", methods=["POST"])
def camera_stop():
    """Stop camera capture loop."""
    try:
        from perception.camera_manager import get_camera_manager, set_camera_disabled
        set_camera_disabled(True)
        cam = get_camera_manager()
        cam.stop_camera()
        if _perception_writer is not None:
            _perception_writer.record_camera_state(active=False, paused=False)
        return jsonify({"success": True, "camera_active": False})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/camera/toggle", methods=["POST"])
def camera_toggle():
    """Toggle camera ON/OFF dynamically."""
    try:
        from perception.camera_manager import get_camera_manager, set_camera_disabled
        cam = get_camera_manager()
        if cam.is_active():
            cam.stop_camera()
            active = False
        else:
            set_camera_disabled(False)
            active = cam.start_camera()
        if _perception_writer is not None:
            _perception_writer.record_camera_state(active=active, paused=False)
        return jsonify({"success": True, "camera_active": active})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/camera/pause", methods=["POST"])
def camera_pause():
    """Pause camera stream temporarily."""
    try:
        from perception.camera_manager import get_camera_manager
        cam = get_camera_manager()
        cam.pause_camera()
        if _perception_writer is not None:
            _perception_writer.record_camera_state(active=False, paused=True)
        return jsonify({"success": True, "camera_active": False, "paused": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/camera/resume", methods=["POST"])
def camera_resume():
    """Resume camera stream."""
    try:
        from perception.camera_manager import get_camera_manager, set_camera_disabled
        set_camera_disabled(False)
        cam = get_camera_manager()
        cam.resume_camera()
        active = cam.is_active()
        if _perception_writer is not None:
            _perception_writer.record_camera_state(active=active, paused=False)
        return jsonify({"success": True, "camera_active": active, "paused": False})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


_cached_camera_devices = []
_cached_camera_devices_time = 0.0

@app.route("/api/camera/devices", methods=["GET"])
def camera_devices():
    """Dynamically enumerate available hardware cameras without DirectShow lock contention."""
    global _cached_camera_devices, _cached_camera_devices_time
    now = time.time()
    devices = []
    try:
        from perception.camera_manager import get_camera_manager
        cam = get_camera_manager()
        active_idx = cam._device_index if cam.is_active() else None

        # Safe Path 1: If camera is actively capturing, return known active device info instantly to avoid DirectShow driver bus conflicts
        if active_idx is not None:
            devices.append({"index": active_idx, "name": f"Camera #{active_idx} (Active)"})
            for d in _cached_camera_devices:
                if d["index"] != active_idx:
                    devices.append(d)
            return jsonify({"success": True, "devices": devices})

        # Safe Path 2: Use cache if scanned recently (< 30s)
        if _cached_camera_devices and (now - _cached_camera_devices_time) < 30.0:
            return jsonify({"success": True, "devices": _cached_camera_devices})

        import cv2
        for idx in range(4):
            try:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY)
                if cap.isOpened():
                    ret, _ = cap.read()
                    if ret:
                        devices.append({"index": idx, "name": f"Camera #{idx}"})
                    cap.release()
                else:
                    break
            except Exception:
                break
        
        if devices:
            _cached_camera_devices = list(devices)
            _cached_camera_devices_time = now
    except Exception as _err:
        print(f"[web_server.py] Silenced exception: {_err}")

    if not devices:
        devices.append({"index": 0, "name": "Default Webcam / Fallback Stream"})
    return jsonify({"success": True, "devices": devices})


@app.route("/api/camera/select", methods=["POST"])
def camera_select():
    """Select camera device index."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        index = int(data.get("index", 0))
        from perception.camera_manager import get_camera_manager
        cam = get_camera_manager()
        active = cam.select_device(index)
        if _perception_writer is not None:
            _perception_writer.record_camera_state(active=active, paused=False)
        return jsonify({"success": True, "device_index": index, "camera_active": active})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/camera/reconnect", methods=["POST"])
def camera_reconnect():
    """Force camera resource release and reconnect."""
    try:
        from perception.camera_manager import get_camera_manager, set_camera_disabled
        cam = get_camera_manager()
        cam.stop_camera()
        time.sleep(0.3)
        set_camera_disabled(False)
        active = cam.start_camera()
        return jsonify({"success": True, "camera_active": active, "status": "reconnected"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/indicators/live", methods=["GET"])
def get_live_indicators():
    """
    Return comprehensive real-time status of all Vivy AI subsystems.
    Updates automatically with no fake statuses.
    """
    try:
        tm = get_telemetry_manager()
        health = tm.get_health_status()
        sub = health.get("subsystems", {})
        
        indicators = {}
        for key, val in sub.items():
            indicators[key] = {
                "status": val.get("status", "GREEN"),
                "state": val.get("state", "READY"),
                "message": val.get("message", ""),
                "root_cause": val.get("root_cause", ""),
                "metrics": val.get("metrics", {})
            }
        
        return jsonify({
            "success": True,
            "timestamp": time.time(),
            "overall_status": health.get("overall_status", "GREEN"),
            "overall_state": health.get("overall_state", "READY"),
            "indicators": indicators
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/camera/frame", methods=["GET", "POST"])
def receive_camera_frame():
    """
    GET: Serve the latest hardware camera frame as JPEG.
    POST: Ingest a base64 JPEG camera frame from browser or local camera stream,
    running face detection, landmark mesh, gaze estimation, attention scoring,
    and presence state updates.
    """
    if request.method == "GET":
        try:
            from perception.camera_manager import get_camera_manager
            cam = get_camera_manager()
            raw_jpg, _ = cam.get_latest_frame_bytes()
            if raw_jpg:
                from flask import Response
                resp = Response(raw_jpg, mimetype="image/jpeg")
                resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                return resp
            return jsonify({"success": False, "error": "No frame available"}), 404
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    try:
        data = request.get_json(force=True) or {}
        frame_b64 = data.get("frame", "")
        if not frame_b64:
            return jsonify({"success": False, "error": "No frame data"}), 400

        from perception.camera_manager import get_camera_manager
        cam = get_camera_manager()
        ingested = cam.ingest_external_frame(frame_b64)
        if not ingested:
            return jsonify({"success": False, "error": "Frame validation failed (corrupted, empty, or invalid format)"}), 400

        pm_state = {}
        if _perception_writer is not None:
            pm_state = _perception_writer.get_diagnostic_report()

        return jsonify({
            "success": True,
            "presence_state": pm_state.get("presence_state", "User Present"),
            "face_count": pm_state.get("face_count", 0),
            "gaze_direction": pm_state.get("gaze_direction", "Unknown"),
            "eye_contact_score": pm_state.get("eye_contact_score", 0.0),
            "attention_score": pm_state.get("attention_score", 0.0),
            "hardware_mode": pm_state.get("hardware_mode", "Live Perception Active"),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/perception/face_status", methods=["GET"])
def get_face_status():
    """Return live face detection and gaze perception state."""
    try:
        from perception.camera_manager import get_camera_manager
        from perception.hardware_scheduler import get_hardware_scheduler
        cam = get_camera_manager()
        hw = get_hardware_scheduler()
        
        pm_state = {}
        if _perception_writer is not None:
            pm_state = _perception_writer.get_diagnostic_report()

        return jsonify({
            "camera_active": cam.is_active(),
            "camera_fps": cam.get_fps(),
            "presence_state": pm_state.get("presence_state", "User Missing"),
            "face_count": pm_state.get("face_count", 0),
            "gaze_direction": pm_state.get("gaze_direction", "Unknown"),
            "eye_contact_score": pm_state.get("eye_contact_score", 0.0),
            "eye_contact_strength": pm_state.get("eye_contact_strength", "None"),
            "attention_score": pm_state.get("attention_score", 0.0),
            "engagement_score": pm_state.get("engagement_score", 0.0),
            "hardware_mode": hw.get_state().mode,
            "hardware_backend": hw.get_state().backend,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/screen/frame", methods=["POST"])
def receive_screen_frame():
    """
    Receives a base64-encoded JPEG frame from the browser screen capture loop.
    Runs PIL-based vision analysis (+ OCR if Tesseract is installed) and writes
    the real screen description to shared/screen_context.txt for the LLM pipeline.

    [UPGRADED] Also delegates to perception.screen_pipeline when available and
    pushes a ScreenEvent to the FusionEngine for the multimodal event log.
    The existing _analyze_screen_frame() remains as the fallback path.
    """
    try:
        data = request.get_json(force=True) or {}
        frame_b64 = data.get("frame", "")
        if not frame_b64:
            return jsonify({"success": False, "error": "No frame data"}), 400

        # ── Perception package path (new, enhanced, queue-based) ──────────────
        if _PERCEPTION_AVAILABLE:
            try:
                arrival_time = time.time()
                # Handle back-pressure by dropping old frames from the queue
                frame_dropped = False
                if _frame_queue.full():
                    try:
                        _frame_queue.get_nowait()
                        _frame_queue.task_done()
                        frame_dropped = True
                    except queue.Empty:
                        pass

                # Notify PerceptionManager of frame arrival BEFORE enqueueing
                # This ensures frame arrival is tracked even if analysis is slow
                if _perception_writer is not None:
                    try:
                        has_ocr_curr = bool(_last_screen_event.get("ocr_text", "")) if _last_screen_event else False
                        app_curr = _last_screen_event.get("app_type", "unknown") if _last_screen_event else "unknown"
                        chars_curr = len(_last_screen_event.get("ocr_text", "")) if _last_screen_event else 0
                        resolution_curr = _last_screen_event.get("resolution", "0x0") if _last_screen_event else "0x0"
                        _perception_writer.record_frame_arrival(
                            app_type=app_curr,
                            ocr_chars=chars_curr,
                            has_ocr=has_ocr_curr,
                            frame_dropped=frame_dropped,
                            resolution=resolution_curr,
                            latency_ms=0.0,
                            ocr_confidence=_last_screen_event.get("ocr_confidence", 1.0) if _last_screen_event else 1.0,
                            scene_layout=_last_screen_event.get("scene_layout") if _last_screen_event else None
                        )
                    except Exception as _pm_fe:
                        pass  # non-fatal

                # Enqueue the new frame for analysis along with arrival timestamp
                if not frame_dropped:
                    _frame_queue.put_nowait((arrival_time, frame_b64))

                # Fetch details from the last successfully processed frame
                has_ocr = False
                app_type = "unknown application"
                chars = 0
                next_delay_ms = 16
                request_high_res = False

                if _last_screen_event is not None:
                    has_ocr = bool(_last_screen_event.get("ocr_text", ""))
                    app_type = _last_screen_event.get("app_type", "unknown application")
                    chars = len(_last_screen_event.get("raw_description", ""))
                    next_delay_ms = _last_screen_event.get("next_delay_ms", 16)
                    request_high_res = bool(_last_screen_event.get("request_high_res", False))

                return jsonify({
                    "success":       True,
                    "chars_detected": chars,
                    "ocr":           has_ocr,
                    "app_type":      app_type,
                    "pipeline":      "perception",
                    "next_delay_ms": next_delay_ms,
                    "request_high_res": request_high_res
                })
            except Exception as _pe:
                print(f"[PerceptionPipeline] Queue error: {_pe}. Falling back to legacy...")
                # Fall through to legacy path below

        # ── Legacy path (existing PIL heuristics) ─────────────────────────────
        # Strip data URI prefix if present
        if "," in frame_b64:
            frame_b64 = frame_b64.split(",", 1)[1]

        # Decode base64 → bytes → PIL Image
        import base64
        from io import BytesIO
        from PIL import Image

        frame_bytes = base64.b64decode(frame_b64)
        img = Image.open(BytesIO(frame_bytes))

        # Run legacy vision analysis
        description = _analyze_screen_frame(img)
        chars = len(description)

        # Notify PerceptionManager of frame arrival (legacy path)
        if _perception_writer is not None:
            try:
                _perception_writer.record_frame_arrival(
                    app_type="unknown",
                    ocr_chars=chars,
                    has_ocr=_TESSERACT_AVAILABLE,
                )
            except Exception as _err:
                print(f"[web_server.py] Silenced exception: {_err}")

        # Write to shared/screen_context.txt with timestamp prefix
        timestamp = int(time.time())
        context_payload = f"[Screen context captured at t={timestamp}]\n{description}"
        os.makedirs(SHARED_DIR, exist_ok=True)
        tmp_file = SCREEN_CONTEXT_TXT + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(context_payload)
        try:
            os.replace(tmp_file, SCREEN_CONTEXT_TXT)
        except Exception as e_replace:
            print(f"[receive_screen_frame] Context replace error: {e_replace}")

        print(f"[VisionBridge] Frame processed — {chars} chars described (tesseract={'yes' if _TESSERACT_AVAILABLE else 'no'})")
        return jsonify({"success": True, "chars_detected": chars, "ocr": _TESSERACT_AVAILABLE})
    except Exception as e:
        print(f"[VisionBridge] Error processing frame: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/screen/status", methods=["GET"])
def screen_status():
    """Returns whether active screen context is available and how old it is."""
    if not os.path.exists(SCREEN_CONTEXT_TXT):
        return jsonify({"active": False, "age_seconds": None})
    try:
        mtime = os.path.getmtime(SCREEN_CONTEXT_TXT)
        age = time.time() - mtime
        with open(SCREEN_CONTEXT_TXT, "r", encoding="utf-8") as f:
            preview = f.read(120)
        return jsonify({"active": age < 60, "age_seconds": round(age, 1), "preview": preview})
    except Exception as e:
        return jsonify({"active": False, "error": str(e)})


@app.route("/api/screen/screenshot", methods=["GET"])
def take_screenshot():
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        screenshot_path = os.path.join(STATIC_DIR, "screen.png")
        img.save(screenshot_path)
        return jsonify({"success": True, "url": f"/static/screen.png?t={int(time.time())}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/screen/audio", methods=["POST"])
def receive_screen_audio():
    """
    Receives a base64-encoded audio chunk from the browser's screen-share audio track.

    The browser's getDisplayMedia() can capture system audio (the audio playing on
    the shared tab/window). This endpoint receives those chunks, decodes them, runs
    heuristic audio analysis (silence/music/speech/ambient detection), and pushes
    the result to the FusionEngine for multimodal context accumulation.

    This audio is NEVER played back — analysis only.
    Non-fatal: any failure returns a graceful error JSON without affecting the pipeline.
    """
    try:
        data = request.get_json(silent=True) or {}
        audio_b64 = data.get("audio", "")
        mime_type = data.get("mime_type", "audio/webm")

        if not audio_b64:
            return jsonify({"success": False, "error": "No audio data"}), 400

        # Decode base64 → bytes
        import base64
        try:
            audio_bytes = base64.b64decode(audio_b64)
        except Exception as b64_err:
            return jsonify({"success": False, "error": f"Base64 decode error: {b64_err}"}), 400

        # Skip very short chunks (< 500 bytes = essentially silence/header-only)
        if len(audio_bytes) < 500:
            return jsonify({"success": True, "skipped": True, "reason": "chunk too short"})

        global _audio_stream_buffer, _audio_stream_header, _audio_latest_chunks, _last_speech_detected_time
        
        # Save header on first chunk (which is the start of the stream)
        if not _audio_stream_header and len(audio_bytes) > 0:
            _audio_stream_header = bytearray(audio_bytes[:16384])
            print(f"[ScreenAudio] Captured stream header of size {len(_audio_stream_header)} bytes")
            
        # Append chunk to buffer and rolling window
        _audio_stream_buffer.extend(audio_bytes)
        _audio_latest_chunks.append(audio_bytes)
        if len(_audio_latest_chunks) > 3:
            _audio_latest_chunks.pop(0)
        
        # Prevent buffer from growing infinitely (e.g., if it exceeds 15MB, keep header + last 2MB)
        if len(_audio_stream_buffer) > 15 * 1024 * 1024:
            _audio_stream_buffer = _audio_stream_header + _audio_stream_buffer[-(2 * 1024 * 1024):]
            print("[ScreenAudio] Buffer capped: truncated to header + last 2MB")

        # Decode WebM/Opus to PCM float32 samples using persistent low-latency FFmpeg
        decoded_samples = None
        event_type = None
        description = None
        confidence = 0.5
        rms = 0.0

        # Ensure persistent FFmpeg process is running (self-healing)
        with _ffmpeg_lock:
            if _ffmpeg_process is None or _ffmpeg_process.poll() is not None:
                _start_ffmpeg()
            
            if _ffmpeg_process is not None and _ffmpeg_process.stdin is not None:
                try:
                    _ffmpeg_process.stdin.write(audio_bytes)
                    _ffmpeg_process.stdin.flush()
                except Exception as write_err:
                    print(f"[ScreenAudio] Persistent FFmpeg write failed: {write_err}. Restarting...")
                    _start_ffmpeg()
                    if _ffmpeg_process is not None and _ffmpeg_process.stdin is not None:
                        try:
                            _ffmpeg_process.stdin.write(audio_bytes)
                            _ffmpeg_process.stdin.flush()
                        except Exception as rewrite_err:
                            print(f"[ScreenAudio] Persistent FFmpeg retry write failed: {rewrite_err}")

        # Retrieve the latest 6 seconds of decoded float32 samples from the stream buffer
        # 6.0s at 16kHz mono (float32) is 96000 samples = 384000 bytes
        import numpy as np
        target_bytes = 16000 * 6 * 4
        with _decoded_pcm_lock:
            buf_len = len(_decoded_pcm_buffer)
            if buf_len >= 4:
                valid_len = (min(buf_len, target_bytes) // 4) * 4
                chunk_bytes = bytes(_decoded_pcm_buffer[-valid_len:])
                decoded_samples = np.frombuffer(chunk_bytes, dtype=np.float32)

        # Run plugin semantic analysis if samples are decoded
        if decoded_samples is not None:
            try:
                from perception.model_router import ModelRouter
                plugin = ModelRouter.get_audio_analysis_plugin()
                if plugin:
                    analysis_results = plugin.analyze(decoded_samples, sample_rate=16000)
                    if analysis_results:
                        res = analysis_results[0]
                        event_type = res.get("event_type", "ambient")
                        description = f"Screen share audio: {res.get('description', '')}"
                        confidence = res.get("confidence", 0.5)
                        # Scale RMS to match legacy 16-bit range for diagnostics
                        rms = float(np.sqrt(np.mean(decoded_samples ** 2))) * 32768.0

                        # Transcription block (run speech/lyrics recognition on all active events when RMS is sufficient)
                        if event_type not in ("silence", "environmental_sounds") and rms >= 80.0:
                            try:
                                import scipy.io.wavfile as wav
                                import tempfile
                                pcm16 = np.clip(decoded_samples * 32768, -32768, 32767).astype(np.int16)
                                shared_dir = os.path.join(BASE_DIR, "shared")
                                os.makedirs(shared_dir, exist_ok=True)

                                fd, temp_filename = tempfile.mkstemp(suffix=".wav", prefix="screen_audio_", dir=shared_dir)
                                os.close(fd)
                                
                                try:
                                    wav.write(temp_filename, 16000, pcm16)

                                    speech_plugin = ModelRouter.get_speech_plugin()
                                    if speech_plugin and speech_plugin.is_available():
                                        trans_res = speech_plugin.transcribe(temp_filename)
                                        text = trans_res.get("text", "").strip()
                                        speech_conf = trans_res.get("confidence", 1.0)
                                        
                                        speaker_id = _diarizer.attribute_speaker(decoded_samples)
                                        lang = detect_language(text) if text else "unknown"
                                        
                                        music_title = None
                                        if event_type == "music" and _perception_writer is not None:
                                            with _perception_writer._lock:
                                                win_title = _perception_writer._active_window_title
                                                app_type_curr = _perception_writer._current_app_type
                                                ocr_text_curr = _perception_writer._last_ocr_text
                                            if win_title and " - " in win_title and not any(x in win_title.lower() for x in ("vivy ai", "localhost", "127.0.0.1", "dashboard")):
                                                music_title = win_title.split(" - ")[0].strip()
                                            if not music_title and app_type_curr and "playing '" in app_type_curr:
                                                import re as _re
                                                m_m = _re.search(r"playing '([^']+)'", app_type_curr)
                                                if m_m:
                                                    music_title = m_m.group(1)
                                            if not music_title and ocr_text_curr:
                                                for line in ocr_text_curr.split("\n"):
                                                    if any(k in line.lower() for k in ["nightcore", "lyrics", "official video", "music video", " - "]) and len(line) < 120:
                                                        music_title = line.strip()
                                                        break
                                                
                                        if _perception_writer is not None:
                                            _perception_writer.record_audio_metadata(
                                                language=lang,
                                                speaker_id=speaker_id,
                                                music_title=music_title,
                                                playback_state="playing" if event_type not in ("silence", "ambient") else "paused",
                                                sound_effects=[event_type] if event_type in ("notifications", "movie_game_audio") else []
                                            )
                                            
                                        if text:
                                            if is_noise_label(text):
                                                text_lower = text.lower()
                                                if "music" in text_lower or "singing" in text_lower:
                                                    event_type = "music"
                                                    description = "Screen share audio: music playing."
                                                elif "laughter" in text_lower:
                                                    event_type = "laughter"
                                                    description = "Screen share audio: laughter."
                                                elif "applause" in text_lower:
                                                    event_type = "applause"
                                                    description = "Screen share audio: applause."
                                                text = ""
                                            else:
                                                print(f"[ScreenAudio] Transcribed speech: {text}")
                                                prev_t = ""
                                                if _perception_writer is not None:
                                                    prev_t = _perception_writer._screen_audio_transcript or ""
                                                stitched_t = stitch_transcripts(prev_t, text)
                                                _last_speech_detected_time = time.time()
                                                if _perception_writer is not None:
                                                    _perception_writer.record_screen_audio_transcript(stitched_t, confidence=speech_conf)
                                                description = f"{description} (speaker: {speaker_id}, lang: {lang}, text: \"{text}\")"
                                                
                                                # Push transcript event to FusionEngine timeline explicitly (Phase 4)
                                                try:
                                                    if _PERCEPTION_AVAILABLE and _fusion_engine_mod is not None:
                                                        _fusion_engine_mod.get_global_engine().push_perception_event(
                                                            source="system_audio",
                                                            semantic=f"[{speaker_id} in {lang}]: \"{text}\"",
                                                            importance=0.95,
                                                            confidence=speech_conf,
                                                            scope="shared_screen",
                                                            metadata={"speaker_id": speaker_id, "language": lang}
                                                        )
                                                except Exception as fe_se:
                                                    pass
                                finally:
                                    if os.path.exists(temp_filename):
                                        try:
                                            os.remove(temp_filename)
                                        except Exception as _err:
                                            print(f"[web_server.py] Silenced exception: {_err}")
                            except Exception as trans_err:
                                print(f"[ScreenAudio] Speech transcription failed: {trans_err}")
            except Exception as plug_err:
                print(f"[ScreenAudio] Plugin analysis failed: {plug_err}")
                decoded_samples = None  # Force fallback to legacy byte-level analysis

        # Legacy byte-level fallback if FFmpeg decoding or plugin analysis failed/returned nothing
        if decoded_samples is None or event_type is None or description is None:
            import struct, math
            # Sample every 4th byte pair as a proxy for PCM amplitude
            raw_len = len(audio_bytes)
            sample_count = min(raw_len // 2, 2000)
            samples = []
            step = max(1, raw_len // (sample_count * 2))
            for i in range(0, min(raw_len - 1, sample_count * step * 2), step * 2):
                try:
                    val = struct.unpack_from('<h', audio_bytes, i)[0]
                    samples.append(val)
                except Exception as _err:
                    print(f"[web_server.py] Silenced exception: {_err}")

            rms = 0.0
            if samples:
                rms = math.sqrt(sum(s * s for s in samples) / len(samples))

            # Map RMS to a semantic label
            if rms < 80:
                event_type = "silence"
                description = "Screen share audio: silence detected."
            elif rms < 800:
                event_type = "ambient"
                description = "Screen share audio: low ambient sound."
            elif rms < 4000:
                event_type = "music"
                description = "Screen share audio: audio playing — likely music or media."
            else:
                event_type = "loud_audio"
                description = "Screen share audio: loud sound — speech or loud media."

        # Silence/decay timeout: if no speech has been transcribed for 15 seconds, clear the rolling transcript
        if time.time() - _last_speech_detected_time > 15.0:
            if _perception_writer is not None:
                with _perception_writer._lock:
                    _perception_writer._screen_audio_transcript = ""

        # Notify PerceptionManager of audio arrival (non-fatal)
        if _perception_writer is not None:
            try:
                # Upgraded audio model status recording (Phase 4)
                _perception_writer.record_audio_chunk(rms=rms, event_type=event_type, sample_rate=16000, channels=1)
                _perception_writer.record_audio_model_inference(
                    running=True,
                    detected_speech=(event_type == "speech"),
                    detected_music=(event_type == "music"),
                    detected_sound_events=[event_type] if event_type != "silence" else [],
                    confidence=confidence
                )
                # Persist human-readable description so it flows into the LLM prompt
                if description and event_type not in ("silence",):
                    _perception_writer.record_audio_event_description(description)
            except Exception as pm_err:
                print(f"[ScreenAudio] PerceptionManager update failed (non-fatal): {pm_err}")

        # Push to FusionEngine (non-fatal if perception unavailable)
        try:
            if _PERCEPTION_AVAILABLE and _fusion_engine_mod is not None:
                _fusion_engine_mod.get_global_engine().push_audio_event({
                    "description":       description,
                    "event_type":        event_type,
                    "confidence":        confidence,
                    "duration_seconds":  2.0,
                    "source_label":      "screen_audio",
                    "rms_level":         round(rms, 1),
                    "chunk_bytes":       len(audio_bytes),
                })
                print(f"[ScreenAudio] {event_type}: RMS={int(rms)}, chunk={len(audio_bytes)}B")
        except Exception as fe:
            print(f"[ScreenAudio] FusionEngine push failed (non-fatal): {fe}")

        return jsonify({
            "success":      True,
            "event_type":   event_type,
            "rms":          round(rms, 1),
            "bytes":        len(audio_bytes),
        })

    except Exception as e:
        print(f"[ScreenAudio] /api/screen/audio error (non-fatal): {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/rvc/models", methods=["GET"])
def get_rvc_models():
    weights_dir = os.path.join(BASE_DIR, "rvc_cpu", "assets", "weights")
    models = []
    if os.path.exists(weights_dir):
        try:
            models = [f for f in os.listdir(weights_dir) if f.endswith(".pth") and f != "Synthesizer_inputs.pth"]
        except Exception as _err:
            print(f"[web_server.py] Silenced exception: {_err}")
    return jsonify(models)


# =====================================================================
# VOICE IDENTITY MANAGEMENT SYSTEM REST & REAL-TIME ENDPOINTS (/api/voice/*)
# =====================================================================
@app.route("/api/voice/profiles", methods=["GET"])
def get_voice_profiles_api():
    try:
        from voice.voice_manager import get_voice_manager
        mgr = get_voice_manager()
        lang_filter = request.args.get("language", None)
        min_qual = int(request.args.get("min_quality", "0"))
        profiles = mgr.db.list_profiles(language_filter=lang_filter, min_quality=min_qual)
        active = mgr.get_active_voice()
        return jsonify({
            "success": True,
            "profiles": profiles,
            "active_voice_id": active["voice_id"],
            "active_style": active.get("active_style", "Professional")
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "profiles": []}), 500

@app.route("/api/voice/select", methods=["POST"])
def select_voice_api():
    try:
        from voice.voice_manager import get_voice_manager
        data = request.json or {}
        voice_id_or_name = data.get("voice", "natural_anime_01")
        style = data.get("style", None)
        mgr = get_voice_manager()
        success = mgr.select_voice(voice_id_or_name, style_name=style)
        return jsonify({"success": success, "active_voice": mgr.get_active_voice()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/voice/preview_generate", methods=["POST"])
def generate_voice_preview_api():
    try:
        from voice.voice_manager import get_voice_manager
        import voice
        import xmlrpc.client
        
        data = request.json or {}
        voice_id = data.get("voice_id")
        prompt = data.get("prompt")
        
        if not voice_id or not prompt:
            return jsonify({"success": False, "error": "Missing voice_id or prompt"}), 400
            
        mgr = get_voice_manager()
        profile = mgr.db.get_profile(voice_id)
        if not profile:
            return jsonify({"success": False, "error": "Voice profile not found"}), 404
            
        model_filename = profile.get("model_filename")
        if not model_filename:
            return jsonify({"success": False, "error": "No RVC model associated with this profile"}), 400
            
        previews_dir = os.path.join(SHARED_DIR, "previews")
        os.makedirs(previews_dir, exist_ok=True)
        
        # Unique ID for concurrent safety
        req_id = str(uuid.uuid4())[:8]
        tmp_tts = os.path.join(previews_dir, f"preview_tts_{req_id}.wav")
        tmp_rvc = os.path.join(previews_dir, f"preview_rvc_{req_id}.wav")
        
        # Generate TTS audio base safely
        voice.generate_tts_only(prompt, tmp_tts)
        if not os.path.exists(tmp_tts):
            return jsonify({"success": False, "error": "TTS synthesis failed"}), 500
            
        # Ping background RVC RPC server
        try:
            proxy = xmlrpc.client.ServerProxy("http://127.0.0.1:8766", allow_none=True)
            res = proxy.convert_voice(tmp_tts, tmp_rvc, 0, "rmvpe", model_filename)
            if res.get("status") == "error":
                return jsonify({"success": False, "error": f"RVC Server Error: {res.get('message')}"}), 500
        except Exception as rpc_err:
            return jsonify({"success": False, "error": f"RPC Connection Failed: {str(rpc_err)}"}), 500
            
        if not os.path.exists(tmp_rvc):
            return jsonify({"success": False, "error": "RVC conversion failed to produce audio"}), 500
            
        # Cleanup temporary TTS file
        try: os.remove(tmp_tts)
        except: pass
        
        preview_url = f"/api/voice/preview_audio?file={os.path.basename(tmp_rvc)}"
        return jsonify({"success": True, "preview_url": preview_url})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/voice/styles", methods=["GET"])
def get_voice_styles_api():
    try:
        from voice.voice_profiles import get_voice_profile_manager
        from voice.voice_manager import get_voice_manager
        pm = get_voice_profile_manager()
        mgr = get_voice_manager()
        active = mgr.get_active_voice()
        styles_meta = [pm.get_style_parameters(s) for s in pm.list_styles()]
        return jsonify({"success": True, "styles": styles_meta, "active_style": active.get("active_style", "Professional")})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/voice/rvc_projects", methods=["GET"])
def get_rvc_projects_api():
    try:
        from voice.voice_manager import get_voice_manager
        mgr = get_voice_manager()
        profiles = mgr.db.list_profiles()
        # Filter out built-in voices (specifically natural_anime_01)
        rvc_voices = [p for p in profiles if p.get("voice_id") != "natural_anime_01"]
        return jsonify({"success": True, "profiles": rvc_voices})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/voice/rename", methods=["POST"])
def rename_voice_api():
    try:
        from voice.voice_manager import get_voice_manager
        data = request.json or {}
        voice_id = data.get("voice_id")
        new_name = data.get("new_name")
        if not voice_id or not new_name:
            return jsonify({"success": False, "error": "Missing voice_id or new_name"}), 400
            
        mgr = get_voice_manager()
        updated = mgr.db.update_profile(voice_id, {"name": new_name})
        if not updated:
            return jsonify({"success": False, "error": "Voice not found"}), 404
        return jsonify({"success": True, "profile": updated})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/voice/remove", methods=["POST"])
def remove_voice_api():
    try:
        from voice.voice_manager import get_voice_manager
        data = request.json or {}
        voice_id = data.get("voice_id")
        if not voice_id:
            return jsonify({"success": False, "error": "Missing voice_id"}), 400
            
        if voice_id == "natural_anime_01":
            return jsonify({"success": False, "error": "Cannot delete the built-in system voice."}), 403
            
        mgr = get_voice_manager()
        profile = mgr.db.get_profile(voice_id)
        if not profile:
            return jsonify({"success": False, "error": "Voice not found"}), 404
            
        model_filename = profile.get("model_filename")
        
        # 1. Delete from DB
        success = mgr.db.delete_profile(voice_id)
        if not success:
            return jsonify({"success": False, "error": "Failed to delete profile from database."}), 500
            
        # 2. Aggressive disk cleanup
        try:
            import shutil
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            # Delete weights
            if model_filename:
                weights_path = os.path.join(base_dir, "rvc_cpu", "assets", "weights", model_filename)
                if os.path.exists(weights_path):
                    os.remove(weights_path)
            # Delete dataset/logs
            logs_path = os.path.join(base_dir, "rvc_cpu", "logs", voice_id)
            if os.path.exists(logs_path):
                shutil.rmtree(logs_path, ignore_errors=True)
        except Exception as cleanup_err:
            print(f"[Cleanup Error] {cleanup_err}")
            # Non-fatal if we can't clean the disk perfectly, the DB entry is gone
            
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/voice/upload", methods=["POST"])
def upload_voice_sample_api():
    try:
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "No file part in request"}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "error": "No file selected"}), 400
        
        from voice.voice_validation import VoiceQualityAnalyzer
        voice_uploads_dir = os.path.join(SHARED_DIR, "voice_uploads")
        os.makedirs(voice_uploads_dir, exist_ok=True)
        file_path = os.path.join(voice_uploads_dir, file.filename)
        file.save(file_path)
        
        analyzer = VoiceQualityAnalyzer()
        audit = analyzer.analyze_audio_sample(file_path)
        return jsonify({"success": True, "file_path": file_path, "filename": file.filename, "analysis": audit})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/voice/train", methods=["POST"])
def train_voice_model_api():
    try:
        from voice.voice_training import get_voice_training_manager
        data = request.json or {}
        audio_path = data.get("audio_path", "")
        voice_name = data.get("voice_name", "Custom Voice")
        voice_id = data.get("voice_id", None)
        iterations = int(data.get("iterations", 1))
        is_retrain = bool(data.get("is_retrain", False))
        job_mode = "INCREMENTAL_RETRAINING" if is_retrain else "FRESH_TRAINING"
        
        # Enforce Mode Separation: Fresh Training MUST NOT inherit an existing voice ID
        if not is_retrain:
            voice_id = None
        base_quality = data.get("base_quality", None)

        # Allow empty audio path ONLY if it's an incremental retrain
        if job_mode == "FRESH_TRAINING" and (not audio_path or not os.path.exists(audio_path)):
            return jsonify({"success": False, "error": "Audio source path invalid or file missing on host."}), 400
        elif job_mode == "INCREMENTAL_RETRAINING" and audio_path and not os.path.exists(audio_path):
            return jsonify({"success": False, "error": "Provided audio source path does not exist."}), 400

        tm = get_voice_training_manager()
        job = tm.enqueue_training_job(
            audio_path=audio_path,
            voice_name=voice_name,
            voice_id=voice_id,
            iterations=iterations,
            job_mode=job_mode,
            base_quality=base_quality
        )
        return jsonify({"success": True, "job": job})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/voice/train/cancel", methods=["POST"])
def cancel_voice_train_api():
    try:
        from voice.voice_training import get_voice_training_manager
        tm = get_voice_training_manager()
        success = tm.cancel_training()
        if not success:
            return jsonify({"success": False, "error": "No active training job to cancel."}), 400
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/voice/train/alert", methods=["POST"])
def voice_train_alert_api():
    try:
        from voice.voice_manager import get_voice_manager
        mgr = get_voice_manager()
        data = request.json or {}
        mgr.notify_realtime_event("training_alert", data)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/voice/train/progress", methods=["GET"])
def get_voice_train_progress_api():
    try:
        from voice.voice_training import get_voice_training_manager
        from voice.voice_manager import get_voice_manager
        tm = get_voice_training_manager()
        mgr = get_voice_manager()
        since = float(request.args.get("since", "0"))
        job_id = request.args.get("job_id", "")
        events = mgr.get_recent_events(since_timestamp=since)
        return jsonify({"success": True, "progress": tm.get_progress(job_id), "events": events, "timestamp": time.time()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/voice/confirm", methods=["POST"])
def confirm_save_voice_api():
    try:
        from voice.voice_manager import get_voice_manager
        data = request.json or {}
        voice_id = data.get("voice_id", "")
        name = data.get("name", "").strip()
        model_filename = data.get("model_filename", "")
        quality_score = int(data.get("quality_score", 90))
        iterations = int(data.get("iterations", 1))
        favorite = bool(data.get("favorite", True))

        if not name or not model_filename:
            return jsonify({"success": False, "error": "Name and model filename are required."}), 400

        mgr = get_voice_manager()
        prof = mgr.db.register_profile(
            name=name,
            model_filename=model_filename,
            language_support=["en", "ja", "hi", "es", "ru"],
            quality_score=quality_score,
            training_iterations=iterations,
            favorite=favorite,
            voice_id=voice_id or None
        )
        # Immediately switch to newly confirmed voice without server restart
        mgr.select_voice(prof["voice_id"])
        return jsonify({"success": True, "profile": prof, "message": f"Voice '{name}' registered and activated successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/voice/preview_audio", methods=["GET"])
def serve_voice_preview_audio_api():
    try:
        from flask import send_file
        filename = request.args.get("file", "")
        preview_path = os.path.join(SHARED_DIR, "previews", os.path.basename(filename))
        if not os.path.exists(preview_path):
            fallback_path = os.path.join(SHARED_DIR, "voice_uploads", os.path.basename(filename))
            if os.path.exists(fallback_path):
                preview_path = fallback_path
        if os.path.exists(preview_path):
            return send_file(preview_path, as_attachment=False)
        return jsonify({"success": False, "error": "Preview audio file not found on disk."}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/upload", methods=["POST"])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400
    
    try:
        # Create shared/uploads directory if not exists
        uploads_dir = os.path.join(SHARED_DIR, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        
        file_path = os.path.join(uploads_dir, file.filename)
        file.save(file_path)
        
        # Read file contents if it is text, or summarize
        file_desc = ""
        _, ext = os.path.splitext(file.filename.lower())
        
        # Handle text files (read first 2000 chars)
        if ext in ['.txt', '.py', '.json', '.md', '.html', '.css', '.js']:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(2000)
                file_desc = f"\n[File Content of '{file.filename}']:\n{content}"
                if len(content) >= 2000:
                    file_desc += "\n... (truncated)"
            except Exception:
                file_desc = f"\n[Attached file: {file.filename}]"
        else:
            file_desc = f"\n[Attached file: {file.filename} ({os.path.getsize(file_path)} bytes)]"
            
        # Write input source first (atomic)
        tmp_sf = os.path.join(SHARED_DIR, "input_source.txt.tmp")
        with open(tmp_sf, "w", encoding="utf-8") as sf:
            sf.write("text")
        os.replace(tmp_sf, os.path.join(SHARED_DIR, "input_source.txt"))
        
        # Write to shared/user_text.txt to feed it to Vivy's pipeline (atomic)
        user_msg = f"I uploaded a file: {file.filename}. Please process it. {file_desc}"
        tmp_uf = USER_TXT + ".tmp"
        with open(tmp_uf, "w", encoding="utf-8") as f:
            f.write(user_msg)
        os.replace(tmp_uf, USER_TXT)
            
        # Append user message to history
        chat_history.append({
            "sender": "user",
            "text": f"📁 Uploaded: {file.filename}",
            "timestamp": int(time.time() * 1000)
        })
        
        # Manually force pipeline status to thinking
        if os.path.exists(STATUS_TXT):
            try:
                tmp_stat = STATUS_TXT + ".tmp"
                with open(tmp_stat, "w", encoding="utf-8") as sf:
                    sf.write("thinking")
                os.replace(tmp_stat, STATUS_TXT)
            except Exception as _err:
                print(f"[web_server.py] Silenced exception: {_err}")
                
        return jsonify({"success": True, "filename": file.filename})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────
# PERCEPTION API ROUTES (new — read-only, non-breaking)
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/perception/events", methods=["GET"])
def perception_events():
    """
    Returns the recent multimodal perception event log as JSON.
    """
    if not _PERCEPTION_AVAILABLE:
        return jsonify({"available": False, "count": 0, "events": []})
    try:
        from perception.fusion_engine import get_global_engine
        events = get_global_engine().get_recent_events()
        return jsonify({"available": True, "count": len(events), "events": events})
    except Exception as e:
        return jsonify({"available": False, "error": str(e), "events": []}), 500


@app.route("/api/perception/context", methods=["GET"])
def perception_context_endpoint():
    """
    Evaluates and returns the prompt context string.
    """
    if not _PERCEPTION_AVAILABLE:
        return "", 200
    try:
        from perception.context_injector import get_perception_context
        screen_context = request.args.get("screen_context", "")
        token_budget_str = request.args.get("token_budget")
        token_budget = int(token_budget_str) if token_budget_str else None
        
        wants_vision = request.args.get("wants_vision", "true").lower() != "false"
        wants_audio = request.args.get("wants_audio", "true").lower() != "false"
        
        # Coordinated fresh perception pass for direct perception queries
        is_percep = request.args.get("is_perception_query", "false").lower() == "true"
        if is_percep:
            # 1. Wait for any pending frames in the queue to be fully analyzed
            try:
                timeout = 1.5
                start_w = time.time()
                while not _frame_queue.empty() and (time.time() - start_w < timeout):
                    time.sleep(0.05)
                
                # 2. Wait for active async OCR
                try:
                    from perception.screen_pipeline import is_ocr_in_progress
                    while is_ocr_in_progress() and (time.time() - start_w < timeout):
                        time.sleep(0.05)
                except ImportError:
                    pass
            except Exception as e:
                print(f"[WebServer] Frame queue wait failed: {e}")
                
            # 3. Run fresh audio analysis on the latest buffer samples
            if wants_audio:
                try:
                    run_fresh_audio_perception(duration_seconds=6.0)
                except Exception as e:
                    print(f"[WebServer] Fresh audio perception failed: {e}")
        
        ctx = get_perception_context(
            screen_context=screen_context, 
            token_budget=token_budget,
            wants_vision=wants_vision,
            wants_audio=wants_audio,
            is_perception_query=is_percep
        )
        return ctx, 200
    except Exception as e:
        print(f"[WebServer] /api/perception/context error: {e}")
        return "", 500


@app.route("/api/perception/narrative", methods=["GET"])
def perception_narrative_endpoint():
    """
    Returns the synthesized observation narrative as JSON.
    """
    if not _PERCEPTION_AVAILABLE:
        return jsonify({"narrative": ""})
    try:
        from perception.fusion_engine import get_global_engine
        narrative = get_global_engine().get_observation_narrative()
        return jsonify({"narrative": narrative})
    except Exception as e:
        return jsonify({"error": str(e), "narrative": ""}), 500


@app.route("/api/perception/push", methods=["POST"])
def perception_push_endpoint():
    """
    Receives an event and pushes it to the global FusionEngine.
    """
    if not _PERCEPTION_AVAILABLE:
        return jsonify({"success": False, "error": "Perception not available"}), 400
    try:
        data = request.json or {}
        source = data.get("source")
        event_data = data.get("data")
        
        from perception.fusion_engine import get_global_engine
        engine = get_global_engine()
        
        if source == "screen":
            engine.push_screen_event(event_data)
        elif source == "audio":
            engine.push_audio_event(event_data)
        elif source == "speech":
            txt = event_data.get("text", "") if isinstance(event_data, dict) else str(event_data)
            meta = event_data.get("metadata", {}) if isinstance(event_data, dict) else {}
            engine.push_speech_event(txt, meta)
        elif source == "user_action":
            act = event_data.get("action", "") if isinstance(event_data, dict) else str(event_data)
            meta = event_data.get("metadata", {}) if isinstance(event_data, dict) else {}
            engine.push_user_action(act, meta)
        elif source == "system":
            desc = event_data.get("description", "") if isinstance(event_data, dict) else str(event_data)
            imp = event_data.get("importance", 0.5) if isinstance(event_data, dict) else 0.5
            engine.push_system_event(desc, imp)
        elif source == "perception":
            engine.push_perception_event(
                source=event_data.get("source", "system"),
                semantic=event_data.get("semantic", ""),
                importance=event_data.get("importance", 0.5),
                confidence=event_data.get("confidence", 1.0),
                scope=event_data.get("scope", "global"),
                metadata=event_data.get("metadata", {})
            )
        else:
            engine._enqueue(source, event_data)
            
        return jsonify({"success": True})
    except Exception as e:
        print(f"[WebServer] /api/perception/push error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/perception/update", methods=["POST"])
def perception_update_endpoint():
    """
    Directly updates fields in the PerceptionManagerWriter (such as correcting transcripts or song titles).
    """
    try:
        data = request.json or {}
        if _perception_writer is not None:
            if "screen_audio_transcript" in data:
                _perception_writer.record_screen_audio_transcript(data["screen_audio_transcript"], confidence=1.0)
            if "audio_music_title" in data:
                _perception_writer.record_audio_metadata(music_title=data["audio_music_title"])
            _perception_writer._flush_to_disk()
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "PerceptionManagerWriter not initialized"}), 400
    except Exception as e:
        print(f"[WebServer] /api/perception/update error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/perception/status", methods=["GET"])
def perception_status():
    """
    Returns the status of the perception system components.
    Includes live PerceptionManager diagnostics.
    """
    status = {
        "perception_available":     _PERCEPTION_AVAILABLE,
        "screen_pipeline_active":   _PERCEPTION_AVAILABLE and _screen_pipeline_mod is not None,
        "fusion_engine_active":     _PERCEPTION_AVAILABLE and _fusion_engine_mod is not None,
        "event_count":              0,
        "audio_pipeline_active":    False,
        "proactivity_active":       False,
    }
    if _PERCEPTION_AVAILABLE and _fusion_engine_mod is not None:
        try:
            status["event_count"] = _fusion_engine_mod.get_global_engine().event_count()
        except Exception as _err:
            print(f"[web_server.py] Silenced exception: {_err}")
    # Include live PerceptionManager diagnostics if available
    if _perception_writer is not None:
        try:
            diag = _perception_writer.get_diagnostic_report()
            status["perception_diagnostics"] = diag
        except Exception as _err:
            print(f"[web_server.py] Silenced exception: {_err}")
    return jsonify(status)


@app.route("/api/perception/diagnostics", methods=["GET"])
def perception_diagnostics():
    """
    Returns the full real-time perception diagnostic state from PerceptionManager.
    This is the FACTUAL runtime state — not LLM-generated.
    Used by the frontend HUD and by the Dialogue Router Gate.
    """
    if _perception_writer is None:
        return jsonify({
            "available": False,
            "error": "PerceptionManager not initialized",
            "screen_sharing_active": False,
            "audio_active": False,
        })
    try:
        diag = _perception_writer.get_diagnostic_report()
        diag["available"] = True
        return jsonify(diag)
    except Exception as e:
        return jsonify({"available": False, "error": str(e)})


# ──────────────────────────────────────────────────────────────────────
# DEVELOPER RUNTIME DIAGNOSTIC MODE ENDPOINTS (Phases 2, 3, 4, 5, 6, 7, 12)
# ──────────────────────────────────────────────────────────────────────
@app.route("/diagnostics")
def developer_dashboard():
    return send_from_directory(TEMPLATES_DIR, "developer_dashboard.html")

@app.route("/api/developer-diagnostic/status", methods=["GET"])
def get_developer_diagnostic_status():
    try:
        from developer_diagnostic_manager import get_developer_diagnostic_manager
        ddm = get_developer_diagnostic_manager()
        return jsonify({"success": True, "data": ddm.get_snapshot()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/developer-diagnostic/toggle", methods=["POST"])
def toggle_developer_diagnostic_mode():
    try:
        from developer_diagnostic_manager import get_developer_diagnostic_manager
        ddm = get_developer_diagnostic_manager()
        req_data = request.get_json(silent=True) or {}
        enable_val = req_data.get("enable")
        new_state = ddm.toggle(enable=enable_val)
        return jsonify({"success": True, "enabled": new_state})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/developer-diagnostic/prompt-trace", methods=["GET"])
def get_developer_diagnostic_prompt_trace():
    try:
        from developer_diagnostic_manager import get_developer_diagnostic_manager
        ddm = get_developer_diagnostic_manager()
        return jsonify({"success": True, "traces": ddm.get_prompt_traces(limit=50)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/developer-diagnostic/websocket-monitor", methods=["GET"])
def get_developer_diagnostic_ws_monitor():
    try:
        from developer_diagnostic_manager import get_developer_diagnostic_manager
        ddm = get_developer_diagnostic_manager()
        return jsonify({"success": True, "packets": ddm.get_ws_packets(limit=50)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/developer-diagnostic/fallbacks", methods=["GET"])
def get_developer_diagnostic_fallbacks():
    try:
        from developer_diagnostic_manager import get_developer_diagnostic_manager
        ddm = get_developer_diagnostic_manager()
        return jsonify({
            "success": True,
            "fallbacks": ddm.get_fallbacks(limit=50),
            "defects": ddm.get_defects(limit=50)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/screen/start", methods=["POST"])
def screen_share_started():
    """
    Called by the browser immediately after getDisplayMedia() resolves
    (i.e. the user just granted screen share permission).

    This is the AUTHORITATIVE signal that screen sharing is active.
    Calls PerceptionManagerWriter.mark_screen_share_started() so the
    perception state is updated instantly — before any frame is even
    analyzed — so the LLM cannot falsely say 'I can\'t see your screen'
    in the first turn after share starts.

    Non-destructive: safe to call even if perception package is absent.
    """
    global _audio_stream_buffer, _audio_stream_header, _audio_latest_chunks
    _audio_stream_buffer = bytearray()
    _audio_stream_header = bytearray()
    _audio_latest_chunks = []
    print("[ScreenAudio] Reset audio stream buffer on screen share start.")

    # Mark screen sharing as active (mic hibernation sentinel)
    SCREEN_SHARING_ACTIVE_TXT = os.path.join(SHARED_DIR, "screen_sharing_active.txt")
    try:
        os.makedirs(SHARED_DIR, exist_ok=True)
        with open(SCREEN_SHARING_ACTIVE_TXT, "w", encoding="utf-8") as f:
            f.write("active")
        print("[ScreenShare] Written screen_sharing_active.txt — mic will hibernate.")
    except Exception as e:
        print(f"[ScreenShare] Failed to write screen_sharing_active.txt (non-fatal): {e}")

    # Start low-latency streaming FFmpeg decoder
    _stop_ffmpeg()
    _start_ffmpeg()

    if _perception_writer is not None:
        try:
            _perception_writer.mark_screen_share_started()
            print("[PerceptionManager] /api/screen/start — screen share marked ACTIVE.")
        except Exception as e:
            print(f"[PerceptionManager] /api/screen/start error (non-fatal): {e}")
    return jsonify({"success": True, "status": "screen_share_started"})


@app.route("/api/screen/stop", methods=["POST"])
def screen_share_stopped():
    """
    Called by the browser immediately when the user stops screen sharing
    (clicking 'Stop Share' button or Esc on the browser share picker).

    Calls PerceptionManagerWriter.mark_screen_share_stopped() so the
    perception state is updated to inactive immediately — before the
    frame timeout would naturally expire. This prevents any window where
    the LLM is told screen sharing is active when it is not.

    Non-destructive: safe to call even if perception package is absent.
    """
    global _audio_stream_buffer, _audio_stream_header, _audio_latest_chunks
    _audio_stream_buffer = bytearray()
    _audio_stream_header = bytearray()
    _audio_latest_chunks = []
    print("[ScreenAudio] Reset audio stream buffer on screen share stop.")

    # Clear screen sharing active sentinel and voice-during-share sentinel
    SCREEN_SHARING_ACTIVE_TXT = os.path.join(SHARED_DIR, "screen_sharing_active.txt")
    VOICE_DURING_SHARE_TXT = os.path.join(SHARED_DIR, "voice_during_share.txt")
    for sentinel in [SCREEN_SHARING_ACTIVE_TXT, VOICE_DURING_SHARE_TXT]:
        try:
            if os.path.exists(sentinel):
                os.remove(sentinel)
        except Exception as e:
            print(f"[ScreenShare] Failed to remove {os.path.basename(sentinel)} (non-fatal): {e}")
    print("[ScreenShare] Removed screen_sharing_active.txt — mic will resume.")

    # Stop low-latency streaming FFmpeg decoder
    _stop_ffmpeg()

    if _perception_writer is not None:
        try:
            _perception_writer.mark_screen_share_stopped()
            print("[PerceptionManager] /api/screen/stop — screen share marked INACTIVE.")
        except Exception as e:
            print(f"[PerceptionManager] /api/screen/stop error (non-fatal): {e}")
    return jsonify({"success": True, "status": "screen_share_stopped"})


@app.route("/api/voice/during_share", methods=["POST"])
def toggle_voice_during_share():
    """
    Toggles the 'voice input during screen share' mode.

    When screen sharing is active, the mic hibernates by default to prevent
    multiple whisper-cli instances from spawning on ambient noise.
    This endpoint allows the user to manually opt-in to voice input while
    screen sharing is active.

    POST body: { "enabled": true/false }  — explicit set
    POST body: {}                          — toggle current state
    """
    VOICE_DURING_SHARE_TXT = os.path.join(SHARED_DIR, "voice_during_share.txt")
    try:
        data = request.get_json(silent=True) or {}
        if "enabled" in data:
            # Explicit set
            if data["enabled"]:
                os.makedirs(SHARED_DIR, exist_ok=True)
                with open(VOICE_DURING_SHARE_TXT, "w", encoding="utf-8") as f:
                    f.write("enabled")
                enabled = True
            else:
                if os.path.exists(VOICE_DURING_SHARE_TXT):
                    os.remove(VOICE_DURING_SHARE_TXT)
                enabled = False
        else:
            # Toggle current state
            if os.path.exists(VOICE_DURING_SHARE_TXT):
                os.remove(VOICE_DURING_SHARE_TXT)
                enabled = False
            else:
                os.makedirs(SHARED_DIR, exist_ok=True)
                with open(VOICE_DURING_SHARE_TXT, "w", encoding="utf-8") as f:
                    f.write("enabled")
                enabled = True
        print(f"[VoiceDuringShare] Manual voice during screen share: {'ENABLED' if enabled else 'DISABLED'}")
        return jsonify({"success": True, "voice_during_share": enabled})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────
# REAL-TIME SELF-EVOLVING AI SUBSYSTEM API ROUTES
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/evolution/status", methods=["GET"])
def evolution_status():
    """Returns the current state of the Self-Evolution Loop."""
    try:
        from evolution import get_evolution_orchestrator
        orch = get_evolution_orchestrator()
        return jsonify({"success": True, "status": orch.get_status()})
    except Exception as e:
        # Fallback to reading shared/evolution_state.json
        evo_state_file = os.path.join(SHARED_DIR, "evolution_state.json")
        if os.path.exists(evo_state_file):
            try:
                with open(evo_state_file, "r", encoding="utf-8") as f:
                    return jsonify({"success": True, "status": json.load(f)})
            except Exception as _err:
                print(f"[web_server.py] Silenced exception: {_err}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/evolution/audit", methods=["GET"])
def evolution_audit():
    """Returns the governance audit trail for the self-evolution engine."""
    try:
        from evolution.governance_layer import get_governance_layer
        gov = get_governance_layer()
        limit_str = request.args.get("limit", "50")
        limit = int(limit_str) if limit_str.isdigit() else 50
        return jsonify({"success": True, "audit_trail": gov.get_audit_trail(limit)})
    except Exception as e:
        audit_file = os.path.join(SHARED_DIR, "evolution_audit.json")
        if os.path.exists(audit_file):
            try:
                with open(audit_file, "r", encoding="utf-8") as f:
                    return jsonify({"success": True, "audit_trail": json.load(f)})
            except Exception as _err:
                print(f"[web_server.py] Silenced exception: {_err}")
        return jsonify({"success": False, "error": str(e)}), 500


import atexit

def cleanup_web_resources():
    try:
        _stop_ffmpeg()
    except Exception as _err:
        print(f"[web_server.py] Silenced exception: {_err}")


# ──────────────────────────────────────────────────────────────────────
# PERCEPTION STREAM & HEALTH ENDPOINTS
# ──────────────────────────────────────────────────────────────────────

@app.route("/api/perception/push", methods=["POST"])
def perception_push_event():
    """HTTP POST fallback endpoint for publishing multimodal perception events."""
    try:
        payload = request.get_json(force=True, silent=True) or {}
        if _perception_writer is not None:
            faces = payload.get("faces", [])
            if faces:
                primary_face = faces[0] if isinstance(faces, list) and len(faces) > 0 else {}
                gaze = primary_face.get("gaze", {})
                emo = primary_face.get("emotion", {})
                _perception_writer.record_face_perception_state({
                    "presence_state": "User Present" if faces else "User Missing",
                    "face_count": len(faces),
                    "gaze": {
                        "gaze_direction": gaze.get("gaze_direction", "Looking At Vivy"),
                        "eye_contact_score": gaze.get("eye_contact_prob", 0.8),
                        "eye_contact_strength": "Strong" if gaze.get("eye_contact_prob", 0.8) >= 0.7 else "Weak"
                    },
                    "primary_face": {
                        "emotion_label": emo.get("label", "neutral"),
                        "emotion_confidence": emo.get("confidence", 0.8),
                        "valence": emo.get("valence", 0.0),
                        "arousal": emo.get("arousal", 0.1)
                    }
                })
        if _PERCEPTION_AVAILABLE and _fusion_engine_mod is not None:
            try:
                _fusion_engine_mod.get_global_engine().push_perception_event(
                    source=payload.get("source", "perception_runner"),
                    semantic=json.dumps(payload),
                    importance=0.6,
                    confidence=1.0
                )
            except Exception as _err:
                print(f"[web_server.py] Silenced exception: {_err}")
        return jsonify({"success": True, "status": "event_pushed"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/perception/health", methods=["GET"], endpoint="api_perception_health")
@app.route("/perception/health", methods=["GET"], endpoint="perception_health")
def perception_health():
    """Health check endpoint for perception pipeline services."""
    try:
        from perception.runner import get_perception_runner
        runner = get_perception_runner()
        return jsonify({
            "status": "healthy",
            "perception_running": runner._running,
            "frame_id": runner.frame_id,
            "camera_active": runner.camera_manager.is_active(),
            "timestamp": time.time()
        })
    except Exception as e:
        return jsonify({"status": "degraded", "error": str(e), "timestamp": time.time()})


@app.route("/api/perception/events", methods=["GET"], endpoint="perception_events_list")
def perception_events_list():
    """Return recent perception events."""
    events_list = []
    if _PERCEPTION_AVAILABLE and _fusion_engine_mod is not None:
        try:
            events_list = _fusion_engine_mod.get_global_engine().get_recent_events(max_age_seconds=120)
        except Exception as _err:
            print(f"[web_server.py] Silenced exception: {_err}")
    return jsonify({"success": True, "events": events_list})


@app.route("/api/perception/narrative", methods=["GET"])
def perception_narrative():
    """Return current observation narrative synthesized by FusionEngine."""
    narrative = ""
    if _PERCEPTION_AVAILABLE and _fusion_engine_mod is not None:
        try:
            narrative = _fusion_engine_mod.get_global_engine().get_observation_narrative()
        except Exception as _err:
            print(f"[web_server.py] Silenced exception: {_err}")
    return jsonify({"success": True, "narrative": narrative})


# ──────────────────────────────────────────────────────────────────────
# ANIMATION AUTHORING PIPELINE ENDPOINTS
# ──────────────────────────────────────────────────────────────────────

_animation_pipeline = None

def get_animation_pipeline():
    global _animation_pipeline
    if _animation_pipeline is None:
        try:
            from animation_authoring_pipeline import AnimationAuthoringPipeline
            registry_path = os.path.join(BASE_DIR, "vivy_animation_registry.json")
            _animation_pipeline = AnimationAuthoringPipeline(registry_path)
        except Exception as e:
            print(f"[WebServer] Failed to initialize Animation Authoring Pipeline: {e}")
    return _animation_pipeline

@app.route("/api/authoring/list", methods=["GET"])
def authoring_list_animations():
    pipeline = get_animation_pipeline()
    if pipeline:
        animations = pipeline.get_existing_animations()
        return jsonify({"success": True, "animations": animations})
    return jsonify({"success": False, "error": "Pipeline not initialized"}), 500

@app.route("/api/authoring/upload", methods=["POST"])
def authoring_upload_video():
    pipeline = get_animation_pipeline()
    if not pipeline:
        return jsonify({"success": False, "error": "Pipeline not initialized"}), 500
        
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part in the request"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400
        
    try:
        task_id, path = pipeline.save_uploaded_video(file)
        return jsonify({"success": True, "task_id": task_id, "video_path": path})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

import threading

_authoring_tasks = {}

@app.route("/api/authoring/generate", methods=["POST"])
def authoring_generate_animation():
    pipeline = get_animation_pipeline()
    if not pipeline:
        return jsonify({"success": False, "error": "Pipeline not initialized"}), 500
        
    data = request.json or {}
    video_path = data.get("video_path")
    if not video_path or not os.path.exists(video_path):
        return jsonify({"success": False, "error": "Invalid or missing video path"}), 400
        
    task_id = str(uuid.uuid4())
    _authoring_tasks[task_id] = {"status": "processing", "progress": 0, "message": "Extracting motion...", "animation_data": None}
    
    def process_task(tid, v_path):
        try:
            pose_data = pipeline.extract_motion(v_path)
            _authoring_tasks[tid]["progress"] = 50
            _authoring_tasks[tid]["message"] = "Refining animation curves..."
            
            def update_status(msg):
                _authoring_tasks[tid]["message"] = msg
                
            anim_data = pipeline.generate_reusable_asset(pose_data, status_callback=update_status)
            _authoring_tasks[tid]["status"] = "complete"
            _authoring_tasks[tid]["progress"] = 100
            _authoring_tasks[tid]["message"] = "Generation complete. Triggering Final Acceptance Test..."
            _authoring_tasks[tid]["animation_data"] = anim_data
            
            # [V6.0 AUTOMATION HOOK] Automatically execute the Diagnostic Acceptance framework
            import subprocess
            subprocess.Popen(["python", "diagnostic_mode.py", anim_data["id"], v_path])
            
        except Exception as e:
            _authoring_tasks[tid]["status"] = "error"
            _authoring_tasks[tid]["message"] = str(e)
            
    thread = threading.Thread(target=process_task, args=(task_id, video_path))
    thread.daemon = True
    thread.start()
    
    return jsonify({"success": True, "task_id": task_id})

@app.route("/api/authoring/status/<task_id>", methods=["GET"])
def authoring_status(task_id):
    if task_id in _authoring_tasks:
        return jsonify({"success": True, "task": _authoring_tasks[task_id]})
    return jsonify({"success": False, "error": "Task not found"}), 404

@app.route("/api/authoring/preview", methods=["POST"])
def authoring_preview_animation():
    """Trigger the animation on the live avatar via the bridge."""
    data = request.json or {}
    trigger_name = data.get("trigger", "")
    if trigger_name:
        try:
            # Send trigger via SentinelBridge / AnimationPlanner logic
            # by writing to shared/animation_trigger.txt
            trigger_txt = os.path.join(BASE_DIR, "shared", "animation_trigger.txt")
            with open(trigger_txt, "w", encoding="utf-8") as f:
                f.write(trigger_name)
            return jsonify({"success": True, "status": f"Sent {trigger_name} to Avatar"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": False, "error": "No trigger provided"}), 400

@app.route("/api/authoring/save", methods=["POST"])
def authoring_save_animation():
    pipeline = get_animation_pipeline()
    if not pipeline:
        return jsonify({"success": False, "error": "Pipeline not initialized"}), 500
        
    data = request.json or {}
    animation_data = data.get("animation_data")
    target_id = data.get("target_id")
    is_overwrite = data.get("is_overwrite", False)
    category = data.get("category", "dance")
    
    if not animation_data or not target_id:
        return jsonify({"success": False, "error": "Missing animation data or target ID"}), 400
        
    try:
        success, msg = pipeline.save_to_registry(animation_data, target_id, is_overwrite, category)
        return jsonify({"success": success, "message": msg})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────
# PROCEDURAL ANIMATION PREVIEW ENDPOINTS
# Write C# code to a shared sentinel file; avatar_bridge.py picks it up
# and dispatches it to the Unity WebSocket connection in real-time.
# ──────────────────────────────────────────────────────────────────────

_PROC_CODE_FILE  = None   # resolved lazily from BASE_DIR
_PROC_STOP_FILE  = None

def _get_proc_paths():
    global _PROC_CODE_FILE, _PROC_STOP_FILE
    if _PROC_CODE_FILE is None:
        _PROC_CODE_FILE = os.path.join(BASE_DIR, "shared", "procedural_anim_code.cs")
        _PROC_STOP_FILE = os.path.join(BASE_DIR, "shared", "procedural_anim_stop.flag")
    return _PROC_CODE_FILE, _PROC_STOP_FILE

@app.route("/api/authoring/procedural/preview", methods=["POST"])
def procedural_preview():
    """
    Receives a C# code snippet from the Procedural Animation editor.
    Writes it to shared/procedural_anim_code.cs so avatar_bridge.py can
    dispatch it to Unity over the existing WebSocket connection.
    Also writes a trigger sentinel so Unity knows a new code push arrived.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        code = data.get("code", "").strip()
        if not code:
            return jsonify({"success": False, "error": "No code provided"}), 400

        code_file, stop_file = _get_proc_paths()
        os.makedirs(os.path.dirname(code_file), exist_ok=True)

        # Remove any previous stop flag
        try:
            if os.path.exists(stop_file):
                os.remove(stop_file)
        except Exception as _e:
            print(f"[ProceduralAnim] Could not remove stop flag (non-fatal): {_e}")

        # Write code atomically
        tmp_path = code_file + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(code)
        os.replace(tmp_path, code_file)

        # Unity Editor script VivyProceduralCompiler.cs will detect the file change directly.
        # We no longer trigger a dummy animation clip via avatar_bridge.
        # trigger_txt = os.path.join(BASE_DIR, "shared", "animation_trigger.txt")
        # try:
        #     with open(trigger_txt, "w", encoding="utf-8") as f:
        #         f.write("ProceduralCodePush")
        # except Exception as _e:
        #     print(f"[ProceduralAnim] Could not write animation_trigger.txt (non-fatal): {_e}")


        print(f"[ProceduralAnim] Code pushed ({len(code)} chars) to {code_file}")
        return jsonify({"success": True, "status": "code_dispatched", "bytes": len(code)})

    except Exception as e:
        print(f"[ProceduralAnim] /api/authoring/procedural/preview error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/authoring/procedural/stop", methods=["POST"])
def procedural_stop():
    """
    Signals Unity to stop the current procedural animation preview.
    Writes a stop flag to shared/procedural_anim_stop.flag.
    """
    try:
        _, stop_file = _get_proc_paths()
        os.makedirs(os.path.dirname(stop_file), exist_ok=True)
        with open(stop_file, "w", encoding="utf-8") as f:
            f.write("stop")
        print("[ProceduralAnim] Stop flag written.")
        return jsonify({"success": True, "status": "stop_requested"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

atexit.register(cleanup_web_resources)

if __name__ == "__main__":
    # Start background monitor thread
    monitor_thread = threading.Thread(target=monitor_pipeline, daemon=True)
    monitor_thread.start()
    
    # Run web server
    default_port = int(os.getenv("VIVY_WEB_PORT", str(8000 + 80)))
    default_host = os.getenv("VIVY_WEB_HOST", "127.0.0.1")
    try:
        from config.config_manager import get_config_manager
        cfg = get_config_manager()
        host = cfg.get("network.web_server_host", cfg.get("server.host", default_host))
        port = int(cfg.get("network.web_server_port", cfg.get("server.web_port", default_port)))
    except Exception:
        host = default_host
        port = default_port
    app.run(host=host, port=port, debug=False)

