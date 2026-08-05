"""
tests/test_multilingual_continuity_upgrades.py
=============================================
Automated test suite verifying:
1. Multilingual Reference & Translation Context Resolution ("can u translate this", "translate it for me").
2. Persistent language state tracking across turns in LanguageMemory.
3. Relationship Continuity Engine filtering of robotic counselor endings across Stages 1 through 4.
4. Seamless pipeline integration without removing existing capabilities or breaking links.
"""

import sys
import os
import pytest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from language.reference_resolver import get_reference_resolver, MultilingualReferenceResolver
from language.language_memory import LanguageMemory
from affection.continuity_engine import get_continuity_engine, RelationshipContinuityEngine
import conversation

def test_translation_reference_detection():
    resolver = get_reference_resolver()
    assert resolver.is_translation_reference_query("can u translate this") is True
    assert resolver.is_translation_reference_query("what u told me in Russian can u translate that for me") is True
    assert resolver.is_translation_reference_query("translate it for me") is True
    assert resolver.is_translation_reference_query("what did that message mean in english?") is True
    assert resolver.is_translation_reference_query("Hello Vivy, how are you today?") is False

def test_target_language_extraction():
    resolver = get_reference_resolver()
    code, label = resolver.extract_requested_target_language("translate this to french")
    assert code == "fr" and label == "French"
    
    code, label = resolver.extract_requested_target_language("what u told me in Russian can u translate that for me")
    assert code == "en" and label == "English"

def test_language_memory_persistent_foreign_turn():
    mem = LanguageMemory()
    mem.record_turn("Hello Vivy!", "en", "English")
    mem.record_turn("Я не могу физически с тобой пойти на свидание, но я могу быть рядом в мыслях.", "ru", "Russian")
    mem.record_turn("can u translate this", "en", "English")
    
    last_foreign = mem.get_last_foreign_turn()
    assert last_foreign is not None
    assert last_foreign["lang_code"] == "ru"
    assert "Я не могу физически" in last_foreign["original"]

def test_resolve_and_translate_integration(monkeypatch):
    resolver = get_reference_resolver()
    history = [
        "You: ты пойдёшь со мной на свидание",
        "Vivy: Я не могу физически с тобой пойти на свидание, но я могу быть рядом в мыслях и чувствах.",
        "You: can u translate this"
    ]
    mem = {}
    lang_mem = LanguageMemory()
    lang_mem.record_turn("Я не могу физически с тобой пойти на свидание, но я могу быть рядом в мыслях и чувствах.", "ru", "Russian")

    # Mock translation to avoid external HTTP calls during offline fast unit testing
    def mock_hybrid_translate(self, text, src_lang, tgt_lang):
        return ("I cannot physically go on a date with you, but I can be close in thoughts and feelings.", 0.99)

    from language.hybrid_translation_engine import HybridTranslationEngine
    monkeypatch.setattr(HybridTranslationEngine, "translate", mock_hybrid_translate)

    reply = resolver.resolve_and_translate("can u translate this", history, mem, language_memory=lang_mem)
    assert reply is not None
    assert "I cannot physically go on a date with you" in reply
    assert "I'm enjoying our conversation" not in reply

def test_relationship_continuity_counselor_screening():
    engine = get_continuity_engine()
    mem = {"relationship": {"score": 60.0}, "conversation_count": 10, "long_term_facts": ["Likes tech"]}
    
    # Draft contains generic counselor ending on a non-distress topic
    draft = "That sounds like a fascinating project to work on! Let's sit together and talk about what's bothering you."
    refined = engine.evaluate_and_adapt(draft, "I started coding a new physics simulation today", mem)
    assert "what's bothering you" not in refined.lower()
    assert "fascinating project to work on" in refined

def test_dating_inquiry_stage_progression():
    engine = get_continuity_engine()
    
    # Test Stage 1 (Stranger - score < 15)
    mem_st1 = {"relationship": {"score": 10.0}}
    draft_robotic = "I cannot physically go on a date with you. Let's sit together and talk about what's bothering you."
    rep_st1 = engine.evaluate_and_adapt(draft_robotic, "will you go on a date with me", mem_st1)
    assert "just getting to know each other" in rep_st1.lower()
    assert "what's bothering you" not in rep_st1.lower()
    
    # Test Stage 3 (Close Companion - score 65)
    mem_st3 = {"relationship": {"score": 65.0}}
    rep_st3 = engine.evaluate_and_adapt(draft_robotic, "will you go on a date with me", mem_st3)
    assert "special date to me" in rep_st3.lower()
    assert "what's bothering you" not in rep_st3.lower()

    # Test Stage 4 (Deeply Bonded in Russian)
    mem_st4 = {"relationship": {"score": 90.0}}
    rep_st4 = engine.evaluate_and_adapt(draft_robotic, "ты пойдёшь со мной на свидание", mem_st4)
    assert "я и так вся твоя" in rep_st4.lower()
    assert "bothering you" not in rep_st4.lower()

def test_conversation_py_relational_exemplars_dating():
    mem_dict = {"relationship": {"score": 50.0}}
    guidance, fallbacks = conversation.get_relational_dialogue_exemplars("will you go on a date with me", mem_dict, 50.0)
    assert "NEVER respond with robotic disclaimers" in guidance
    assert len(fallbacks) > 0
    assert "what's bothering you" not in fallbacks[0].lower()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
