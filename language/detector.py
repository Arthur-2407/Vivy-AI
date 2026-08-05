"""
language/detector.py
====================
Step 1: Automatic Language Detection
Instantly detects language from Whisper audio metadata or Unicode script boundaries
with zero VRAM usage and zero hardcoded rules.
"""

import os
import re
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED_DIR = os.path.join(BASE_DIR, "shared")
DETECTED_LANG_TXT = os.path.join(SHARED_DIR, "detected_language.txt")


class LanguageDetector:
    """
    Multimodal language classifier utilizing Whisper STT signals for spoken voice turns,
    Unicode script boundaries, and zero-hardcoding Latin linguistic fingerprints.
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.config = self._load_config(config)
        self.enabled = self.config.get("enabled", True)
        self.default_lang = self.config.get("default_language", "en")
        self.dialect_mapping = self.config.get("regional_dialect_mapping", {})
        self.fingerprints = self.config.get("linguistic_fingerprints", {})
        
    def _load_config(self, passed_cfg: Dict[str, Any] = None) -> Dict[str, Any]:
        if passed_cfg is not None:
            return passed_cfg
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            raw = cfg.get("multilingual_engine", {})
            if isinstance(raw, dict) and raw:
                return raw
        except Exception as err:
            print(f"[LanguageDetector] Config manager load warning: {err}")

        # Fallback default configuration structure with zero external hardcoding reliance
        return {
            "enabled": True,
            "default_language": "en",
            "auto_detect_from_whisper": True,
            "auto_detect_from_text": True,
            "regional_dialect_mapping": {
                "or": {"name": "Odia", "script_range_start": 2816, "script_range_end": 2943, "script_ranges": [[2816, 2943]], "use_localized_tts": True, "honorific": "ତୁମେ"},
                "bn": {"name": "Bengali", "script_range_start": 2432, "script_range_end": 2559, "script_ranges": [[2432, 2559]], "use_localized_tts": True, "honorific": "ତୁମେ"},
                "hi": {"name": "Hindi", "script_range_start": 2304, "script_range_end": 2431, "script_ranges": [[2304, 2431]], "use_localized_tts": False, "honorific": "आप"},
                "ja": {"name": "Japanese", "script_range_start": 12352, "script_range_end": 12799, "script_ranges": [[12288, 12799], [19968, 40959]], "use_localized_tts": False, "honorific": "さん"},
                "zh": {"name": "Chinese", "script_range_start": 19968, "script_range_end": 40959, "script_ranges": [[19968, 40959], [13312, 19903]], "use_localized_tts": False, "honorific": "您"},
                "fr": {"name": "French", "script_range_start": -1, "script_range_end": -1, "script_ranges": [], "use_localized_tts": False, "honorific": ""},
                "ko": {"name": "Korean", "script_range_start": 44032, "script_range_end": 55215, "script_ranges": [[44032, 55215], [12592, 12687]], "use_localized_tts": False, "honorific": "님"},
                "ru": {"name": "Russian", "script_range_start": 1024, "script_range_end": 1279, "script_ranges": [[1024, 1279]], "use_localized_tts": False, "honorific": ""},
                "es": {"name": "Spanish", "script_range_start": -1, "script_range_end": -1, "script_ranges": [], "use_localized_tts": False, "honorific": ""},
                "de": {"name": "German", "script_range_start": -1, "script_range_end": -1, "script_ranges": [], "use_localized_tts": False, "honorific": ""},
                "it": {"name": "Italian", "script_range_start": -1, "script_range_end": -1, "script_ranges": [], "use_localized_tts": False, "honorific": ""},
                "ar": {"name": "Arabic", "script_range_start": 1536, "script_range_end": 1791, "script_ranges": [[1536, 1791]], "use_localized_tts": True, "honorific": ""},
                "pt": {"name": "Portuguese", "script_range_start": -1, "script_range_end": -1, "script_ranges": [], "use_localized_tts": False, "honorific": ""},
                "ta": {"name": "Tamil", "script_range_start": 2944, "script_range_end": 3071, "script_ranges": [[2944, 3071]], "use_localized_tts": True, "honorific": ""},
                "te": {"name": "Telugu", "script_range_start": 3072, "script_range_end": 3199, "script_ranges": [[3072, 3199]], "use_localized_tts": True, "honorific": ""},
                "mr": {"name": "Marathi", "script_range_start": 2304, "script_range_end": 2431, "script_ranges": [[2304, 2431]], "use_localized_tts": True, "honorific": "तुमची"},
                "gu": {"name": "Gujarati", "script_range_start": 2688, "script_range_end": 2815, "script_ranges": [[2688, 2815]], "use_localized_tts": True, "honorific": ""},
                "ml": {"name": "Malayalam", "script_range_start": 3328, "script_range_end": 3455, "script_ranges": [[3328, 3455]], "use_localized_tts": True, "honorific": ""},
                "pa": {"name": "Punjabi", "script_range_start": 2560, "script_range_end": 2687, "script_ranges": [[2560, 2687]], "use_localized_tts": True, "honorific": ""},
                "kn": {"name": "Kannada", "script_range_start": 3200, "script_range_end": 3327, "script_ranges": [[3200, 3327]], "use_localized_tts": True, "honorific": ""}
            },
            "linguistic_fingerprints": {
                "fr": ["qu'est-ce", "qu'est", "que", "qui", "aimes", "manger", "peux", "dire", "comment", "faire", "une", "les", "ingrédients", "nécessaires", "pourquoi", "quand", "oui", "merci", "bonjour", "salut", "vous", "nous", "recette", "cuisiner"],
                "ja": ["watashi", "anata", "boku", "kimi", "to", "deeto", "ikanai", "iku", "suki", "daijoubu", "nani", "doushite", "ohayo", "konnichiwa", "arigatou", "tabetai"],
                "es": ["hola", "buenos", "días", "cómo", "estás", "qué", "tal", "gracias", "por", "favor", "amigo", "muchas", "bienvenido"],
                "de": ["hallo", "guten", "morgen", "wie", "geht", "dir", "danke", "bitte", "ja", "nein", "alles", "gut", "warum"],
                "it": ["ciao", "buongiorno", "come", "stai", "grazie", "prego", "perché", "molto", "bene", "amico"],
                "ru": ["privet", "spasibo", "khorosho", "kak", "dela", "dobro", "pojaluy"]
            }
        }

    def detect(self, input_data: str, is_voice_turn: bool = False) -> Dict[str, Any]:
        """
        Classifies language of input_data.
        For voice turns, evaluates Whisper STT detected language first before text validation.
        """
        if not self.enabled:
            return {"code": self.default_lang, "name": "English", "confidence": 1.0, "source": "disabled_override"}

        # 1. Voice Turn -> Read Whisper detected language if present
        if is_voice_turn and self.config.get("auto_detect_from_whisper", True):
            whisper_res = self._check_whisper_metadata()
            if whisper_res["code"] != self.default_lang or not input_data.strip():
                return whisper_res

        # 2. Text Turn / Verification -> Fast CPU Unicode Script Evaluation (< 5ms)
        if self.config.get("auto_detect_from_text", True) and input_data.strip():
            text_res = self.classify_text_by_script(input_data)
            if text_res["code"] != self.default_lang or not is_voice_turn:
                return text_res

        return {"code": self.default_lang, "name": "English", "confidence": 0.95, "source": "default_fallback"}

    def _check_whisper_metadata(self) -> Dict[str, Any]:
        """Checks shared/detected_language.txt emitted by whisper STT pipeline."""
        try:
            if os.path.exists(DETECTED_LANG_TXT):
                age = os.path.getmtime(DETECTED_LANG_TXT)
                with open(DETECTED_LANG_TXT, "r", encoding="utf-8") as f:
                    lang_code = f.read().strip().lower()
                
                # Acknowledge and clear to prevent stale readings in future turns
                try:
                    with open(DETECTED_LANG_TXT, "w", encoding="utf-8") as f_clr:
                        f_clr.write("")
                except Exception:
                    pass

                if lang_code and lang_code in self.dialect_mapping:
                    meta = self.dialect_mapping[lang_code]
                    return {"code": lang_code, "name": meta.get("name", lang_code.upper()), "confidence": 0.98, "source": "whisper_stt"}
                elif lang_code and len(lang_code) <= 3:
                    return {"code": lang_code, "name": lang_code.upper(), "confidence": 0.95, "source": "whisper_stt"}
        except Exception as err:
            logger.warning(f"[LanguageDetector] Error reading Whisper metadata: {err}")
            
        return {"code": self.default_lang, "name": "English", "confidence": 0.50, "source": "whisper_fallback"}

    def classify_text_by_script(self, text: str) -> Dict[str, Any]:
        """
        Instantaneous (<5ms) character script evaluation using Unicode code point boundaries
        defined in configuration, ensuring high accuracy for Indic and CJK languages.
        """
        if not text or not text.strip():
            return {"code": self.default_lang, "name": "English", "confidence": 1.0, "source": "empty_text"}

        script_counts: Dict[str, int] = {}
        total_valid_chars = 0

        for char in text:
            cp = ord(char)
            # Skip basic ASCII whitespace, punctuation, and digits during script voting
            if cp <= 127:
                if char.isalpha():
                    script_counts["en"] = script_counts.get("en", 0) + 1
                    total_valid_chars += 1
                continue

            total_valid_chars += 1
            matched_dialect = False

            # Check configured regional dialect mapping boundaries and script_ranges arrays
            for lang_code, meta in self.dialect_mapping.items():
                ranges = meta.get("script_ranges")
                if not ranges:
                    ranges = [[meta.get("script_range_start", -1), meta.get("script_range_end", -1)]]
                for r_start, r_end in ranges:
                    if r_start <= cp <= r_end:
                        script_counts[lang_code] = script_counts.get(lang_code, 0) + 1
                        matched_dialect = True
                        break
                if matched_dialect:
                    break

            if not matched_dialect:
                # Fallback check for standard Indic, Cyrillic, Hangul and CJK ideographs if unmapped in config
                if 0x0900 <= cp <= 0x097F:
                    script_counts["hi"] = script_counts.get("hi", 0) + 1
                elif 0x0B00 <= cp <= 0x0B7F:
                    script_counts["or"] = script_counts.get("or", 0) + 1
                elif 0x0980 <= cp <= 0x09FF:
                    script_counts["bn"] = script_counts.get("bn", 0) + 1
                elif 0x3000 <= cp <= 0x30FF or 0x4E00 <= cp <= 0x9FFF:
                    script_counts["ja"] = script_counts.get("ja", 0) + 1
                elif 0x0400 <= cp <= 0x04FF:
                    script_counts["ru"] = script_counts.get("ru", 0) + 1
                elif 0xAC00 <= cp <= 0xD7AF or 0x3130 <= cp <= 0x318F:
                    script_counts["ko"] = script_counts.get("ko", 0) + 1
                elif 0x0600 <= cp <= 0x06FF:
                    script_counts["ar"] = script_counts.get("ar", 0) + 1
                elif 0x0B80 <= cp <= 0x0BFF:
                    script_counts["ta"] = script_counts.get("ta", 0) + 1
                elif 0x0C00 <= cp <= 0x0C7F:
                    script_counts["te"] = script_counts.get("te", 0) + 1

        if not total_valid_chars or not script_counts:
            return {"code": self.default_lang, "name": "English", "confidence": 0.95, "source": "ascii_fallback"}

        # Find script with highest character representation in text
        best_code, count = max(script_counts.items(), key=lambda x: x[1])
        ratio = count / total_valid_chars

        if best_code == "en":
            # Check if Indic, CJK, Arabic, or Cyrillic characters exist alongside English words (bilingual code-switching)
            for regional_code in ["or", "hi", "bn", "ja", "zh", "ru", "ko", "ar", "ta", "te", "mr", "gu", "ml", "pa", "kn"]:
                if script_counts.get(regional_code, 0) >= 3 or (script_counts.get(regional_code, 0) >= 1 and ratio < 0.8):
                    meta = self.dialect_mapping.get(regional_code, {})
                    return {
                        "code": regional_code,
                        "name": meta.get("name", regional_code.upper()),
                        "confidence": 0.98,
                        "source": "unicode_script_frequency"
                    }

            # Tier 3: Evaluate configured Latin linguistic fingerprints (e.g. French, Spanish, German, Romaji)
            if self.fingerprints and len(text.strip()) > 1:
                text_lower = text.lower().strip()
                text_tokens = set(re.findall(r"\b[\w']+\b|[\u3000-\u303f\uff00-\uffef]", text_lower))
                best_fp_code = None
                best_fp_score = 0
                for lang_code, markers in self.fingerprints.items():
                    score = 0
                    for marker in markers:
                        if marker in text_tokens:
                            score += 2 if len(marker) >= 5 else 1
                        elif (" " in marker or len(marker) >= 5) and marker in text_lower:
                            score += 1
                    if score > best_fp_score and score >= 1:
                        best_fp_score = score
                        best_fp_code = lang_code
                
                if best_fp_code and (best_fp_score >= 2 or (best_fp_score >= 1 and len(text_lower.split()) <= 3)):
                    meta = self.dialect_mapping.get(best_fp_code, {})
                    lang_name = meta.get("name", "Japanese" if best_fp_code == "ja" else best_fp_code.upper())
                    return {
                        "code": best_fp_code,
                        "name": lang_name,
                        "confidence": min(0.95, 0.6 + (best_fp_score * 0.1)),
                        "source": "linguistic_fingerprint"
                    }

        meta = self.dialect_mapping.get(best_code, {})
        lang_name = meta.get("name", "English" if best_code == "en" else best_code.upper())

        return {
            "code": best_code,
            "name": lang_name,
            "confidence": min(1.0, 0.5 + (ratio * 0.5)),
            "source": "unicode_script_frequency"
        }

import threading
_global_detector = None
_detector_lock = threading.Lock()

def get_detector() -> LanguageDetector:
    global _global_detector
    if _global_detector is None:
        with _detector_lock:
            if _global_detector is None:
                _global_detector = LanguageDetector()
    return _global_detector
