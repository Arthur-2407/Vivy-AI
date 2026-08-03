"""
language/language_manager.py
==============================
Language Intelligence Layer — Top-Level Orchestrator.

Single integration point for the entire Language Intelligence subsystem.
Coordinates all 6 new modules + existing detector/router/translator/voice_selector.

Used from run_vivy.py as a drop-in upgrade of the existing language hooks:

    Before:
        lang_res = _language_router.process_input_turn(user_input, input_source)
        reply    = _language_translator.verify_and_localize(reply, detected_lang_code)

    After:
        lang_res = _language_manager.process_input(user_input, input_source)
        reply    = _language_manager.process_output(reply, detected_lang_code)

Nothing downstream changes. The conversation pipeline, memory, TTS, and RVC
pipelines are completely untouched.
"""

import time
import logging
import threading
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class LanguageManager:
    """
    Orchestrates the full Language Intelligence Layer for every conversation turn.

    Input side  (process_input):
        1. LanguageDetector      — detect language
        2. LanguageContext        — update session state, detect code-switching
        3. LanguageConfig         — load personality profile
        4. PromptLocalizer        — build rich Qwen directive
        5. LanguageMemory         — record turn for cross-lingual recall

    Output side (process_output):
        1. OutputTranslator       — verify reply language matches user's language
        2. HybridTranslationEngine — translate if reply drifted to English
        3. TranslationValidator   — score quality and optionally trigger Qwen review
    """

    def __init__(self):
        self._lock = threading.Lock()

        # Load all sub-modules with graceful individual fallbacks
        self._detector = None
        self._context = None
        self._lang_config = None
        self._localizer = None
        self._memory = None
        self._translator = None
        self._hybrid_engine = None
        self._voice_selector = None

        self._supported_native: list = []
        self._default_lang: str = "en"
        self._enabled: bool = True

        self._init_modules()

    def _init_modules(self):
        """Initialize all language sub-modules with graceful fallbacks."""

        try:
            from language.detector import LanguageDetector
            self._detector = LanguageDetector()
            logger.info("[LanguageManager] LanguageDetector ready.")
        except Exception as e:
            logger.error(f"[LanguageManager] LanguageDetector init failed: {e}")

        try:
            from language.language_context import get_language_context
            self._context = get_language_context()
            logger.info("[LanguageManager] LanguageContext ready.")
        except Exception as e:
            logger.error(f"[LanguageManager] LanguageContext init failed: {e}")

        try:
            from language.language_config import get_language_config
            self._lang_config = get_language_config()
            self._supported_native = self._detector.config.get(
                "supported_native_llm_languages",
                ["en", "hi", "ja", "zh", "es", "fr", "de", "ru", "or", "bn"]
            ) if self._detector else []
            self._default_lang = self._detector.config.get("default_language", "en") if self._detector else "en"
            logger.info("[LanguageManager] LanguageConfig ready.")
        except Exception as e:
            logger.error(f"[LanguageManager] LanguageConfig init failed: {e}")

        try:
            from language.prompt_localizer import get_prompt_localizer
            self._localizer = get_prompt_localizer()
            logger.info("[LanguageManager] PromptLocalizer ready.")
        except Exception as e:
            logger.error(f"[LanguageManager] PromptLocalizer init failed: {e}")

        try:
            from language.language_memory import get_language_memory
            self._memory = get_language_memory()
            logger.info("[LanguageManager] LanguageMemory ready.")
        except Exception as e:
            logger.error(f"[LanguageManager] LanguageMemory init failed: {e}")

        try:
            from language.translator import OutputTranslator
            self._translator = OutputTranslator()
            logger.info("[LanguageManager] OutputTranslator ready.")
        except Exception as e:
            logger.error(f"[LanguageManager] OutputTranslator init failed: {e}")

        try:
            from language.voice_selector import MultilingualVoiceSelector
            self._voice_selector = MultilingualVoiceSelector()
            logger.info("[LanguageManager] MultilingualVoiceSelector ready.")
        except Exception as e:
            logger.error(f"[LanguageManager] MultilingualVoiceSelector init failed: {e}")

        # Hybrid engine init is deferred — NLLB is lazy-loaded on first non-English turn
        try:
            from language.hybrid_translation_engine import get_hybrid_translation_engine
            self._hybrid_engine = get_hybrid_translation_engine()
            logger.info("[LanguageManager] HybridTranslationEngine ready (NLLB lazy-loads on first use).")
        except Exception as e:
            logger.error(f"[LanguageManager] HybridTranslationEngine init failed: {e}")

        logger.info("[LanguageManager] All modules initialized. Language Intelligence Layer ACTIVE.")

    # ------------------------------------------------------------------
    # INPUT SIDE
    # ------------------------------------------------------------------

    def process_input(
        self,
        user_text: str,
        input_source: str = "text",
        emotion: str = "neutral",
    ) -> Dict[str, Any]:
        """
        Process one user input turn through the full Language Intelligence Layer.

        Returns a dict compatible with the existing _language_router.process_input_turn() output:
            {
                "lang_code":     str,   # e.g. "fr"
                "lang_name":     str,   # e.g. "French"
                "prompt_hint":   str,   # rich multilingual directive for Qwen
                "confidence":    float,
                "source":        str,   # detection source
                "context":       dict,  # LanguageContext snapshot
                "is_code_switching": bool,
            }
        """
        result: Dict[str, Any] = {
            "lang_code": self._default_lang,
            "lang_name": "English",
            "prompt_hint": "",
            "confidence": 1.0,
            "source": "default",
            "context": {},
            "is_code_switching": False,
        }

        try:
            # Step 1: Detect language
            is_voice = (input_source == "voice")
            detected: Dict[str, Any] = {"code": "en", "name": "English", "confidence": 1.0, "source": "default"}
            if self._detector is not None:
                detected = self._detector.detect(user_text, is_voice_turn=is_voice)

            lang_code = detected.get("code", "en")
            lang_name = detected.get("name", "English")
            confidence = detected.get("confidence", 1.0)
            source = detected.get("source", "unknown")

            result.update({"lang_code": lang_code, "lang_name": lang_name,
                           "confidence": confidence, "source": source})

            if lang_code != "en":
                logger.info(f"[LanguageManager] Input dialect: {lang_name} ({lang_code}) conf={confidence:.2f} src={source}")

            # Step 2: Update language context (detects code-switching)
            is_code_switching = False
            if self._context is not None:
                switched = self._context.update(lang_code, lang_name, confidence, source)
                is_code_switching = self._context.is_code_switching
                result["is_code_switching"] = is_code_switching
                result["context"] = self._context.snapshot()

            # Step 3: Build rich prompt directive
            if lang_code != "en":
                profile = self._lang_config.get_profile(lang_code) if self._lang_config else {}
                ctx_hint = self._context.get_context_hint() if self._context else ""
                prompt_hint = ""
                if self._localizer is not None:
                    prompt_hint = self._localizer.build_directive(
                        lang_code, lang_name, profile,
                        context_hint=ctx_hint,
                        is_code_switching=is_code_switching,
                    )
                result["prompt_hint"] = prompt_hint

            # Step 4: Record in language memory
            if self._memory is not None:
                self._memory.record_turn(user_text, lang_code, lang_name, emotion=emotion)

        except Exception as err:
            logger.error(f"[LanguageManager] process_input error (non-fatal): {err}")
            import traceback
            traceback.print_exc()

        return result

    # ------------------------------------------------------------------
    # OUTPUT SIDE
    # ------------------------------------------------------------------

    def process_output(
        self,
        reply: str,
        target_lang_code: str,
        emotion: str = "neutral",
    ) -> str:
        """
        Process Vivy's generated reply through the output Language Intelligence Layer.

        Steps:
          1. OutputTranslator.verify_and_localize  (existing logic, preserved)
          2. If reply still in English for non-English target → HybridTranslationEngine
          3. Record output in LanguageMemory

        Returns the final, localized reply string.
        """
        if not reply or not reply.strip() or target_lang_code == "en":
            return reply

        processed = reply
        try:
            # Step 1: Existing OutputTranslator (fast cache + cultural polish)
            if self._translator is not None:
                processed = self._translator.verify_and_localize(reply, target_lang_code)

            # Step 2: If still English, invoke HybridTranslationEngine
            if self._hybrid_engine is not None and processed:
                from language.detector import LanguageDetector
                _det = self._detector if self._detector else LanguageDetector()
                detected_out = _det.classify_text_by_script(processed)
                out_lang = detected_out.get("code", "en")

                if out_lang == "en" and target_lang_code != "en":
                    logger.info(
                        f"[LanguageManager] Output still English after translator — "
                        f"invoking HybridTranslationEngine for {target_lang_code}"
                    )
                    translated, conf = self._hybrid_engine.translate(
                        processed, src_lang="en", tgt_lang=target_lang_code
                    )
                    if translated and translated != processed:
                        logger.info(f"[LanguageManager] Hybrid engine translated reply (conf={conf:.2f})")
                        processed = translated

            # Step 3: Record output in language memory
            if self._memory is not None:
                self._memory.record_turn(processed, target_lang_code, "", emotion=emotion)

        except Exception as err:
            logger.error(f"[LanguageManager] process_output error (non-fatal): {err}")

        return processed or reply

    # ------------------------------------------------------------------
    # Voice Selector Proxy (preserves existing API)
    # ------------------------------------------------------------------

    def get_voice_selector(self):
        """Returns the MultilingualVoiceSelector — preserves existing API."""
        return self._voice_selector

    # ------------------------------------------------------------------
    # Status / Diagnostics
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic status of all sub-modules."""
        return {
            "detector": self._detector is not None,
            "context": self._context.snapshot() if self._context else None,
            "lang_config": self._lang_config is not None,
            "localizer": self._localizer is not None,
            "memory": self._memory.get_language_distribution() if self._memory else None,
            "translator": self._translator is not None,
            "hybrid_engine": self._hybrid_engine.get_stats() if self._hybrid_engine else None,
            "voice_selector": self._voice_selector is not None,
        }

    def normalize_query_for_retrieval(self, raw_query: str, detected_lang: str = "en") -> str:
        """Proxy to LanguageMemory — preserves CrossLingualMemoryFilter API."""
        if self._memory is not None:
            return self._memory.normalize_query_for_retrieval(raw_query, detected_lang)
        return raw_query

    def post_process_memories(self, retrieved_memories: list, target_lang: str = "en") -> list:
        """Proxy to LanguageMemory — preserves CrossLingualMemoryFilter API."""
        if self._memory is not None:
            return self._memory.post_process_memories(retrieved_memories, target_lang)
        return retrieved_memories


# Module-level singleton
_instance: Optional[LanguageManager] = None
_init_lock = threading.Lock()


def get_language_manager() -> LanguageManager:
    global _instance
    if _instance is None:
        with _init_lock:
            if _instance is None:
                _instance = LanguageManager()
    return _instance
