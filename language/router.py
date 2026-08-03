"""
language/router.py
==================
Step 2: Language Routing & Conversation Preparation
Prepares conversational turns, sets target dialect context, and injects clean
multilingual prompt directives for Qwen3-8B without breaking existing history formatting.
"""

import os
import time
import logging
from typing import Dict, Any, Tuple

from language.detector import LanguageDetector

logger = logging.getLogger(__name__)


class LanguageRouter:
    """
    Orchestrates multilingual conversation states across active session turns.
    Dynamically generates prompt instructions so Vivy naturally replies in the
    exact language spoken by the user without manual reconfiguration.
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.detector = LanguageDetector(config)
        self.current_lang_code = "en"
        self.current_lang_name = "English"
        self.supported_native = self.detector.config.get(
            "supported_native_llm_languages",
            ["en", "hi", "ja", "zh", "es", "fr", "de", "ru", "or", "bn"]
        )
        self.dialect_mapping = self.detector.config.get("regional_dialect_mapping", {})
        
    def process_input_turn(self, user_text: str, input_source: str = "text") -> Dict[str, Any]:
        """
        Processes incoming user text, determines dialect, records current state,
        and constructs system prompt context instructions.
        """
        is_voice = (input_source == "voice")
        detected = self.detector.detect(user_text, is_voice_turn=is_voice)
        
        self.current_lang_code = detected.get("code", "en")
        self.current_lang_name = detected.get("name", "English")
        
        logger.info(f"[LanguageRouter] Detected input dialect: {self.current_lang_name} ({self.current_lang_code}) via {detected.get('source')}")
        
        prompt_instruction = ""
        if self.current_lang_code != "en":
            honorific = ""
            if self.current_lang_code in self.dialect_mapping:
                honorific_val = self.dialect_mapping[self.current_lang_code].get("honorific")
                if honorific_val:
                    honorific = f" You may adopt polite respectful expressions such as '{honorific_val}' where appropriate."
            
            prompt_instruction = (
                f"\n[CRITICAL MULTILINGUAL DIRECTIVE: The user is speaking in {self.current_lang_name} ({self.current_lang_code}). "
                f"You MUST respond natively and fluently in {self.current_lang_name} ({self.current_lang_code}), "
                f"matching their emotional warmth and caring tone.{honorific}]"
            )
            
        return {
            "lang_code": self.current_lang_code,
            "lang_name": self.current_lang_name,
            "prompt_hint": prompt_instruction,
            "confidence": detected.get("confidence", 1.0),
            "source": detected.get("source", "unknown")
        }

    def get_current_state(self) -> Dict[str, Any]:
        return {
            "current_language_code": self.current_lang_code,
            "current_language_name": self.current_lang_name,
            "is_native_to_llm": self.current_lang_code in self.supported_native,
            "timestamp": time.time()
        }
