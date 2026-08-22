import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import sys
# [HOTFIX] Mock pkg_resources to prevent legacy packages (webrtcvad) from crashing modern environments
try:
    import pkg_resources
except ImportError:
    class MockPkgResources:
        class Distribution:
            version = "2.0.10"
        @staticmethod
        def get_distribution(name):
            return MockPkgResources.Distribution()
    sys.modules['pkg_resources'] = MockPkgResources()
import webrtcvad
import subprocess
import queue
import sys
import time
import os
import threading
from colorama import Fore, Style
from resource_manager import get_resource_manager

# Reconfigure stdout/stderr to use utf-8 to avoid encoding errors with emojis on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Real terminal output reference — set by run_vivy.py after stdout redirect
# Falls back to sys.stdout if not set (standalone use stays unchanged)
_console_out = None

def set_console_out(stream):
    """Inject the real terminal stdout handle (called by run_vivy.py)."""
    global _console_out
    _console_out = stream

def _cprint(msg):
    """Write msg to the real terminal if available, otherwise to sys.stdout."""
    target = _console_out if _console_out is not None else sys.stdout
    try:
        target.write(msg + "\n")
        target.flush()
    except Exception as _err:
        print(f"[mic_input.py] Silenced exception: {_err}")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from config.config_manager import get_config_manager
    cfg = get_config_manager()
    SAMPLE_RATE = int(cfg.get("pipeline.mic_sample_rate", 16000))
    FRAME_MS = int(cfg.get("pipeline.mic_frame_ms", 30))
    BASE_SILENCE_TIMEOUT = float(cfg.get("pipeline.mic_base_silence_timeout", 1.2))
    MAX_SILENCE_LIMIT = float(cfg.get("pipeline.mic_max_silence_limit", 3.0))
    
    WHISPER_PATH = os.path.join(BASE_DIR, "whisper.cpp", "whisper-cli.exe")
    # Fetch from models.whisper, otherwise fallback
    _model_path_cfg = cfg.get("models.whisper", "models/ggml-small.bin")
    MODEL_PATH = os.path.abspath(os.path.join(BASE_DIR, _model_path_cfg))
except Exception:
    SAMPLE_RATE = 16000
    FRAME_MS = 30
    BASE_SILENCE_TIMEOUT = 1.2
    MAX_SILENCE_LIMIT = 3.0
    WHISPER_PATH = os.path.join(BASE_DIR, "whisper.cpp", "whisper-cli.exe")
    MODEL_PATH = os.path.join(BASE_DIR, "models", "ggml-small.bin")

CHANNELS = 1
FRAME_SIZE = int(SAMPLE_RATE * FRAME_MS / 1000)
MAX_SILENCE_FRAMES = int(BASE_SILENCE_TIMEOUT / (FRAME_MS / 1000))

RECORD_DIR = os.path.join(BASE_DIR, "recordings")
OUT_PREFIX = os.path.join(RECORD_DIR, "last")

os.makedirs(RECORD_DIR, exist_ok=True)
# =========================================
STATUS_TXT = os.path.join(BASE_DIR, "shared", "status.txt")

def set_status(status):
    try:
        with open(STATUS_TXT, "w", encoding="utf-8") as sf:
            sf.write(status)
    except Exception as _err:
        print(f"[mic_input.py] Silenced exception: {_err}")
vad = webrtcvad.Vad(2)
audio_queue = queue.Queue()

# Silero VAD Integration
_silero_vad_model = None
_silero_get_speech_timestamps = None
try:
    import torch
    # Suppress output to prevent messing up the terminal UI
    import warnings
    warnings.filterwarnings("ignore")
    _silero_vad_model, utils = torch.hub.load(
        repo_or_dir='snakers4/silero-vad',
        model='silero_vad',
        force_reload=False,
        onnx=False,
        trust_repo=True
    )
    (get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) = utils
    _silero_get_speech_timestamps = get_speech_timestamps
    print(Fore.GREEN + "[mic_input] Silero VAD loaded successfully." + Style.RESET_ALL)
except Exception as e:
    print(Fore.YELLOW + f"[mic_input] Silero VAD not available, using WebRTC VAD fallback. ({e})" + Style.RESET_ALL)

# Global lock: only ONE whisper-cli subprocess may run at a time.
# Prevents the 6+ simultaneous whisper-cli processes seen in Task Manager
# when the mic loop fires faster than whisper can transcribe.
_whisper_lock = threading.RLock()

recording = False
audio_buffer = []
start_time = 0
silence_frames = 0
speech_frames = 0

noise_profile = np.zeros(FRAME_SIZE // 2 + 1, dtype=np.float32)
NOISE_ALPHA = 0.01

# Wav2Vec2 Voice Emotion Integration (Lazy Loaded)
_voice_emotion_model = None
_voice_emotion_processor = None
_voice_emotion_init_attempted = False

def _get_voice_emotion_model():
    global _voice_emotion_model, _voice_emotion_processor, _voice_emotion_init_attempted
    if not _voice_emotion_init_attempted:
        _voice_emotion_init_attempted = True
        try:
            from transformers import Wav2Vec2ForSequenceClassification, Wav2Vec2FeatureExtractor
            _voice_emotion_processor = Wav2Vec2FeatureExtractor.from_pretrained("ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition")
            _voice_emotion_model = Wav2Vec2ForSequenceClassification.from_pretrained("ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition")
            print(Fore.GREEN + "[mic_input] Wav2Vec2 Voice Emotion model loaded successfully." + Style.RESET_ALL)
        except ImportError:
            print(Fore.YELLOW + "[mic_input] transformers package missing, Wav2Vec2 Emotion disabled." + Style.RESET_ALL)
        except Exception as e:
            print(Fore.YELLOW + f"[mic_input] Wav2Vec2 Voice Emotion init error: {e}" + Style.RESET_ALL)
    return _voice_emotion_model, _voice_emotion_processor

# ============= MIC SELECTION =============
def list_mics():
    print(Fore.YELLOW + "\nAvailable Microphones:")
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print(f"[{i}] {d['name']}")
    print(Style.RESET_ALL)

def select_mic():
    # Automatically select default system recording device to avoid console blocking
    try:
        default_input = sd.default.device[0]
        if default_input >= 0:
            return default_input
    except Exception as _err:
        print(f"[mic_input.py] Silenced exception: {_err}")
    
    # Fallback: select first device with input channels
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            return i
    return 0

def show_timer():
    elapsed = time.time() - start_time
    sys.stdout.write(
        Fore.CYAN + f"\rRecording: {elapsed:05.1f}s " + Style.RESET_ALL
    )
    sys.stdout.flush()

# ========== SAFE STREAM DENOISER ==========
def suppress_noise(frame):
    global noise_profile
    spectrum = np.fft.rfft(frame)
    mag = np.abs(spectrum)
    noise_profile[:] = (1 - NOISE_ALPHA) * noise_profile + NOISE_ALPHA * mag
    clean_mag = np.maximum(mag - noise_profile * 0.8, 0.0)
    clean_spec = clean_mag * np.exp(1j * np.angle(spectrum))
    return np.fft.irfft(clean_spec).astype(np.float32)

def run_whisper(wav_file, output_txt_path=None):
    set_status("transcribing")
    print(Fore.GREEN + "\nTranscribing..." + Style.RESET_ALL)
    _cprint("  \033[96mTranscribing voice...\033[0m")

    # Pluggable speech integration with automatic language metadata preservation
    text = ""
    detected_lang = "en"
    lang_confidence = 1.0
    try:
        from perception.model_router import ModelRouter
        speech_plugin = ModelRouter.get_speech_plugin()
        if speech_plugin and speech_plugin.is_available():
            # Acquire lock: only one transcription at a time
            if not _whisper_lock.acquire(timeout=8.0):
                print(Fore.YELLOW + "[Whisper] Another transcription in progress, skipping this recording." + Style.RESET_ALL)
                set_status("ready")
                return ""
            try:
                res = speech_plugin.transcribe(wav_file)
                text = res.get("text", "")
                detected_lang = res.get("language", "en")
                lang_confidence = res.get("confidence", 1.0)
            finally:
                _whisper_lock.release()
        else:
            # Fallback if plugin is not available or registered
            if not _whisper_lock.acquire(timeout=8.0):
                print(Fore.YELLOW + "[Whisper] Another transcription in progress, skipping this recording." + Style.RESET_ALL)
                set_status("ready")
                return ""
            try:
                import re as _re_w
                result = subprocess.run(
                    [
                        WHISPER_PATH,
                        "-m", MODEL_PATH,
                        "-f", wav_file,
                        "-t", "2",
                        "-l", "auto",
                        "--prompt", "Vivy",
                    ],
                    cwd=BASE_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )
                text = result.stdout.strip()
                combo = f"{result.stderr}\n{result.stdout}"
                m = _re_w.search(r"detecting language:\s*([a-z]{2,3})\s*(?:\(p\s*=\s*([0-9.]+)\))?", combo, _re_w.IGNORECASE)
                if m:
                    detected_lang = m.group(1).lower()
                    if len(m.groups()) >= 2 and m.group(2):
                        try: lang_confidence = float(m.group(2))
                        except (ValueError, TypeError): pass
            finally:
                _whisper_lock.release()
    except Exception as e:
        print(Fore.RED + f"Pluggable speech failed: {e}. Falling back to legacy subprocess..." + Style.RESET_ALL)
        if not _whisper_lock.acquire(timeout=8.0):
            print(Fore.YELLOW + "[Whisper] Another transcription in progress, skipping this recording." + Style.RESET_ALL)
            set_status("ready")
            return ""
        try:
            import re as _re_w
            result = subprocess.run(
                [
                    WHISPER_PATH,
                    "-m", MODEL_PATH,
                    "-f", wav_file,
                    "-t", "2",
                    "-l", "auto",
                    "--prompt", "Vivy",
                ],
                cwd=BASE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            text = result.stdout.strip()
            combo = f"{result.stderr}\n{result.stdout}"
            m = _re_w.search(r"detecting language:\s*([a-z]{2,3})\s*(?:\(p\s*=\s*([0-9.]+)\))?", combo, _re_w.IGNORECASE)
            if m:
                detected_lang = m.group(1).lower()
                if len(m.groups()) >= 2 and m.group(2):
                    try: lang_confidence = float(m.group(2))
                    except (ValueError, TypeError): pass
        finally:
            _whisper_lock.release()

    if not text:
        print(Fore.RED + "No transcription produced." + Style.RESET_ALL)
        _cprint("  \033[90m[No speech recognized — returning to ready]\033[0m")
        set_status("ready")
        return ""

    # Suppress ambient silence and [BLANK_AUDIO] at the source to terminate loopback feedback
    try:
        from run_vivy import is_blank_or_noise
        if is_blank_or_noise(text) or "[blank_audio]" in text.lower() or "(speaking in foreign language)" in text.lower():
            print(Fore.YELLOW + f"[Whisper] Suppressed ambient silence or unparsed audio: '{text}'" + Style.RESET_ALL)
            _cprint(f"  \033[90m🗣  Heard: {text} [ambient silence ignored]\033[0m")
            set_status("ready")
            time.sleep(0.45)  # Acoustic loop stabilization pause
            return ""
    except Exception as _nb_err:
        print(f"[mic_input.py] Silenced noise check exception: {_nb_err}")

    # FORCE creation of transcript file
    transcript_dir = os.path.join(BASE_DIR, "transcripts")
    os.makedirs(transcript_dir, exist_ok=True)

    txt_path = os.path.join(
        transcript_dir,
        os.path.basename(wav_file).replace(".wav", ".txt")
    )

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)

    # Propagate detected language metadata without discarding STT classification
    try:
        from language.detector import LanguageDetector
        _ld = LanguageDetector()
        if not detected_lang or detected_lang == "en":
            _det = _ld.classify_text_by_script(text)
            if _det.get("code", "en") != "en":
                detected_lang = _det.get("code")
                lang_confidence = _det.get("confidence", 0.95)
                
        _lang_path = os.path.join(BASE_DIR, "shared", "detected_language.txt")
        with open(_lang_path, "w", encoding="utf-8") as lf:
            lf.write(detected_lang)
            
        if detected_lang != "en":
            mapping = _ld.config.get("regional_dialect_mapping", {})
            lang_name = mapping.get(detected_lang, {}).get("name", detected_lang.upper())
            print(Fore.MAGENTA + f"Detected Language: {lang_name} ({detected_lang}) [Confidence: {lang_confidence:.2f}]" + Style.RESET_ALL)
            _cprint(f"  \033[95m🌐 Detected Language: {lang_name} ({detected_lang}) [Confidence: {lang_confidence:.2f}]\033[0m")
    except Exception as _l_err:
        print(Fore.YELLOW + f"[mic_input] Language identification warning: {_l_err}" + Style.RESET_ALL)

    print(Fore.WHITE + "🗣 " + text + Style.RESET_ALL)
    print(Fore.CYAN + f"Transcript saved: {txt_path}" + Style.RESET_ALL)
    _cprint(f"  \033[97m🗣  Heard: {text}\033[0m")

    # Write to speech_diagnostics.json
    try:
        import json
        diag_file = os.path.join(BASE_DIR, "shared", "speech_diagnostics.json")
        os.makedirs(os.path.dirname(diag_file), exist_ok=True)
        with open(diag_file, "w", encoding="utf-8") as df:
            json.dump({
                "last_speech_transcript": text,
                "last_speech_timestamp": time.time()
            }, df, indent=2)
    except Exception as de:
        print(Fore.RED + f"Error writing speech diagnostics: {de}" + Style.RESET_ALL)

    if output_txt_path:
        try:
            source_file = os.path.join(BASE_DIR, "shared", "input_source.txt")

            # Check if there is pending unread user text from web chat client
            pending_text = ""
            if os.path.exists(output_txt_path):
                try:
                    with open(output_txt_path, "r", encoding="utf-8") as f_check:
                        pending_text = f_check.read().strip()
                except Exception as _err:
                    print(f"[mic_input.py] Silenced exception: {_err}")

            # If pending user text from text client exists, do not overwrite it
            if pending_text:
                source_mode = ""
                if os.path.exists(source_file):
                    try:
                        with open(source_file, "r", encoding="utf-8") as sf_check:
                            source_mode = sf_check.read().strip().lower()
                    except Exception as _err:
                        print(f"[mic_input.py] Silenced exception: {_err}")
                if source_mode == "text":
                    print(Fore.YELLOW + f"[mic_input] Preserving pending web chat text: '{pending_text}' (skipping voice write)." + Style.RESET_ALL)
                    return text

            # Write input source first
            try:
                with open(source_file, "w", encoding="utf-8") as sf:
                    sf.write("voice")
            except Exception as se:
                print(Fore.RED + f"Error writing input source: {se}" + Style.RESET_ALL)

            with open(output_txt_path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            print(Fore.RED + f"Error writing to {output_txt_path}: {e}" + Style.RESET_ALL)

    return text

def start_mic_listening(output_txt_path=None, mic_index=None):
    global recording, audio_buffer, start_time, silence_frames, speech_frames, noise_profile
    
    set_status("ready")
    
    # [VOICE STATE MANAGEMENT] Ensure mic does not automatically open unthrottled loop by default
    # unless auto_listen is enabled in config or user activates voice mode in UI/push-to-talk.
    try:
        from config.config_manager import get_config_manager
        _cfg = get_config_manager()
        auto_listen_enabled = _cfg.get("pipeline.auto_listen", False)
        mic_mute_path = os.path.join(BASE_DIR, "shared", "mic_mute.txt")
        if not auto_listen_enabled and not os.path.exists(mic_mute_path):
            os.makedirs(os.path.dirname(mic_mute_path), exist_ok=True)
            with open(mic_mute_path, "w", encoding="utf-8") as f:
                f.write("muted by default (auto_listen=false)")
            print(Fore.YELLOW + "\n[Voice Input] Standby Mode Active (auto_listen=false). Mic is muted until toggled ON in Dashboard UI or Config.\n" + Style.RESET_ALL)
    except Exception as _al_err:
        print(f"[mic_input] Auto-listen initialization check warning: {_al_err}")


    if mic_index is None:
        mic_index = select_mic()
        
    def callback(indata, frames, time_info, status):
        audio_queue.put(indata.copy())

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        blocksize=FRAME_SIZE,
        dtype="int16",
        callback=callback,
        device=mic_index,
    ):
        print(Fore.GREEN + "\nAuto-listening loop started (respects mute state & cooldowns).\n" + Style.RESET_ALL)
        
        recording = False
        audio_buffer = []
        pre_speech_buffer = []
        silence_frames = 0
        speech_frames = 0
        was_vivy_active = False
        last_partial_time = 0
        last_partial_text = "" 

        while True:
            # Check for mic mute file or active pipeline status (speaking, thinking, voice generation)
            # This prevents mic feedback loopback transcribing Vivy's own speaker output.
            status = "ready"
            if os.path.exists(os.path.join(BASE_DIR, "shared", "status.txt")):
                try:
                    with open(os.path.join(BASE_DIR, "shared", "status.txt"), "r", encoding="utf-8") as sf:
                        status = sf.read().strip().lower()
                except Exception as _err:
                    print(f"[mic_input.py] Silenced exception: {_err}")

            # ── Screen sharing hibernation guard ────────────────────────────
            # If screen sharing is active and user has NOT manually opted in
            # to voice-during-share, hibernate the mic loop to prevent ambient
            # noise from triggering back-to-back whisper-cli invocations.
            screen_sharing_active = os.path.exists(
                os.path.join(BASE_DIR, "shared", "screen_sharing_active.txt")
            )
            voice_during_share = os.path.exists(
                os.path.join(BASE_DIR, "shared", "voice_during_share.txt")
            )
            if screen_sharing_active and not voice_during_share:
                # Drain the audio queue to avoid stale audio building up
                while not audio_queue.empty():
                    try:
                        audio_queue.get_nowait()
                    except queue.Empty:
                        break
                recording = False
                time.sleep(0.5)
                continue
            # ───────────────────────────────────────────────────────────────

            mute = os.path.exists(os.path.join(BASE_DIR, "shared", "mic_mute.txt"))
            is_vivy_active = status in ("speaking", "generating_tts", "applying_rvc", "thinking", "processing", "transcribing")
            
            if mute or is_vivy_active:
                if mute and status != "muted":
                    set_status("muted")
                while not audio_queue.empty():
                    try:
                        audio_queue.get_nowait()
                    except queue.Empty:
                        break
                recording = False
                was_vivy_active = is_vivy_active
                time.sleep(0.15)
                continue
            elif was_vivy_active:
                # Coordinated state machine: apply acoustic cooldown after Vivy stops speaking/thinking
                was_vivy_active = False
                time.sleep(0.4)
                while not audio_queue.empty():
                    try:
                        audio_queue.get_nowait()
                    except queue.Empty:
                        break

            data = audio_queue.get()
            pcm_bytes = data.reshape(-1).tobytes()
            
            if _silero_vad_model is not None:
                # Silero requires float32 tensors in [-1, 1]
                float32_data = data.astype(np.float32) / 32768.0
                tensor_data = torch.from_numpy(float32_data).unsqueeze(0)
                try:
                    speech_timestamps = _silero_get_speech_timestamps(
                        tensor_data,
                        _silero_vad_model,
                        sampling_rate=SAMPLE_RATE,
                        threshold=0.3
                    )
                    speech = len(speech_timestamps) > 0
                except Exception:
                    speech = vad.is_speech(pcm_bytes, SAMPLE_RATE)
            else:
                speech = vad.is_speech(pcm_bytes, SAMPLE_RATE)

            # ── Screen audio contamination check ──
            # Load perception state to get screen audio activity
            screen_audio_rms = 0.0
            screen_audio_active = False
            try:
                import json
                state_file = os.path.join(BASE_DIR, "shared", "perception_state.json")
                if os.path.exists(state_file):
                    with open(state_file, "r", encoding="utf-8") as f:
                        state = json.load(f)
                        screen_audio_active = state.get("audio_active", False)
                        screen_audio_rms = state.get("last_audio_rms", 0.0)
            except Exception as _err:
                print(f"[mic_input.py] Silenced exception: {_err}")

            mic_rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2)))
            
            # If screen audio is active and playing sound, check for loopback contamination
            if screen_audio_active and screen_audio_rms > 200.0:
                # If mic RMS is close to or lower than the screen audio RMS,
                # it is highly likely to be speaker bleed-through/loopback contamination.
                if mic_rms < screen_audio_rms * 1.5:
                    speech = False
            # ──────────────────────────────────────

            if speech:
                silence_frames = 0
                speech_frames += 1

                if not recording:
                    recording = True
                    # Prepend pre-speech sliding window (~360ms) to preserve opening consonants and dialect phonetics
                    audio_buffer = list(pre_speech_buffer)
                    pre_speech_buffer.clear()
                    speech_frames = 0
                    start_time = time.time()
                    set_status("recording")
                    print(Fore.GREEN + "\n🎤 Voice detected. Recording..." + Style.RESET_ALL)
                    _cprint("  \033[92m🎤 Voice detected. Recording...\033[0m")
            else:
                if recording:
                    silence_frames += 1
                else:
                    pre_speech_buffer.append(data.copy())
                    if len(pre_speech_buffer) > 12:
                        pre_speech_buffer.pop(0)

            if recording:
                audio_buffer.append(data.copy())
                show_timer()
                
                # Rolling Context Partial Transcription (every 1.5 seconds)
                if time.time() - last_partial_time > 1.5 and len(audio_buffer) > 20:
                    last_partial_time = time.time()
                    try:
                        import numpy as np
                        import scipy.io.wavfile as wav
                        raw = (np.concatenate(audio_buffer, axis=0).reshape(-1).astype(np.float32) / 32768.0)
                        pcm16 = np.clip(raw * 32768, -32768, 32767).astype(np.int16)
                        tmp_wav = os.path.join(RECORD_DIR, "partial_tmp.wav")
                        wav.write(tmp_wav, SAMPLE_RATE, pcm16)
                        
                        # Lazy import of text_queue and stt backend to avoid NameError
                        # from incomplete patch application (patch_mic.py was only partially applied)
                        try:
                            from pipeline.queues import text_queue as _partial_text_queue
                        except Exception:
                            _partial_text_queue = None

                        # Resolve the STT backend: prefer ModelRouter speech plugin,
                        # fall back to WhisperCLIBackend subprocess
                        _partial_stt = None
                        try:
                            from perception.model_router import ModelRouter as _MR
                            _sp = _MR.get_speech_plugin()
                            if _sp and _sp.is_available():
                                _partial_stt = _sp
                        except Exception:
                            pass
                        if _partial_stt is None:
                            try:
                                from pipeline.stt import WhisperCLIBackend as _WCLIBE
                                _partial_stt = _WCLIBE(model_path=MODEL_PATH, whisper_exe=WHISPER_PATH)
                            except Exception:
                                pass

                        if _partial_stt is not None:
                            raw_result = _partial_stt.transcribe(tmp_wav)
                            # Handle both dict (ModelRouter) and str (pipeline.stt) return types
                            if isinstance(raw_result, dict):
                                partial_text = raw_result.get("text", "")
                            else:
                                partial_text = raw_result or ""
                            if partial_text and partial_text != last_partial_text:
                                last_partial_text = partial_text
                                if _partial_text_queue is not None:
                                    try:
                                        _partial_text_queue.put_nowait({"type": "partial", "text": partial_text})
                                    except Exception:
                                        pass
                    except Exception:
                        pass


            if recording and silence_frames > MAX_SILENCE_FRAMES:
                print(Fore.YELLOW + "\nSilence detected. Processing..." + Style.RESET_ALL)
                _cprint("  \033[93mSilence detected. Processing voice...\033[0m")
                set_status("processing")
                recording = False
                silence_frames = 0

                raw = (
                    np.concatenate(audio_buffer, axis=0)
                    .reshape(-1)
                    .astype(np.float32)
                    / 32768.0
                )

                # Preserve unattenuated raw waveform for high-fidelity speech consonant transcription
                pcm16 = np.clip(raw * 32768, -32768, 32767).astype(np.int16)

                filename = os.path.join(RECORD_DIR, f"rec_{int(time.time())}.wav")
                wav.write(filename, SAMPLE_RATE, pcm16)

                print(Fore.CYAN + f"Saved: {filename}" + Style.RESET_ALL)

                if os.path.getsize(filename) > 1000:
                    # Execute Wav2Vec2 Voice Emotion inference if available
                    ve_model, ve_proc = _get_voice_emotion_model()
                    if ve_model is not None and ve_proc is not None:
                        try:
                            # Use original raw float32 data for emotion feature extraction
                            inputs = ve_proc(raw, sampling_rate=SAMPLE_RATE, return_tensors="pt", padding=True)
                            with torch.no_grad():
                                logits = ve_model(**inputs).logits
                            predicted_ids = torch.argmax(logits, dim=-1).item()
                            emotion_labels = ve_model.config.id2label
                            voice_emotion = emotion_labels.get(predicted_ids, "neutral")
                            print(Fore.MAGENTA + f"Voice Emotion Detected: {voice_emotion}" + Style.RESET_ALL)
                            
                            # Log voice emotion for the Emotion Engine
                            ve_path = os.path.join(BASE_DIR, "shared", "voice_emotion.txt")
                            with open(ve_path, "w", encoding="utf-8") as vef:
                                vef.write(voice_emotion)
                        except Exception as e:
                            print(Fore.YELLOW + f"Voice Emotion inference failed: {e}" + Style.RESET_ALL)

                    run_whisper(filename, output_txt_path)
                else:
                    print(Fore.RED + "Invalid WAV, skipped." + Style.RESET_ALL)

if __name__ == "__main__":
    start_mic_listening()

