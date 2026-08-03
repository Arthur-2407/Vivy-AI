"""
language/voice_selector.py
==========================
Step 6: Multilingual Voice Generation & RVC Identity Preservation
Routes foreign dialects and regional scripts to appropriate TTS synthesis backends
while preserving seamless compatibility with Vivy's custom RVC voice cloning engine.
"""

import os
import sys
import time
import logging
import subprocess
from typing import Dict, Any, Callable

from language.detector import LanguageDetector

logger = logging.getLogger(__name__)


class MultilingualVoiceSelector:
    """
    Selects optimal speech generation strategies based on dialect character scripts.
    Ensures regional languages (Odia, Bengali, Hindi, Japanese) receive accurate acoustic
    synthesis before being passed into the RVC voice cloning converter.
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.detector = LanguageDetector(config)
        self.preserve_rvc = self.detector.config.get("preserve_rvc_voice_identity", True)
        self.dialect_mapping = self.detector.config.get("regional_dialect_mapping", {})
        self._localized_engine_checked = False
        self._pyttsx3_available = False

    def _check_localized_engine(self):
        if not self._localized_engine_checked:
            self._localized_engine_checked = True
            try:
                import pyttsx3
                self._pyttsx3_available = True
                logger.info("[VoiceSelector] Localized system TTS backend available.")
            except ImportError:
                self._pyttsx3_available = False

    def synthesize(self, text: str, output_wav_path: str, lang_code: str = "en", fallback_tts_func: Callable = None) -> bool:
        """
        Synthesizes text into output_wav_path using the optimal engine for lang_code.
        If language is English or natively supported by Coqui/XTTS, executes standard fallback_tts_func.
        For regional Indic dialects, routes through localized OS synthesis to generate accurate phonics.
        """
        if not text or not text.strip():
            logger.warning("[VoiceSelector] Empty text provided for synthesis.")
            return False

        os.makedirs(os.path.dirname(output_wav_path) if os.path.dirname(output_wav_path) else ".", exist_ok=True)
        meta = self.dialect_mapping.get(lang_code, {})
        use_localized = meta.get("use_localized_tts", False)

        # 1. Standard English or non-localized dialect -> Invoke existing voice.generate_tts_only()
        if lang_code == "en" or not use_localized:
            if fallback_tts_func is not None:
                try:
                    fallback_tts_func(text, output_wav_path)
                    logger.info(f"[VoiceSelector] Synthesized {lang_code} audio via primary TTS engine.")
                    return os.path.exists(output_wav_path)
                except Exception as err:
                    logger.warning(f"[VoiceSelector] Primary TTS failed ({err}), attempting localized fallback...")
            
        # 2. Regional Dialect (Odia / Bengali / Hindi) -> Invoke localized system synthesis
        self._check_localized_engine()
        if self._pyttsx3_available:
            try:
                import pyttsx3
                engine = pyttsx3.init()
                # Try to select best matching system voice
                voices = engine.getProperty('voices')
                for v in voices:
                    v_lower = (getattr(v, 'name', '') + getattr(v, 'id', '')).lower()
                    if any(w in v_lower for w in [lang_code, meta.get("name", "").lower(), "india", "indic", "devanagari"]):
                        try:
                            engine.setProperty('voice', v.id)
                            break
                        except Exception:
                            pass
                
                # Set conversational speech rate
                try:
                    engine.setProperty('rate', 175)
                except Exception:
                    pass

                engine.save_to_file(text, output_wav_path)
                engine.runAndWait()
                logger.info(f"[VoiceSelector] Localized audio generated for dialect '{lang_code}' at {output_wav_path}")
                if os.path.exists(output_wav_path) and os.path.getsize(output_wav_path) > 100:
                    return True
            except Exception as loc_err:
                logger.error(f"[VoiceSelector] Localized synthesis failed: {loc_err}")

        # 3. Ultimate resilient fallback -> execute default TTS function to ensure audio continuity
        if fallback_tts_func is not None:
            try:
                fallback_tts_func(text, output_wav_path)
                logger.info(f"[VoiceSelector] Synthesized audio via resilient fallback TTS.")
                return os.path.exists(output_wav_path)
            except Exception as fb_err:
                logger.error(f"[VoiceSelector] Fallback TTS failed: {fb_err}")

        return os.path.exists(output_wav_path)
