"""
voice/voice_router.py
=====================
Language-Aware Voice Router for Vivy AI.
Evaluates dialect compatibility across custom RVC voice identities and routes speech generation:
  - If target language is natively supported by XTTS / Coqui (en, es, fr, de, ja, zh, ru, ko):
    routes directly through primary XTTS synthesis -> RVC voice cloning.
  - If regional dialect requires localized script accuracy (Odia, Bengali, Hindi, regional variants):
    routes through system phonemic fallback -> RVC vocal identity preservation.
Ensures zero speech dropouts and acoustic continuity across global conversations.
"""

import logging
from typing import Dict, Any, Optional

from .voice_manager import get_voice_manager

logger = logging.getLogger(__name__)

class LanguageVoiceRouter:
    """Routes multilingual speech generation to optimal acoustic synthesis engines."""

    def __init__(self):
        self.mgr = get_voice_manager()
        # Dialects natively supported by multi-lingual neural TTS backends
        self.native_neural_dialects = {"en", "es", "fr", "de", "it", "pt", "pl", "tr", "ru", "nl", "cs", "ar", "zh", "hu", "ko", "ja", "hi"}

    def resolve_synthesis_strategy(self, text: str, lang_code: str = "en", voice_id: Optional[str] = None) -> dict:
        """
        Returns execution plan for synthesizing the text in the required dialect using active vocal profile.
        """
        active_voice = self.mgr.get_active_voice()
        selected_vid = voice_id or active_voice["voice_id"]
        is_supported = self.mgr.check_language_support(lang_code, selected_vid)

        strategy = {
            "lang_code": lang_code,
            "voice_id": selected_vid,
            "voice_name": active_voice.get("name", "Vivy Anime Girl"),
            "model_filename": active_voice.get("model_filename", "vivy_anime_female.pth"),
            "active_style": active_voice.get("active_style", "Professional"),
            "style_params": active_voice.get("style_parameters", {}),
            "use_neural_xtts": lang_code.lower() in self.native_neural_dialects or is_supported,
            "apply_rvc_conversion": True,
            "fallback_required": not is_supported and lang_code.lower() not in self.native_neural_dialects
        }

        logger.info(f"[LanguageVoiceRouter] Resolved strategy for language '{lang_code}' with voice '{strategy['voice_name']}': XTTS={strategy['use_neural_xtts']}, RVC={strategy['apply_rvc_conversion']}")
        return strategy

# Singleton router
_global_router = None

def get_voice_router() -> LanguageVoiceRouter:
    global _global_router
    if _global_router is None:
        _global_router = LanguageVoiceRouter()
    return _global_router
