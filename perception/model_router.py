"""
perception/model_router.py
==========================
Routing layer that selects the appropriate model plugin for perception tasks
based on capability, cost, latency, availability, and configuration.
"""

import logging
from typing import Dict, Type, Any, Optional
from perception.plugins.interfaces import (
    BaseVisionPlugin,
    BaseSpeechPlugin,
    BaseOCRPlugin,
    BaseAudioAnalysisPlugin,
    BasePlugin
)

logger = logging.getLogger(__name__)

class ModelRouter:
    """
    Central router to fetch registered perception plugins.
    Reads preferences from configuration.
    """
    _plugins: Dict[str, Dict[str, Type[BasePlugin]]] = {
        "vision": {},
        "speech": {},
        "ocr": {},
        "audio_analysis": {}
    }
    
    _instances: Dict[str, BasePlugin] = {}

    @classmethod
    def register_plugin(cls, category: str, name: str, plugin_class: Type[BasePlugin]):
        """Register a plugin class under a category (vision, speech, ocr, audio_analysis)."""
        if category in cls._plugins:
            cls._plugins[category][name] = plugin_class
            logger.info(f"[ModelRouter] Registered {category} plugin: {name}")
        else:
            logger.warning(f"[ModelRouter] Invalid plugin category: {category}")

    @classmethod
    def get_plugin(cls, category: str) -> Optional[BasePlugin]:
        """
        Get the configured plugin instance for a category.
        Instantiates the plugin lazily on first access.
        """
        from perception.config_loader import get
        
        # Auto-register standard builtin plugin modules if category dictionary is unpopulated
        try:
            if not cls._plugins.get(category):
                if category == "speech": import perception.plugins.speech
                elif category == "vision": import perception.plugins.vision
                elif category == "ocr": import perception.plugins.ocr
                elif category == "audio_analysis": import perception.plugins.audio
        except Exception as _reg_err:
            logger.debug(f"[ModelRouter] Auto-import note for {category}: {_reg_err}")

        # Read preferred plugin from config
        # Default choices based on existing codebase (prioritizing in-memory CTranslate2 faster-whisper over subprocess)
        defaults = {
            "vision": "null",
            "speech": "faster_whisper",
            "ocr": "pytesseract",
            "audio_analysis": "heuristic"
        }
        
        preferred = get("model_routing", f"{category}_preferred", default=defaults.get(category))
        
        # If already instantiated and matches preference, return it
        cache_key = f"{category}:{preferred}"
        if cache_key in cls._instances:
            inst = cls._instances[cache_key]
            if inst.is_available():
                return inst
        
        # Look up plugin class
        category_plugins = cls._plugins.get(category, {})
        plugin_class = category_plugins.get(preferred)
        
        if not plugin_class or not issubclass(plugin_class, BasePlugin):
            # Fall back to default if preferred is not registered/available
            fallback = defaults.get(category)
            logger.warning(f"[ModelRouter] Configured {category} plugin '{preferred}' not found. Falling back to '{fallback}'.")
            plugin_class = category_plugins.get(fallback)
            cache_key = f"{category}:{fallback}"
            if cache_key in cls._instances:
                return cls._instances[cache_key]
        
        if plugin_class:
            try:
                # Instantiate plugin
                instance = plugin_class()
                if instance.is_available():
                    cls._instances[cache_key] = instance
                    return instance
                else:
                    logger.warning(f"[ModelRouter] Plugin {instance.name} is not available. Falling back to default.")
            except Exception as e:
                logger.error(f"[ModelRouter] Error instantiating {plugin_class.__name__}: {e}")
                
        # Hard fallback to null or first available if everything fails
        if category == "vision":
            from perception.vision_adapter import NullVisionAdapter
            return NullVisionAdapter()
            
        # For others, try to find any available plugin
        for p_name, p_class in category_plugins.items():
            try:
                inst = p_class()
                if inst.is_available():
                    cls._instances[f"{category}:{p_name}"] = inst
                    return inst
            except Exception as _err:
                print(f"[model_router.py] Silenced exception: {_err}")
                
        return None

    @classmethod
    def get_vision_plugin(cls) -> BaseVisionPlugin:
        plugin = cls.get_plugin("vision")
        assert isinstance(plugin, BaseVisionPlugin)
        return plugin

    @classmethod
    def get_speech_plugin(cls) -> Optional[BaseSpeechPlugin]:
        plugin = cls.get_plugin("speech")
        if plugin is None:
            return None
        assert isinstance(plugin, BaseSpeechPlugin)
        return plugin

    @classmethod
    def get_ocr_plugin(cls) -> Optional[BaseOCRPlugin]:
        plugin = cls.get_plugin("ocr")
        if plugin is None:
            return None
        assert isinstance(plugin, BaseOCRPlugin)
        return plugin

    @classmethod
    def get_audio_analysis_plugin(cls) -> Optional[BaseAudioAnalysisPlugin]:
        plugin = cls.get_plugin("audio_analysis")
        if plugin is None:
            return None
        assert isinstance(plugin, BaseAudioAnalysisPlugin)
        return plugin
