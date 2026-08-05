"""
language/reference_resolver.py
==============================
Multilingual Reference & Translation Context Resolver for Vivy AI.
Handles reference resolution for expressions like "can you translate this",
"what u said me can u translate it for me", and "what u told me in Russian can u translate that for me".

Interoperates seamlessly with LanguageMemory and HybridTranslationEngine to resolve
anaphoric references across languages without relying on hardcoded replies or causing LLM fallbacks.
"""

import re
import time
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Dynamic regex patterns for detecting explicit translation reference queries
_TRANSLATION_REQUEST_PATTERNS = [
    r"\b(can|could|would|please|will)?\s*(you|u)?\s*translate\s+(this|that|it|what\s+(you|u)\s+(said|told|wrote)|my\s+last\s+(message|word)|your\s+last\s+(message|word|reply)|for\s+(me|mr|us))\b",
    r"\btranslate\s*(it|this|that)?\s*(for|to)\s*(me|mr|english|russian|french|german|spanish|hindi|japanese|chinese|odia|bengali)\b",
    r"\bwhat\s+(you|u)\s+(said|told|wrote)\s+.*translate\b",
    r"\bwhat\s+(did|does|would)\s+.*(mean|say)\b",
    r"\b(give\s+me|show\s+me)?\s*(the\s+)?translation\s*(in|to|of)?\b"
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _TRANSLATION_REQUEST_PATTERNS]

class MultilingualReferenceResolver:
    """
    Resolves conversational translation references by tracking previous foreign-language turns
    and dynamically linking user commands to targeted translations.
    """

    def __init__(self):
        self._language_map = {
            "english": ("en", "English"),
            "russian": ("ru", "Russian"),
            "hindi": ("hi", "Hindi"),
            "japanese": ("ja", "Japanese"),
            "chinese": ("zh", "Chinese"),
            "spanish": ("es", "Spanish"),
            "french": ("fr", "French"),
            "german": ("de", "German"),
            "odia": ("or", "Odia"),
            "bengali": ("bn", "Bengali"),
        }
        logger.info("[MultilingualReferenceResolver] Ready.")

    def is_translation_reference_query(self, user_text: str) -> bool:
        """
        Determines if the user's input is an explicit request to translate a referenced message.
        """
        if not user_text or len(user_text.strip()) < 3:
            return False
        text_clean = user_text.strip().lower()
        # Direct word checks to quickly pass non-translation chat
        if not any(w in text_clean for w in ["translate", "translation", "mean", "meaning", "say in", "saying"]):
            return False
        for pat in _COMPILED_PATTERNS:
            if pat.search(text_clean):
                return True
        if any(p in text_clean for p in ["mean in english", "what did that mean", "what does that mean", "can u translate", "can you translate", "translate that", "translate this"]):
            return True
        if text_clean.startswith("translate"):
            return True
        return False

    def extract_requested_target_language(self, user_text: str, fallback_lang_code: str = "en") -> Tuple[str, str]:
        """
        Extracts the target language from expressions like "to english", "in english", "translate it for me".
        Carefully identifies whether a language mentioned (like 'in Russian') refers to the source text rather than target.
        """
        u_clean = user_text.lower()
        
        # 1. Check if user explicitly used directional prepositions indicating target language ("to X" or "into X")
        for name, (code, label) in self._language_map.items():
            if f"to {name}" in u_clean or f"into {name}" in u_clean:
                return code, label

        # 2. Check if the language is mentioned as the source language (e.g. "what u told me in russian", "what you said in russian")
        source_lang_detected = None
        for name, (code, label) in self._language_map.items():
            if f"in {name}" in u_clean:
                if any(src_p in u_clean for src_p in [f"told me in {name}", f"said in {name}", f"wrote in {name}", f"message in {name}", f"you in {name}", f"u in {name}"]):
                    source_lang_detected = code
                elif not source_lang_detected:
                    return code, label

        # If source language was explicitly detected (like Russian) and query is asking to translate for the user in English
        if source_lang_detected and source_lang_detected != "en":
            return "en", "English"

        # If user didn't specify target language, default target is fallback or English
        for n, (c, l) in self._language_map.items():
            if c == fallback_lang_code:
                return c, l
        return "en", "English"

    def resolve_and_translate(
        self,
        user_text: str,
        history: List[str],
        mem: Dict[str, Any],
        language_memory: Any = None
    ) -> Optional[str]:
        """
        Resolves the reference ("this", "what you said in Russian", etc.) from conversation history or LanguageMemory,
        invokes HybridTranslationEngine, and returns a natural companion response.
        Returns None if resolution cannot find suitable text to translate.
        """
        if not self.is_translation_reference_query(user_text):
            return None

        target_lang_code, target_lang_label = self.extract_requested_target_language(user_text, fallback_lang_code="en")
        
        # Candidate text to translate and its assumed source language code
        target_text = ""
        source_lang_code = "auto"

        # 1. Check LanguageMemory for recent non-English turns or last foreign turn
        if language_memory is not None:
            try:
                if hasattr(language_memory, "get_last_foreign_turn"):
                    foreign_turn = language_memory.get_last_foreign_turn()
                    if foreign_turn and foreign_turn.get("original"):
                        target_text = foreign_turn["original"].strip()
                        source_lang_code = foreign_turn.get("lang_code", "auto")
                elif hasattr(language_memory, "get_records"):
                    records = language_memory.get_records(last_n=10)
                    for rec in reversed(records):
                        # Find the most recent non-English turn or turn in another dialect
                        if rec.get("lang_code") != "en" and rec.get("original"):
                            target_text = rec["original"].strip()
                            source_lang_code = rec.get("lang_code", "auto")
                            break
            except Exception as e:
                logger.warning(f"[MultilingualReferenceResolver] LanguageMemory check failed: {e}")

        # 2. Check visible conversation history if LanguageMemory yielded nothing
        if not target_text and history:
            # Check last 6 turns in reverse order for non-English script or content
            for turn in reversed(history[-10:]):
                if not isinstance(turn, str):
                    continue
                line_text = turn.split(": ", 1)[-1].strip() if ": " in turn else turn.strip()
                # Skip multilingual directive meta-text or user's current translation request
                if "[MULTILINGUAL DIRECTIVE" in line_text or "can u translate" in line_text.lower() or "translate" in line_text.lower():
                    continue
                # If the user explicitly mentioned a language (like Russian) in their query, search for Cyrillic / non-Latin characters
                if "russian" in user_text.lower() or any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in line_text):
                    if any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in line_text):
                        target_text = line_text
                        source_lang_code = "ru"
                        break
                # Or check any general non-ASCII script (Cyrillic, Devanagari, Kanji, CJK, etc.)
                if any(ord(c) > 127 for c in line_text) and len(line_text) > 3:
                    target_text = line_text
                    break
            # If still nothing, simply take Vivy's last message or User's message prior to the translation command
            if not target_text:
                for turn in reversed(history[-6:]):
                    if isinstance(turn, str) and (turn.startswith("Vivy:") or turn.startswith("Assistant:")):
                        clean_turn = turn.split(": ", 1)[-1].strip()
                        if not any(w in clean_turn.lower() for w in ["enjoying our conversation", "appreciate you sharing", "right here with you", "tell me a little more"]):
                            target_text = clean_turn
                            break

        if not target_text:
            logger.info("[MultilingualReferenceResolver] No suitable reference message found to translate.")
            return None

        # Clean target text of quotes or extraneous prefixes
        target_text = target_text.strip('\"\'')
        
        # Invoke HybridTranslationEngine
        translated_text = ""
        try:
            from language.hybrid_translation_engine import get_hybrid_translation_engine
            engine = get_hybrid_translation_engine()
            translated_text, conf = engine.translate(
                target_text,
                src_lang=source_lang_code if source_lang_code != "auto" else "en",
                tgt_lang=target_lang_code
            )
            logger.info(f"[MultilingualReferenceResolver] Translated '{target_text[:30]}...' -> '{translated_text[:30]}...' (conf={conf:.2f})")
        except Exception as err:
            logger.error(f"[MultilingualReferenceResolver] Hybrid engine translation failed: {err}")

        # Fallback to direct Qwen / local LLM translation if Hybrid engine failed or returned empty
        if not translated_text or translated_text == target_text:
            try:
                from models.llm_engine import llm
                prompt = (
                    "<|im_start|>system\n"
                    f"You are Vivy AI, a bilingual expert companion. Translate the exact text below into natural, fluent {target_lang_label}.\n"
                    "Do NOT explain or add introductory commentary. Return ONLY the translation.<|im_end|>\n"
                    f"<|im_start|>user\nTranslate to {target_lang_label}: \"{target_text}\"<|im_end|>\n"
                    "<|im_start|>assistant\n"
                )
                out = llm(prompt, max_tokens=300, temperature=0.2, stop=["<|im_end|>", "\n\n"])
                translated_text = out["choices"][0]["text"].strip().strip('\"\'')
            except Exception as _e:
                logger.error(f"[MultilingualReferenceResolver] LLM fallback translation failed: {_e}")

        if not translated_text:
            return f"I wanted to translate that for you, but I encountered a momentary glitch in my language engine. Here is the message I was referring to: \"{target_text}\""

        # Format natural companion response
        if source_lang_code == "ru" or any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in target_text):
            return f"Here is the translation of what I said: \"{translated_text}\" 😊"
        else:
            return f"Here is the translation: \"{translated_text}\""

# Module singleton
_resolver_instance: Optional[MultilingualReferenceResolver] = None

def get_reference_resolver() -> MultilingualReferenceResolver:
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = MultilingualReferenceResolver()
    return _resolver_instance
