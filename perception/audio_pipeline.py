"""
perception/audio_pipeline.py
==============================
System/ambient audio perception pipeline for Vivy AI.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional, TypedDict, List, Dict, Any
import numpy as np

from perception.plugins.interfaces import BaseAudioAnalysisPlugin
from perception.model_router import ModelRouter

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Typed output
# ─────────────────────────────────────────────────────────────────────────────
class AudioEvent(TypedDict):
    """Structured output of one audio perception cycle."""
    timestamp:        float
    event_type:       str    # "music" | "speech" | "silence" | "ambient" | "alarm" | "applause" | "laughter" | "crying" | "explosion"
    description:      str    # Human-readable description
    confidence:       float  # 0.0–1.0
    duration_seconds: float  # Duration of the analysed chunk


# ─────────────────────────────────────────────────────────────────────────────
# Heuristic Audio Analysis Plugin
# ─────────────────────────────────────────────────────────────────────────────
class HeuristicAudioAnalysisPlugin(BaseAudioAnalysisPlugin):
    """Heuristic audio event analysis engine."""

    @property
    def name(self) -> str:
        return "heuristic"

    def is_available(self) -> bool:
        return True

    def analyze(self, audio_data: np.ndarray, sample_rate: int = 16000) -> List[Dict[str, Any]]:
        """
        Analyses a 1D float32 numpy audio chunk.
        Detects: silence, speech, music, notifications (alert/chime), environmental_sounds, or movie_game_audio.
        """
        events = []
        try:
            # We need config to check min_audio_level_db
            from perception.config_loader import get
            min_db = float(get("audio_perception", "min_audio_level_db", default=-40.0))

            # RMS energy
            rms = float(np.sqrt(np.mean(audio_data ** 2)))
            rms_db = 20 * np.log10(rms + 1e-9)
            duration = float(len(audio_data) / sample_rate)

            if rms_db < min_db:
                events.append({
                    "event_type": "silence",
                    "description": "No significant audio activity detected.",
                    "confidence": 0.9,
                    "duration_seconds": duration
                })
            else:
                # 1. Zero-crossing rate
                zcr = float(np.mean(np.abs(np.diff(np.sign(audio_data)))) / 2)

                # 2. Spectral analysis
                fft_vals = np.abs(np.fft.rfft(audio_data))
                freqs    = np.fft.rfftfreq(len(audio_data), 1 / sample_rate)
                centroid = float(np.sum(freqs * fft_vals) / (np.sum(fft_vals) + 1e-9))

                # 3. Spectral Rolloff (85% energy)
                cum_power = np.cumsum(fft_vals ** 2)
                tot_power = cum_power[-1] if len(cum_power) > 0 else 0
                if tot_power > 1e-9:
                    rolloff_idx = np.where(cum_power >= 0.85 * tot_power)[0]
                    rolloff = freqs[rolloff_idx[0]] if len(rolloff_idx) > 0 else 0.0
                else:
                    rolloff = 0.0

                # 4. Spectral Crest (peak value / mean value of magnitude spectrum)
                peak = np.max(fft_vals) if len(fft_vals) > 0 else 0
                mean_val = np.mean(fft_vals) if len(fft_vals) > 0 else 0
                crest = float(peak / (mean_val + 1e-9))

                # 5. Temporal dynamics (sub-frame variance)
                n_sub = 8
                sub_len = len(audio_data) // n_sub
                sub_rms = []
                for j in range(n_sub):
                    chunk = audio_data[j*sub_len:(j+1)*sub_len]
                    if len(chunk) > 0:
                        sub_rms.append(float(np.sqrt(np.mean(chunk ** 2))))
                rms_var = np.var(sub_rms) if sub_rms else 0.0
                rms_max_to_min = (np.max(sub_rms) / (np.min(sub_rms) + 1e-9)) if sub_rms else 1.0

                # Classification Logic
                if centroid > 2500 and crest > 10.0 and duration < 2.0:
                    events.append({
                        "event_type": "notifications",
                        "description": "High-pitched notification chime or alert detected.",
                        "confidence": 0.85,
                        "duration_seconds": duration
                    })
                elif rms_db > -22.0 and rms_max_to_min > 4.0 and rms_var > 0.003:
                    events.append({
                        "event_type": "movie_game_audio",
                        "description": "Dynamic media sound, action effects, or game audio with high temporal variance.",
                        "confidence": 0.8,
                        "duration_seconds": duration
                    })
                elif 3500 > centroid > 350 and 0.05 < zcr < 0.28 and rms_max_to_min > 2.5:
                    events.append({
                        "event_type": "speech",
                        "description": "Voice or speech activity detected in the audio.",
                        "confidence": 0.82,
                        "duration_seconds": duration
                    })
                elif 2800 > centroid > 250 and rms_max_to_min < 3.0 and rms_var < 0.002 and crest > 4.5:
                    events.append({
                        "event_type": "music",
                        "description": "Melodic audio or music playing steadily.",
                        "confidence": 0.78,
                        "duration_seconds": duration
                    })
                elif rms_max_to_min < 1.8 and rms_var < 0.0001 and crest < 4.0:
                    events.append({
                        "event_type": "environmental_sounds",
                        "description": "Continuous steady environmental background sound (room tone/static).",
                        "confidence": 0.65,
                        "duration_seconds": duration
                    })
                else:
                    events.append({
                        "event_type": "ambient",
                        "description": "Ambient background sound detected.",
                        "confidence": 0.5,
                        "duration_seconds": duration
                    })
        except Exception as e:
            logger.debug(f"[HeuristicAudioAnalysisPlugin] Analysis error: {e}")

        return events


# Register Heuristic Plugin with ModelRouter
ModelRouter.register_plugin("audio_analysis", "heuristic", HeuristicAudioAnalysisPlugin)


# ─────────────────────────────────────────────────────────────────────────────
# Audio Pipeline Thread runner
# ─────────────────────────────────────────────────────────────────────────────
class AudioPipeline:
    """
    Background ambient audio perception pipeline.
    Runs in a dedicated thread and routes analysis to ModelRouter plugins.
    """

    def __init__(self):
        self._thread:   Optional[threading.Thread] = None
        self._running:  bool                       = False
        self._lock      = threading.Lock()
        self._config:   dict                       = {}
        self._last_event_type: str                 = ""
        self._classification_history: Dict[str, List[str]] = {}

    def start(self) -> bool:
        cfg = self._load_config()
        if not cfg.get("enabled", False):
            logger.info("[AudioPipeline] Disabled by config — not starting.")
            return False

        with self._lock:
            if self._running:
                return True
            self._running = True

        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="AudioPipeline",
        )
        self._thread.start()
        logger.info("[AudioPipeline] Started.")
        return True

    def stop(self):
        with self._lock:
            self._running = False
        logger.info("[AudioPipeline] Stopped.")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        try:
            from perception.config_loader import get_config
            self._config = get_config().get("audio_perception", {})
        except Exception:
            self._config = {}
        return self._config

    def _run_loop(self):
        interval = float(self._config.get("ambient_analysis_interval", 2.0))
        logger.info("[AudioPipeline] Entering audio perception loop.")
        while self._running:
            try:
                # Capture system loopback and mic audio in parallel
                sys_chunk, mic_chunk = self._capture_both_audio(duration_seconds=interval)

                # Process system audio
                if sys_chunk is not None:
                    sys_events = self._classify_chunk(sys_chunk, interval, source="system")
                    for event in sys_events:
                        self._push_event(event)

                # Process mic audio
                if mic_chunk is not None:
                    mic_events = self._classify_chunk(mic_chunk, interval, source="mic")
                    for event in mic_events:
                        self._push_event(event)

            except Exception as e:
                logger.debug(f"[AudioPipeline] Loop error: {e}")
                time.sleep(interval)

    def _capture_both_audio(self, duration_seconds: float = 2.0) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        sys_data = None
        mic_data = None
        sample_rate = 16000
        use_loopback = self._config.get("system_audio_capture", False)

        device_sr = sample_rate
        device_channels = 1
        
        # Query default input device specifications
        try:
            import sounddevice as sd
            default_input = sd.default.device[0]
            if default_input >= 0:
                device_info = sd.query_devices(default_input, 'input')
                device_sr = int(device_info.get('default_samplerate', sample_rate))
                device_channels = min(2, int(device_info.get('max_input_channels', 1)))
        except Exception as e_query:
            logger.debug(f"[AudioPipeline] Input device query failed: {e_query}")

        # 1. Start mic recording asynchronously (sounddevice)
        try:
            import sounddevice as sd
            mic_recording = sd.rec(
                int(device_sr * duration_seconds),
                samplerate=device_sr,
                channels=device_channels,
                dtype="float32"
            )
        except Exception as e:
            logger.debug(f"[AudioPipeline] Failed to start sounddevice mic recording: {e}")
            mic_recording = None

        # 2. Capture system speaker audio (blocking) if loopback is enabled
        if use_loopback:
            try:
                import soundcard as sc
                default_speaker = sc.default_speaker()
                with default_speaker.recorder(samplerate=sample_rate) as recorder:
                    sys_raw = recorder.record(numframes=int(sample_rate * duration_seconds))
                if sys_raw.ndim > 1:
                    sys_data = sys_raw.mean(axis=1).astype("float32")
                else:
                    sys_data = sys_raw.astype("float32")
            except Exception as e:
                logger.debug(f"[AudioPipeline] WASAPI loopback capture failed: {e}")
                if mic_recording is None:
                    time.sleep(duration_seconds)
        else:
            # If system audio is not captured, we sleep/wait below
            if mic_recording is None:
                time.sleep(duration_seconds)

        # 3. Wait for mic recording to finish
        if mic_recording is not None:
            try:
                import sounddevice as sd
                sd.wait()
                if mic_recording.ndim > 1 and mic_recording.shape[1] > 1:
                    mic_data = mic_recording.mean(axis=1)
                else:
                    mic_data = mic_recording.flatten()
                
                # Resample to 16000 Hz if device rate differs from pipeline expectations
                if device_sr != sample_rate and len(mic_data) > 0:
                    x_old = np.linspace(0, duration_seconds, len(mic_data))
                    x_new = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds))
                    mic_data = np.interp(x_new, x_old, mic_data).astype("float32")
            except Exception as e:
                logger.debug(f"[AudioPipeline] sounddevice wait/processing failed: {e}")

        return sys_data, mic_data

    def _classify_chunk(self, audio_chunk: np.ndarray, duration_seconds: float, source: str) -> List[AudioEvent]:
        """Delegate analysis to ModelRouter audio_analysis plugin."""
        events: List[AudioEvent] = []
        try:
            plugin = ModelRouter.get_audio_analysis_plugin()
            if plugin:
                results = plugin.analyze(audio_chunk, sample_rate=16000)
                for res in results:
                    raw_event_type = res.get("event_type", "ambient")
                    
                    # Temporal consensus smoothing
                    if source not in self._classification_history:
                        self._classification_history[source] = []
                    hist = self._classification_history[source]
                    hist.append(raw_event_type)
                    if len(hist) > 8:
                        hist.pop(0)
                        
                    # Majority vote filtering
                    if raw_event_type in ("alarm", "notifications") and res.get("confidence", 0.5) > 0.85:
                        event_type = raw_event_type
                    else:
                        counts = {}
                        for item in hist:
                            counts[item] = counts.get(item, 0) + 1
                        sorted_types = sorted(counts.keys(), key=lambda k: (counts[k], k == raw_event_type), reverse=True)
                        event_type = sorted_types[0] if sorted_types else raw_event_type

                    # Dedup: skip if same type as last event for this source (reduces noise)
                    last_key = f"{source}:{event_type}"
                    if event_type in ("silence", "ambient") and getattr(self, "_last_event_key", None) == last_key:
                        continue
                    self._last_event_key = last_key
                    
                    description = res.get("description", "")
                    if event_type != raw_event_type:
                        desc_map = {
                            "silence": "No significant audio activity detected.",
                            "music": "Melodic audio or music playing steadily.",
                            "speech": "Voice or speech activity detected in the audio.",
                            "movie_game_audio": "Dynamic media sound, action effects, or game audio with high temporal variance.",
                            "environmental_sounds": "Continuous steady environmental background sound (room tone/static).",
                            "ambient": "Ambient background sound detected."
                        }
                        description = desc_map.get(event_type, description)

                    if source == "system":
                        description = f"System audio: {description}"
                    else:
                        description = f"Ambient: {description}"
                    
                    events.append(AudioEvent(
                        timestamp=time.time(),
                        event_type=event_type,
                        description=description,
                        confidence=res.get("confidence", 0.5),
                        duration_seconds=res.get("duration_seconds", duration_seconds)
                    ))
        except Exception as e:
            logger.debug(f"[AudioPipeline] Classification error: {e}")
        return events

    def _push_event(self, event: AudioEvent):
        try:
            from perception.fusion_engine import get_global_engine
            get_global_engine().push_audio_event(event)
        except Exception as e:
            logger.debug(f"[AudioPipeline] Push failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────────────────────────────────────
_global_pipeline: Optional[AudioPipeline] = None
_global_pipeline_lock = threading.Lock()


def get_global_pipeline() -> AudioPipeline:
    global _global_pipeline
    if _global_pipeline is None:
        with _global_pipeline_lock:
            if _global_pipeline is None:
                _global_pipeline = AudioPipeline()
    return _global_pipeline


def start_if_enabled() -> bool:
    try:
        return get_global_pipeline().start()
    except Exception as e:
        logger.warning(f"[AudioPipeline] start_if_enabled() failed: {e}")
        return False
