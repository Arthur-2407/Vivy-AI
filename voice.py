import os
import re
import sys
import importlib.util
import types
import numpy as np
import sounddevice as sd
import soundfile as sf
from contextlib import contextmanager

# [COMPATIBILITY POLYFILL] Inject mock pkg_resources for modern setuptools environments where pkg_resources is omitted
try:
    import pkg_resources
except ImportError:
    _mock_pkg = types.ModuleType("pkg_resources")
    _mock_pkg.get_distribution = lambda name: types.SimpleNamespace(version="2.0.10")
    def _mock_resource_filename(package_or_requirement, resource_name):
        try:
            spec = importlib.util.find_spec(package_or_requirement)
            if spec and spec.origin:
                return os.path.join(os.path.dirname(spec.origin), resource_name.replace("/", os.sep))
        except Exception:
            pass
        return resource_name
    _mock_pkg.resource_filename = _mock_resource_filename
    sys.modules["pkg_resources"] = _mock_pkg


# ===============================
# Create recordings folder
# ===============================
RECORDINGS_DIR = "vivy_recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

recording_count = 0

from resource_manager import get_resource_manager

# ===============================
# Silent stdout/stderr context
# ===============================
@contextmanager
def suppress_output():
    with get_resource_manager().suppress_output():
        yield

# ===============================
# Available voices (declared immediately — model loads lazily)
# ===============================
print("Available voices:")
print("0: ljspeech_female (default)")

voices = ["ljspeech_female"]
selected_voice = voices[0]
print(f"Selected voice: {selected_voice}")

# ===============================
# Lazy TTS loader — defers Coqui TTS model init to first call.
# This prevents VS Code / Jedi LSP from crashing when it dry-imports
# this module during background analysis (exit code 1 / -32097 bug).
# The TTS model is still loaded exactly once — on first use.
# All existing callers use tts.tts_to_file(...) unchanged.
# ===============================
_tts_instance = None

def configure_female_voice(engine):
    """Ensure pyttsx3 engine uses an expressive female vocal identity (e.g. Zira, Haruka) and never defaults to a male voice like David."""
    try:
        voices = engine.getProperty('voices')
        best_voice = None
        # Prioritize high quality female voice profiles
        for v in voices:
            v_lower = (getattr(v, 'name', '') + getattr(v, 'id', '')).lower()
            if any(k in v_lower for k in ['zira', 'haruka', 'female', 'woman', 'hazel', 'hazem', 'eva', 'anime']) and not any(m in v_lower for m in ['david', 'mark', 'male']):
                best_voice = v
                break
        if not best_voice and voices:
            # Fallback to any non-male voice if available
            for v in voices:
                v_lower = (getattr(v, 'name', '') + getattr(v, 'id', '')).lower()
                if not any(m in v_lower for m in ['david', 'mark', 'male']):
                    best_voice = v
                    break
        if best_voice:
            engine.setProperty('voice', best_voice.id)
        engine.setProperty('rate', 175)
    except Exception as err:
        print(f"[Voice] Voice configuration exception (non-fatal): {err}")

def _get_tts():
    """Return the singleton TTS instance, creating it on first call.
    The TTS library import itself is deferred to here so that module-level
    import is near-instant and does not crash the Jedi/pygls LSP."""
    global _tts_instance
    if _tts_instance is None:
        try:
            import torch
            # 1. Attempt to load XTTS-v2 (Preferred)
            from TTS.api import TTS
            gpu_enabled = torch.cuda.is_available()
            with suppress_output():
                _tts_instance = TTS(
                    model_name="tts_models/multilingual/multi-dataset/xtts_v2",
                    progress_bar=False,
                    gpu=gpu_enabled
                )
            print(f"[Voice] Initialized XTTS-v2 (GPU: {gpu_enabled})")
        except Exception as e1:
            try:
                # 2. Attempt to load Chatterbox TTS
                import chatterbox
                with suppress_output():
                    _tts_instance = chatterbox.ChatterboxTTS(model="chatterbox-english")
                print("[Voice] Initialized Chatterbox TTS")
            except ImportError:
                # 3. Fallback to Coqui TTS (Tacotron2-DDC)
                try:
                    from TTS.api import TTS
                    with suppress_output():
                        _tts_instance = TTS(
                            model_name="tts_models/en/ljspeech/tacotron2-DDC",
                            progress_bar=False,
                            gpu=False
                        )
                    print("[Voice] Initialized Coqui TTS (Fallback)")
                except Exception as e3:
                    print(f"[Voice] Coqui TTS failed ({e3}), initializing offline pyttsx3 engine as Step 4 resilient fallback.")
                    class _OfflinePyTTSX3Engine:
                        def __init__(self):
                            import pyttsx3
                            self._engine_class = pyttsx3
                        def tts_to_file(self, text, file_path, speaker=None, **kwargs):
                            engine = self._engine_class.init()
                            configure_female_voice(engine)
                            engine.save_to_file(text, file_path)
                            engine.runAndWait()
                    _tts_instance = _OfflinePyTTSX3Engine()
    return _tts_instance

class _LazyTTSProxy:
    """Transparent proxy for TTS: delegates all attribute access and calls
    to the real TTS instance, which is created on first access."""
    def __getattr__(self, name):
        return getattr(_get_tts(), name)

    def __call__(self, *args, **kwargs):
        return _get_tts()(*args, **kwargs)

tts = _LazyTTSProxy()

# ===============================
# Voice properties
# ===============================
speech_rate = 1.0   # Recommended: 0.9 – 1.1
volume = 1.0        # 0.0 – 1.0

# ===============================
# Text sanitization & pacing
# ===============================
def clean_text(text: str) -> str:
    # 1. Remove <think>...</think> blocks completely
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    
    # 2. Remove any unclosed or standalone HTML/XML tags (e.g. <think>, <[^>]*>)
    text = re.sub(r"<[^>]*>", "", text)
    
    # 3. Remove asterisks actions (e.g., *blushes*, *giggles*)
    text = re.sub(r"\*.*?\*", "", text)
    
    # 4. Remove parenthetical/bracketed actions (e.g., (giggles), [sighs])
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"\[.*?\]", "", text)
    
    # 5. Remove emojis
    try:
        emoji_pattern = re.compile(
            "["
            "\U00010000-\U0010ffff"
            "\u2600-\u27BF"
            "\uFE0F"
            "]+", flags=re.UNICODE
        )
        text = emoji_pattern.sub("", text)
    except Exception as _err:
        print(f"[voice.py] Silenced exception: {_err}")

    text = text.strip()

    text = re.sub(r"\.{2,}", "...", text)
    text = re.sub(r"\s+", " ", text)

    # Natural pacing
    text = text.replace(",", ", ")
    text = text.replace(";", "; ")
    text = text.replace(":", ": ")

    # Remove extra spaces around punctuation
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)

    # Return placeholder if sanitized text is empty
    if not text.strip(".,!?;: "):
        return "Hmm."

    if not text.endswith((".", "!", "?")):
        text += "."

    return text

# ===============================
# Audio Processing Helpers
# ===============================
def normalize_audio(audio):
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.95
    return audio

def soft_compress(audio, threshold=0.6, ratio=4.0):
    compressed = np.copy(audio)
    mask = np.abs(audio) > threshold
    compressed[mask] = np.sign(audio[mask]) * (
        threshold + (np.abs(audio[mask]) - threshold) / ratio
    )
    return compressed

def time_stretch(audio, rate):
    if rate == 1.0:
        return audio

    # High-quality resampling (no robotic artifacts)
    new_length = int(len(audio) / rate)
    x_old = np.linspace(0, 1, len(audio))
    x_new = np.linspace(0, 1, new_length)
    return np.interp(x_new, x_old, audio).astype(np.float32)

def trim_silence(audio, threshold=0.0005):
    non_silent = np.where(np.abs(audio) > threshold)[0]
    if len(non_silent) == 0:
        return audio
    return audio[non_silent[0]:non_silent[-1]]

# ===============================
# Core Speak Function
# ===============================
def speak(text):
    global recording_count
    recording_count += 1

    text = clean_text(text)

    output_file = os.path.join(
        RECORDINGS_DIR, f"vivy_{recording_count}.wav"
    )

    # Generate speech
    with suppress_output():
        tts.tts_to_file(
            text=text,
            file_path=output_file,
            speaker=None
        )

    # Load audio
    data, samplerate = sf.read(output_file, dtype="float32")

    # Post-processing for natural voice
    data = trim_silence(data)
    data = time_stretch(data, speech_rate)
    data = soft_compress(data)
    data = normalize_audio(data)
    data *= volume

    # Play audio
    sd.play(data, samplerate)
    sd.wait()

def generate_tts_only(text, output_path):
    text = clean_text(text)
    
    # Ensure folder exists safely without failing on relative root paths
    if os.path.dirname(output_path):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Generate speech with resilient error recovery
    try:
        with suppress_output():
            tts.tts_to_file(
                text=text,
                file_path=output_path,
                speaker=None
            )
    except Exception as synth_err:
        print(f"[Voice] Primary synthesis exception ({synth_err}), executing resilient pyttsx3 offline fallback...")
        try:
            import pyttsx3
            eng = pyttsx3.init()
            configure_female_voice(eng)
            eng.save_to_file(text, output_path)
            eng.runAndWait()
        except Exception as fb_err:
            print(f"[Voice] Fallback engine error: {fb_err}")
            # Ensure file exists even on complete audio driver exhaustion to prevent downstream RVC crash
            if not os.path.exists(output_path):
                import numpy as _np, soundfile as _sf
                _sf.write(output_path, _np.zeros(22050, dtype=_np.float32), 22050)

    # Load audio
    data, samplerate = sf.read(output_path, dtype="float32")

    # Post-processing for natural voice
    data = trim_silence(data)
    data = time_stretch(data, speech_rate)
    data = soft_compress(data)
    data = normalize_audio(data)
    data *= volume

    # Save post-processed audio back to output_path
    sf.write(output_path, data, samplerate)


# ===============================
# Standalone test loop
# ===============================
if __name__ == "__main__":
    while True:
        text_to_speak = input(
            "\nEnter text to speak (or type 'exit'): "
        )
        if text_to_speak.lower() == "exit":
            break

        print("Speaking...")
        speak(text_to_speak)
