"""
language/prompt_localizer.py
==============================
Rich Multilingual Prompt Directive Builder — replaces the simple 2-line string
currently generated inside router.py with a rich, profile-aware instruction block
that gives Qwen full context about the target language, dialect style, tone,
and honorifics on every non-English turn.

router.py itself is NOT modified — this module is called by LanguageManager
and its output is used as the prompt_hint.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class PromptLocalizer:
    """
    Constructs a rich, context-aware multilingual system directive for Qwen3.

    Inputs:
      - lang_code, lang_name    (from LanguageDetector)
      - profile                 (from LanguageConfig)
      - context_hint            (from LanguageContext)
      - dialect_meta            (honorific, writing style from regional_dialect_mapping)

    Output: a structured [MULTILINGUAL DIRECTIVE] block injected into the prompt.
    """

    def __init__(self):
        self._dialect_mapping: Dict[str, Any] = {}
        self._reload()

    def _reload(self):
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            self._dialect_mapping = cfg.get("multilingual_engine", {}).get("regional_dialect_mapping", {})
        except Exception as err:
            logger.warning(f"[PromptLocalizer] Config reload warning: {err}")

    def build_directive(
        self,
        lang_code: str,
        lang_name: str,
        profile: Dict[str, Any],
        context_hint: str = "",
        is_code_switching: bool = False,
    ) -> str:
        """
        Build the full multilingual directive string.
        Returns empty string for English (no directive needed).
        """
        if lang_code == "en":
            return ""

        # Pull honorific from dialect mapping
        dialect_meta = self._dialect_mapping.get(lang_code, {})
        honorific = dialect_meta.get("honorific", "")

        # Profile details
        tone = profile.get("tone", "warm_friendly").replace("_", " ")
        formality = profile.get("formality", "casual")
        writing_style = profile.get("writing_style", "conversational")
        use_contractions = profile.get("use_contractions", False)

        lines = [
            f"[MULTILINGUAL DIRECTIVE — MANDATORY]",
            f"The user is speaking in {lang_name} ({lang_code}).",
            f"You MUST respond natively and fluently in {lang_name} ({lang_code}).",
            f"Tone: {tone}. Formality: {formality}. Writing style: {writing_style}.",
        ]

        if honorific:
            lines.append(f"Use appropriate honorifics where natural (e.g. '{honorific}').")

        if use_contractions:
            lines.append("Natural contractions are appropriate in this language.")

        if is_code_switching:
            lines.append(
                "Note: The user is mixing languages in this session — follow their lead and respond in their most recent language."
            )

        if context_hint:
            lines.append(f"Context: {context_hint}")

        lines.append(
            f"Do NOT respond in English unless the user switches back to English. "
            f"Every word of your reply must be in {lang_name}."
        )

        directive = "\n[" + "\n".join(lines) + "]"
        logger.debug(f"[PromptLocalizer] Built directive for {lang_name} ({lang_code})")
        return directive


# Module-level singleton
_instance: Optional[PromptLocalizer] = None


def get_prompt_localizer() -> PromptLocalizer:
    global _instance
    if _instance is None:
        _instance = PromptLocalizer()
    return _instance
