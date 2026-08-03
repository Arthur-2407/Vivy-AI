"""
language/language_config.py
============================
Language Profile Registry — reads per-language personality, tone, and formality
profiles from vivy_config.json so Vivy adapts her warmth and writing style
automatically for every supported dialect.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_PROFILE = {
    "tone": "warm_friendly",
    "formality": "casual",
    "writing_style": "conversational",
    "use_contractions": True
}


class LanguageConfig:
    """
    Reads language personality profiles from the centralized ConfigManager and
    exposes them via get_profile(lang_code). Falls back gracefully if the config
    section is missing or the language is not defined.
    """

    def __init__(self):
        self._profiles: Dict[str, Dict[str, Any]] = {}
        self._nllb_cfg: Dict[str, Any] = {}
        self._hybrid_cfg: Dict[str, Any] = {}
        self._cache_cfg: Dict[str, Any] = {}
        self._reload()

    def _reload(self):
        """Load / hot-reload all language-related config sections from ConfigManager."""
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            eng = cfg.get("multilingual_engine", {})
            self._profiles = eng.get("language_profiles", {})
            self._nllb_cfg = eng.get("nllb_model", {})
            self._hybrid_cfg = eng.get("hybrid_translation", {})
            self._cache_cfg = eng.get("translation_cache", {})
        except Exception as err:
            logger.warning(f"[LanguageConfig] Config load warning: {err}")

    def get_profile(self, lang_code: str) -> Dict[str, Any]:
        """Return the language personality profile for lang_code, with safe defaults."""
        return dict(self._profiles.get(lang_code, _DEFAULT_PROFILE))

    def get_nllb_config(self) -> Dict[str, Any]:
        """Return NLLB model configuration."""
        return dict(self._nllb_cfg)

    def get_hybrid_config(self) -> Dict[str, Any]:
        """Return hybrid translation engine rules."""
        return dict(self._hybrid_cfg)

    def get_cache_config(self) -> Dict[str, Any]:
        """Return translation cache configuration."""
        return dict(self._cache_cfg)

    def get_nllb_lang_code(self, lang_code: str) -> Optional[str]:
        """Map a 2-letter ISO lang code to an NLLB BCP-47 flores200 code."""
        return self._nllb_cfg.get("nllb_lang_map", {}).get(lang_code)


# Module-level singleton
_instance: Optional[LanguageConfig] = None


def get_language_config() -> LanguageConfig:
    global _instance
    if _instance is None:
        _instance = LanguageConfig()
    return _instance
