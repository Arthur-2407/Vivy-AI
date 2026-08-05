"""
language/language_memory.py
============================
Extended Cross-Lingual Memory — wraps and extends CrossLingualMemoryFilter with
emotion tagging, normalized storage, and enriched retrieval across language shifts.

Existing CrossLingualMemoryFilter is NOT removed or replaced — this class
composes it internally and adds the new capabilities on top.
"""

import time
import logging
from typing import Dict, Any, List, Optional, Tuple

from language.memory_filter import CrossLingualMemoryFilter

logger = logging.getLogger(__name__)

_MAX_TURN_RECORDS = 200  # keep last N turns of normalized memory records


class LanguageMemory:
    """
    Stores per-turn language-aware memory records with:
      - original text in detected language
      - normalized English equivalent (for embedding / retrieval)
      - detected language code + name
      - emotion tag (passed in from Vivy's existing emotion classifier)
      - timestamp

    On retrieval, wraps existing CrossLingualMemoryFilter to guarantee
    cross-language memory bridging continues to work exactly as before.
    """

    def __init__(self, config: Dict[str, Any] = None):
        self._base_filter = CrossLingualMemoryFilter(config)
        self._turn_records: List[Dict[str, Any]] = []
        self._last_foreign_record: Optional[Dict[str, Any]] = None
        self._last_translation_reference: Optional[Dict[str, Any]] = None
        self._enabled: bool = True
        if config:
            self._enabled = config.get("cross_lingual_memory", True)

        # Simple static English normalizations for common non-English phrases
        # (extensible from config; not hardcoded)
        self._normalization_map: Dict[str, str] = {}
        try:
            from config.config_manager import get_config_manager
            cfg_norm = get_config_manager().get("multilingual_engine", {}).get(
                "cross_lingual_normalization_map", {}
            )
            if cfg_norm:
                self._normalization_map.update(cfg_norm)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Core record API
    # ------------------------------------------------------------------

    def record_turn(
        self,
        original_text: str,
        lang_code: str,
        lang_name: str,
        emotion: str = "neutral",
        normalized_english: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Store a memory record for a single conversation turn.
        Returns the stored record dict.
        """
        if not self._enabled or not original_text:
            return {}

        norm_eng = normalized_english or self._normalize_to_english(original_text, lang_code)
        record = {
            "timestamp": time.time(),
            "original": original_text,
            "lang_code": lang_code,
            "lang_name": lang_name,
            "normalized_english": norm_eng,
            "emotion": emotion,
        }
        self._turn_records.append(record)
        if len(self._turn_records) > _MAX_TURN_RECORDS:
            self._turn_records.pop(0)

        # Persist reference for non-English turn or turn containing non-ASCII character set (e.g., Cyrillic/CJK)
        if lang_code != "en" or any(ord(c) > 127 for c in original_text):
            self._last_foreign_record = record

        logger.debug(
            f"[LanguageMemory] Recorded turn — lang={lang_code}, emotion={emotion}, "
            f"norm='{norm_eng[:60]}...'" if len(norm_eng) > 60 else
            f"[LanguageMemory] Recorded turn — lang={lang_code}, emotion={emotion}, norm='{norm_eng}'"
        )
        return record

    def _normalize_to_english(self, text: str, lang_code: str) -> str:
        """
        Attempt lightweight normalization of non-English text to English keywords
        for memory embedding purposes. Falls back to the base filter's concept map.
        """
        if lang_code == "en":
            return text

        # Check configured normalization map first
        text_stripped = text.strip(".,!?¿?।:;\\n ")
        for phrase, eng in self._normalization_map.items():
            if phrase in text_stripped or text_stripped in phrase:
                return eng

        # Delegate to existing CrossLingualMemoryFilter concept map
        return self._base_filter.normalize_query_for_retrieval(text, detected_lang=lang_code)

    # ------------------------------------------------------------------
    # Retrieval API — proxies to existing CrossLingualMemoryFilter
    # ------------------------------------------------------------------

    def normalize_query_for_retrieval(self, raw_query: str, detected_lang: str = "en") -> str:
        """Proxy to CrossLingualMemoryFilter — preserves existing behaviour exactly."""
        return self._base_filter.normalize_query_for_retrieval(raw_query, detected_lang)

    def post_process_memories(self, retrieved_memories: List[str], target_lang: str = "en") -> List[str]:
        """Proxy to CrossLingualMemoryFilter — preserves existing behaviour exactly."""
        return self._base_filter.post_process_memories(retrieved_memories, target_lang)

    # ------------------------------------------------------------------
    # Analytics helpers
    # ------------------------------------------------------------------

    def get_recent_emotions(self, last_n: int = 5) -> List[str]:
        """Return emotion labels from the last N recorded turns."""
        return [r["emotion"] for r in self._turn_records[-last_n:]]

    def get_language_distribution(self) -> Dict[str, int]:
        """Return a count of turns per language this session."""
        dist: Dict[str, int] = {}
        for r in self._turn_records:
            dist[r["lang_code"]] = dist.get(r["lang_code"], 0) + 1
        return dist

    def get_records(self, last_n: int = 10) -> List[Dict[str, Any]]:
        """Return last N raw turn records."""
        return list(self._turn_records[-last_n:])

    def get_last_foreign_turn(self) -> Optional[Dict[str, Any]]:
        """Return the most recently recorded non-English or multilingual turn for translation reference resolution."""
        if self._last_foreign_record:
            return self._last_foreign_record
        for rec in reversed(self._turn_records):
            if rec.get("lang_code") != "en" or any(ord(c) > 127 for c in rec.get("original", "")):
                return rec
        return None

    def store_translation_reference(self, original_text: str, source_lang: str, target_lang: str) -> None:
        """Persist explicit translation interaction state across consecutive conversational turns."""
        self._last_translation_reference = {
            "timestamp": time.time(),
            "original_text": original_text,
            "source_lang": source_lang,
            "target_lang": target_lang
        }


# Module-level singleton
_instance: Optional[LanguageMemory] = None


def get_language_memory() -> LanguageMemory:
    global _instance
    if _instance is None:
        _instance = LanguageMemory()
    return _instance
