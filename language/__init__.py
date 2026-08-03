"""
Vivy AI Core Neural Pipeline — Multilingual & Cross-Lingual Intelligence Subsystem
===================================================================================
Provides robust, zero-hardcoded language detection, routing, memory extraction,
output translation, and multilingual TTS with RVC voice identity preservation.

v2.0 — Hybrid Language Intelligence Layer with NLLB-200 (CPU) + Qwen3 orchestration.
"""

import os
import sys
import logging

logger = logging.getLogger(__name__)

# Ensure base directory is in sys.path for internal imports
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

_language_router_instance = None
_detector_instance = None
_voice_selector_instance = None
_language_manager_instance = None


def get_language_detector():
    """Returns a singleton instance of the LanguageDetector."""
    global _detector_instance
    if _detector_instance is None:
        try:
            from language.detector import LanguageDetector
            _detector_instance = LanguageDetector()
            logger.info("[LanguageEngine] LanguageDetector initialized.")
        except Exception as err:
            logger.error(f"[LanguageEngine] Error initializing LanguageDetector: {err}")
            _detector_instance = None
    return _detector_instance


def get_language_router():
    """Returns a singleton instance of the LanguageRouter."""
    global _language_router_instance
    if _language_router_instance is None:
        try:
            from language.router import LanguageRouter
            _language_router_instance = LanguageRouter()
            logger.info("[LanguageEngine] LanguageRouter initialized.")
        except Exception as err:
            logger.error(f"[LanguageEngine] Error initializing LanguageRouter: {err}")
            _language_router_instance = None
    return _language_router_instance


def get_voice_selector():
    """Returns a singleton instance of the MultilingualVoiceSelector."""
    global _voice_selector_instance
    if _voice_selector_instance is None:
        try:
            from language.voice_selector import MultilingualVoiceSelector
            _voice_selector_instance = MultilingualVoiceSelector()
            logger.info("[LanguageEngine] MultilingualVoiceSelector initialized.")
        except Exception as err:
            logger.error(f"[LanguageEngine] Error initializing MultilingualVoiceSelector: {err}")
            _voice_selector_instance = None
    return _voice_selector_instance


def get_language_manager():
    """
    Returns a singleton instance of the LanguageManager (v2.0 Hybrid Intelligence Layer).
    Coordinates NLLB-200, Qwen3, LanguageContext, PromptLocalizer, LanguageMemory, and
    TranslationValidator in a single orchestrated subsystem.
    """
    global _language_manager_instance
    if _language_manager_instance is None:
        try:
            from language.language_manager import LanguageManager
            _language_manager_instance = LanguageManager()
            logger.info("[LanguageEngine] LanguageManager (Hybrid Intelligence Layer) initialized.")
        except Exception as err:
            logger.error(f"[LanguageEngine] Error initializing LanguageManager: {err}")
            _language_manager_instance = None
    return _language_manager_instance


def detect_language(text_or_audio_path: str, is_voice_turn: bool = False) -> dict:
    """Convenience proxy method for automatic language detection."""
    detector = get_language_detector()
    if detector is not None:
        return detector.detect(text_or_audio_path, is_voice_turn=is_voice_turn)
    return {"code": "en", "name": "English", "confidence": 1.0, "source": "fallback_monolinear"}
