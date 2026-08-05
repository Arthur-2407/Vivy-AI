"""
voice/__init__.py
=================
Vivy AI Voice Identity Management System & Real-Time Multilingual RVC Subsystem.
Provides a first-class voice identity lifecycle:
  Upload -> Analysis -> Training Queue -> Quality Validation -> Preview -> Approval -> Database -> Real-time Output
Without breaking existing TTS, RVC, or multilingual conversational pipelines.
"""

from .voice_manager import VoiceManager, get_voice_manager
from .voice_database import VoiceDatabase
from .voice_profiles import VoiceProfileManager
from .voice_validation import VoiceQualityAnalyzer
from .voice_preview import VoicePreviewEngine
from .voice_training import VoiceTrainingManager
from .voice_router import LanguageVoiceRouter, get_voice_router
from .voice_selector import UnifiedVoiceSelector, get_unified_voice_selector
from .voice_export import VoiceExportManager, get_voice_exporter

import os as _os
import sys as _sys
import importlib.util as _util

# [MODULE SHADOWING BRIDGE] Explicitly link root-level voice.py file so that TTS generation functions
# (generate_tts_only, speak, clean_text, speech_rate, etc.) remain directly accessible on the voice module.
_root_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_root_voice_file = _os.path.join(_root_dir, "voice.py")
if _os.path.exists(_root_voice_file):
    try:
        _spec = _util.spec_from_file_location("_root_voice_py_mod", _root_voice_file)
        if _spec and _spec.loader:
            _root_mod = _util.module_from_spec(_spec)
            _sys.modules["_root_voice_py_mod"] = _root_mod
            _spec.loader.exec_module(_root_mod)
            for _attr in dir(_root_mod):
                if not _attr.startswith("__"):
                    globals()[_attr] = getattr(_root_mod, _attr)
    except Exception as _br_err:
        import logging as _log
        _log.getLogger(__name__).warning(f"[Voice Module Bridge] Warning linking root voice.py: {_br_err}")

def __getattr__(name):
    if "_root_voice_py_mod" in _sys.modules:
        _mod = _sys.modules["_root_voice_py_mod"]
        if hasattr(_mod, name):
            return getattr(_mod, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

def __setattr__(name, value):
    if "_root_voice_py_mod" in _sys.modules:
        _mod = _sys.modules["_root_voice_py_mod"]
        if hasattr(_mod, name):
            setattr(_mod, name, value)
    globals()[name] = value

__all__ = [
    "VoiceManager",
    "get_voice_manager",
    "VoiceDatabase",
    "VoiceProfileManager",
    "VoiceQualityAnalyzer",
    "VoicePreviewEngine",
    "VoiceTrainingManager",
    "LanguageVoiceRouter",
    "get_voice_router",
    "UnifiedVoiceSelector",
    "get_unified_voice_selector",
    "VoiceExportManager",
    "get_voice_exporter",
]
if "_root_voice_py_mod" in _sys.modules:
    for _k in dir(_sys.modules["_root_voice_py_mod"]):
        if not _k.startswith("__") and _k not in __all__:
            __all__.append(_k)
