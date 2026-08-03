"""
language/translation_validator.py
===================================
Translation Quality & Confidence Scorer — evaluates NLLB output quality
before deciding whether to pass it directly or escalate to Qwen for review.

Zero VRAM. Zero external API calls. Pure heuristics + script analysis (<1ms).
"""

import re
import logging
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)


class TranslationValidator:
    """
    Evaluates the quality of a translation produced by NLLB (or any other engine)
    and returns a confidence score in [0.0, 1.0].

    Scoring criteria (all configurable via thresholds):
      1. Script consistency  — output script matches expected target script
      2. Length ratio        — translation is not absurdly longer/shorter than source
      3. Non-empty           — output is not blank or whitespace
      4. No source leakage   — output does not just echo the source unchanged
      5. Punctuation health  — basic punctuation preservation check
    """

    def __init__(self, config: Dict[str, Any] = None):
        # Load thresholds from config or use safe defaults
        hybrid_cfg = {}
        try:
            from config.config_manager import get_config_manager
            hybrid_cfg = get_config_manager().get("multilingual_engine", {}).get("hybrid_translation", {})
        except Exception:
            pass

        self._confidence_threshold: float = hybrid_cfg.get("confidence_threshold", 0.82)
        self._min_length_ratio: float = 0.20   # translation must be ≥20% length of source
        self._max_length_ratio: float = 5.0    # translation must be ≤500% length of source

        # Script Unicode ranges to verify output script matches target language
        # Loaded from config regional_dialect_mapping
        self._script_ranges: Dict[str, list] = {}
        try:
            from config.config_manager import get_config_manager
            dialect_map = get_config_manager().get("multilingual_engine", {}).get("regional_dialect_mapping", {})
            for lang, meta in dialect_map.items():
                ranges = meta.get("script_ranges", [])
                if ranges:
                    self._script_ranges[lang] = ranges
        except Exception:
            pass

    def score(
        self,
        source_text: str,
        translation: str,
        src_lang: str,
        tgt_lang: str,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Score a translation. Returns (confidence: float, details: dict).
        confidence in [0.0, 1.0].  details explains each sub-score.
        """
        details: Dict[str, Any] = {}
        scores = []

        # 1. Non-empty check
        if not translation or not translation.strip():
            return 0.0, {"fail": "empty_translation"}
        details["non_empty"] = True
        scores.append(1.0)

        # 2. Source leakage check (translation == source → no real translation happened)
        src_stripped = source_text.strip().lower()
        tgt_stripped = translation.strip().lower()
        if src_stripped == tgt_stripped and src_lang != tgt_lang:
            details["source_leakage"] = True
            scores.append(0.0)
        else:
            details["source_leakage"] = False
            scores.append(1.0)

        # 3. Length ratio check
        src_len = max(len(source_text.strip()), 1)
        tgt_len = len(translation.strip())
        ratio = tgt_len / src_len
        if self._min_length_ratio <= ratio <= self._max_length_ratio:
            len_score = 1.0
        else:
            len_score = max(0.0, 1.0 - abs(ratio - 1.0) * 0.5)
        details["length_ratio"] = round(ratio, 2)
        scores.append(len_score)

        # 4. Script consistency check (only for non-Latin target languages)
        script_score = self._check_script_consistency(translation, tgt_lang)
        details["script_score"] = round(script_score, 2)
        scores.append(script_score)

        # 5. Punctuation health (source has sentence-ending punctuation → so should translation)
        src_has_punct = bool(re.search(r'[.!?。！？।]', source_text))
        tgt_has_punct = bool(re.search(r'[.!?。！？।]', translation))
        punct_score = 1.0 if (src_has_punct == tgt_has_punct) else 0.85
        details["punctuation_health"] = punct_score
        scores.append(punct_score)

        # Weighted average (script consistency weighted more heavily)
        weights = [0.15, 0.25, 0.20, 0.30, 0.10]
        confidence = sum(s * w for s, w in zip(scores, weights))
        details["confidence"] = round(confidence, 3)

        logger.debug(
            f"[TranslationValidator] {src_lang}→{tgt_lang} conf={confidence:.3f} | {details}"
        )
        return confidence, details

    def _check_script_consistency(self, text: str, tgt_lang: str) -> float:
        """
        Returns 1.0 if the translation contains characters from the expected
        target script. Returns 0.7 for Latin-target languages (no script check needed).
        Returns 0.5 if non-Latin script is expected but not found.
        """
        ranges = self._script_ranges.get(tgt_lang)
        if not ranges:
            # Latin-script target or unknown — skip script check
            return 0.9

        # Count characters in expected script ranges
        in_range = 0
        total_non_ascii = 0
        for ch in text:
            cp = ord(ch)
            if cp > 127:
                total_non_ascii += 1
                if any(r[0] <= cp <= r[1] for r in ranges):
                    in_range += 1

        if total_non_ascii == 0:
            # No non-ASCII at all in a non-Latin target → suspicious
            return 0.4
        ratio = in_range / total_non_ascii
        return min(1.0, 0.5 + ratio * 0.5)

    @property
    def confidence_threshold(self) -> float:
        return self._confidence_threshold

    def needs_qwen_review(self, confidence: float) -> bool:
        """Returns True if confidence is below the configured threshold."""
        return confidence < self._confidence_threshold


# Module-level singleton
_instance = None


def get_translation_validator() -> TranslationValidator:
    global _instance
    if _instance is None:
        _instance = TranslationValidator()
    return _instance
