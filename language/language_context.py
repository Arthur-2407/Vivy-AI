"""
language/language_context.py
==============================
Per-session Language State Manager — tracks language switches, code-switching
events, and maintains a rich session context object that flows through the
entire Language Intelligence Layer on every turn.
"""

import time
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

_MAX_HISTORY = 20  # maximum language switch events to keep in memory


class LanguageContext:
    """
    Maintains active language state for a Vivy conversation session.

    Attributes
    ----------
    current_lang_code   : ISO 639-1 code of the active language (e.g. "fr")
    current_lang_name   : Human-readable name (e.g. "French")
    previous_lang_code  : Language used in the prior turn
    switch_count        : Total number of language switches this session
    switch_history      : Chronological list of (timestamp, from_code, to_code)
    is_code_switching   : True when user is mixing languages in the same session
    """

    def __init__(self):
        self.current_lang_code: str = "en"
        self.current_lang_name: str = "English"
        self.previous_lang_code: str = "en"
        self.previous_lang_name: str = "English"
        self.switch_count: int = 0
        self.switch_history: List[Dict[str, Any]] = []
        self.is_code_switching: bool = False
        self.session_languages: List[str] = ["en"]
        self._last_update: float = time.time()

    def update(self, lang_code: str, lang_name: str, confidence: float = 1.0, source: str = "unknown") -> bool:
        """
        Update active language state. Returns True if a language switch occurred.
        """
        self._last_update = time.time()
        
        if lang_code == self.current_lang_code:
            return False  # No switch

        # Record the switch
        self.previous_lang_code = self.current_lang_code
        self.previous_lang_name = self.current_lang_name
        self.current_lang_code = lang_code
        self.current_lang_name = lang_name
        self.switch_count += 1

        event = {
            "timestamp": self._last_update,
            "from": self.previous_lang_code,
            "to": lang_code,
            "confidence": confidence,
            "source": source,
        }
        self.switch_history.append(event)
        if len(self.switch_history) > _MAX_HISTORY:
            self.switch_history.pop(0)

        # Track unique languages seen this session
        if lang_code not in self.session_languages:
            self.session_languages.append(lang_code)

        # Code-switching: user has used 3+ languages or switches rapidly
        self.is_code_switching = (len(self.session_languages) >= 3) or (self.switch_count >= 3)

        logger.info(
            f"[LanguageContext] Switch #{self.switch_count}: {self.previous_lang_code} → {lang_code} "
            f"(conf={confidence:.2f}, src={source}, code_switching={self.is_code_switching})"
        )
        return True

    def get_context_hint(self) -> str:
        """
        Returns a concise context string describing the current language situation,
        injected into prompts for Qwen awareness.
        """
        if self.current_lang_code == "en":
            return ""
        parts = [f"Active language: {self.current_lang_name} ({self.current_lang_code})"]
        if self.is_code_switching:
            langs_seen = ", ".join(self.session_languages)
            parts.append(f"Code-switching session — languages used: [{langs_seen}]")
        if self.previous_lang_code != self.current_lang_code:
            parts.append(f"Previous turn language: {self.previous_lang_name}")
        return " | ".join(parts)

    def snapshot(self) -> Dict[str, Any]:
        """Return a serializable snapshot of current context state."""
        return {
            "current_lang_code": self.current_lang_code,
            "current_lang_name": self.current_lang_name,
            "previous_lang_code": self.previous_lang_code,
            "switch_count": self.switch_count,
            "is_code_switching": self.is_code_switching,
            "session_languages": list(self.session_languages),
            "last_update": self._last_update,
        }


# Module-level singleton (one context per process lifetime)
_instance: Optional[LanguageContext] = None


def get_language_context() -> LanguageContext:
    global _instance
    if _instance is None:
        _instance = LanguageContext()
    return _instance
