"""
tests/test_multilingual_pipeline.py
=====================================
Automated verification tests for Vivy Multilingual & Cross-Lingual Subsystem.
Validates language detection, routing prompts, memory translation, output localization,
and voice synthesis fallbacks across English, Hindi, Odia, Bengali, and Japanese.
"""

import os
import sys
import time
import pytest
import shutil
import tempfile

# Ensure base directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from language import get_language_router, get_language_detector, get_voice_selector, detect_language
from language.memory_filter import CrossLingualMemoryFilter
from language.translator import OutputTranslator


@pytest.fixture
def setup_test_env():
    shared_dir = os.path.join(BASE_DIR, "shared")
    os.makedirs(shared_dir, exist_ok=True)
    lang_file = os.path.join(shared_dir, "detected_language.txt")
    if os.path.exists(lang_file):
        try: os.remove(lang_file)
        except Exception: pass
    yield shared_dir
    if os.path.exists(lang_file):
        try: os.remove(lang_file)
        except Exception: pass


def test_language_detection_text(setup_test_env):
    detector = get_language_detector()
    assert detector is not None
    
    # English test
    res_en = detector.detect("Hello Vivy. How are you today?")
    assert res_en["code"] == "en"
    
    # Hindi Devanagari test
    res_hi = detector.detect("कैसी हो?")
    assert res_hi["code"] == "hi"
    assert res_hi["name"] == "Hindi"
    
    # Odia script test
    res_or = detector.detect("ତୁମେ କଣ କରୁଛ?")
    assert res_or["code"] == "or"
    assert res_or["name"] == "Odia"
    
    # Japanese test
    res_ja = detector.detect("こんにちは、元気ですか？")
    assert res_ja["code"] == "ja"


def test_language_detection_whisper_metadata(setup_test_env):
    shared_dir = setup_test_env
    detector = get_language_detector()
    
    # Simulate Whisper STT outputting Hindi code to detected_language.txt during audio voice turn
    lang_file = os.path.join(shared_dir, "detected_language.txt")
    with open(lang_file, "w", encoding="utf-8") as f:
        f.write("hi")
        
    res_voice = detector.detect("hello how are you", is_voice_turn=True)
    assert res_voice["code"] == "hi"
    assert res_voice["source"] == "whisper_stt"


def test_language_router_turn_processing():
    router = get_language_router()
    assert router is not None
    
    # Test Odia input routing
    turn_res = router.process_input_turn("ତୁମେ କଣ କରୁଛ?", input_source="text")
    assert turn_res["lang_code"] == "or"
    assert "CRITICAL MULTILINGUAL DIRECTIVE" in turn_res["prompt_hint"]
    assert "Odia" in turn_res["prompt_hint"]
    assert "ତୁମେ" in turn_res["prompt_hint"]


def test_cross_lingual_memory_filter():
    mem_filter = CrossLingualMemoryFilter()
    
    # Normalizing an Odia conceptual query to connect with stored English memories
    norm_query = mem_filter.normalize_query_for_retrieval("ମୋର ନାମ କଣ", detected_lang="or")
    assert "user name what is my name" in norm_query
    
    # Normalizing a Hindi conceptual query
    norm_hi = mem_filter.normalize_query_for_retrieval("मेरा नाम क्या है", detected_lang="hi")
    assert "user name what is my name" in norm_hi


def test_output_translator_localization():
    translator = OutputTranslator()
    
    # Verify exact user specification scenario replies
    hi_trans = translator.verify_and_localize("Hello! How are you today?", target_lang_code="hi")
    assert "मैं ठीक हूँ" in hi_trans
    
    or_trans = translator.verify_and_localize("I am talking with you.", target_lang_code="or")
    assert "ମୁଁ ତୁମ ସହ କଥା ହେଉଛି" in or_trans


def test_voice_selector_and_rvc_preservation(tmp_path):
    selector = get_voice_selector()
    assert selector is not None
    
    test_wav = os.path.join(tmp_path, "test_output.wav")
    
    # Mock fallback TTS function that simulates generating an acoustic WAV file
    def mock_tts_func(text, output_path):
        with open(output_path, "wb") as f:
            f.write(b"RIFF_MOCK_AUDIO_WAV_HEADER_DATA_" * 10)
            
    success = selector.synthesize("Hello world", test_wav, lang_code="en", fallback_tts_func=mock_tts_func)
    assert success is True
    assert os.path.exists(test_wav)
    assert os.path.getsize(test_wav) > 50


def test_japanese_kanji_and_cjk_validation():
    detector = get_language_detector()
    
    # Test user benchmark phrase with Kanji ideographs
    res_ja = detector.detect("元気かいかが")
    assert res_ja["code"] == "ja"
    assert res_ja["name"] == "Japanese"
    
    # Test word count validation in conversation module for non-whitespace scripts
    from conversation import score_response_rie, clean
    c_res = clean("私は元気ですよ！", "元気かいかが", {})
    assert c_res != "", "clean() rejected Japanese sentence due to whitespace word count limit!"
    
    s_score, is_valid = score_response_rie("私は元気ですよ！", "元気かいかが", {"long_term_facts": {}}, ["general"])
    assert s_score > 0.0, "score_response_rie() rejected Japanese sentence!"
    assert is_valid is True, f"Expected Japanese sentence to be valid, got score={s_score}, is_valid={is_valid}"


def test_latin_fingerprints_and_romaji():
    detector = get_language_detector()
    
    # Test French conversational phrases
    res_fr1 = detector.detect("qu'est-ce que tu aimes manger")
    assert res_fr1["code"] == "fr", f"Expected 'fr', got {res_fr1}"
    
    res_fr2 = detector.detect("tu peux me dire comment faire une pizza")
    assert res_fr2["code"] == "fr", f"Expected 'fr', got {res_fr2}"
    
    # Test Romaji Japanese phrase
    res_romaji = detector.detect("Watashi to deeto ni ikanai?")
    assert res_romaji["code"] == "ja", f"Expected 'ja', got {res_romaji}"


def test_multilingual_cooking_task_rie():
    from conversation import score_response_rie
    
    # Verify that a French recipe reply passes RIE validation during cooking task
    mem_cooking = {
        "active_task": "cooking",
        "task_state": {"query": "pizza", "skip_prep": False},
        "strategy_plan": {"strategy": "medium"},
        "long_term_facts": {}
    }
    score, is_valid = score_response_rie(
        "Pour une pizza, voici la recette et les ingrédients : de la farine et du fromage.",
        "dis-moi les ingrédients nécessaires",
        mem_cooking,
        ["recipe", "continuation"]
    )
    assert score > 0.0, "RIE rejected French cooking reply due to English-only food terms!"
    assert is_valid is True, f"Expected French cooking response to be valid, got score={score}, is_valid={is_valid}"


# ================================================================
# NEW TESTS — Hybrid Language Intelligence Layer (v2.0)
# ================================================================

def test_language_config_profiles():
    """Verify LanguageConfig loads profiles from config and provides safe defaults."""
    from language.language_config import get_language_config
    cfg = get_language_config()

    fr_profile = cfg.get_profile("fr")
    assert isinstance(fr_profile, dict)
    assert "tone" in fr_profile
    assert "formality" in fr_profile

    # Unknown lang → safe default
    xx_profile = cfg.get_profile("xx")
    assert isinstance(xx_profile, dict)
    assert "tone" in xx_profile

    # NLLB lang map available
    nllb_fr = cfg.get_nllb_lang_code("fr")
    assert nllb_fr == "fra_Latn", f"Expected 'fra_Latn', got {nllb_fr}"

    nllb_hi = cfg.get_nllb_lang_code("hi")
    assert nllb_hi == "hin_Deva", f"Expected 'hin_Deva', got {nllb_hi}"


def test_language_context_tracking():
    """Verify LanguageContext correctly tracks language switches and code-switching."""
    from language.language_context import LanguageContext

    ctx = LanguageContext()  # fresh instance for test isolation
    assert ctx.current_lang_code == "en"

    # Switch to French
    switched = ctx.update("fr", "French", confidence=0.9)
    assert switched is True
    assert ctx.current_lang_code == "fr"
    assert ctx.previous_lang_code == "en"
    assert ctx.switch_count == 1

    # Switch to Hindi
    ctx.update("hi", "Hindi", confidence=0.95)
    assert ctx.switch_count == 2

    # Switch to Japanese → 3 unique languages → code-switching
    ctx.update("ja", "Japanese", confidence=0.88)
    assert ctx.is_code_switching is True
    assert len(ctx.session_languages) >= 3

    # Context hint is non-empty during multilingual session
    hint = ctx.get_context_hint()
    assert "Japanese" in hint or "ja" in hint

    # Snapshot
    snap = ctx.snapshot()
    assert snap["current_lang_code"] == "ja"
    assert snap["switch_count"] == 3


def test_translation_validator_scores():
    """Verify TranslationValidator produces sensible confidence scores."""
    from language.translation_validator import get_translation_validator
    validator = get_translation_validator()

    # Empty translation → 0.0
    score, _ = validator.score("Hello", "", "en", "fr")
    assert score == 0.0

    # Source leakage (identical text) → low score
    score_leak, details = validator.score("Hello", "Hello", "en", "fr")
    assert details.get("source_leakage") is True

    # Good translation — reasonable length ratio, non-empty
    score_good, details_good = validator.score("How are you?", "Comment allez-vous?", "en", "fr")
    assert score_good > 0.4, f"Expected decent score, got {score_good}"

    # needs_qwen_review with low confidence
    assert validator.needs_qwen_review(0.5) is True
    assert validator.needs_qwen_review(0.99) is False


def test_hybrid_engine_routing_rules():
    """Verify HybridTranslationEngine routes complexity to the correct engine."""
    from language.hybrid_translation_engine import HybridTranslationEngine
    engine = HybridTranslationEngine()  # fresh instance

    # Simple text → nllb
    assert engine.classify_complexity("Hi there") in ("simple", "normal")
    assert engine.decide_engine("simple") == "nllb"

    # Code → qwen
    assert engine.classify_complexity("```python\ndef hello(): pass\n```") == "code"
    assert engine.decide_engine("code") == "qwen"

    # Emotional → nllb_then_qwen_validate
    assert engine.decide_engine("emotional") == "nllb_then_qwen_validate"

    # Creative → qwen
    assert engine.decide_engine("creative") == "qwen"


def test_language_manager_init_and_input():
    """Verify LanguageManager initializes all modules and processes input correctly."""
    from language.language_manager import get_language_manager

    mgr = get_language_manager()

    # English input → no directive
    en_res = mgr.process_input("Hello Vivy!", input_source="text")
    assert en_res["lang_code"] == "en"
    assert en_res["prompt_hint"] == ""

    # French input → French lang code + non-empty directive
    fr_res = mgr.process_input("qu'est-ce que tu aimes manger", input_source="text")
    assert fr_res["lang_code"] == "fr", f"Expected 'fr', got {fr_res}"
    assert "MULTILINGUAL" in fr_res.get("prompt_hint", ""), "Expected rich multilingual directive"
    assert "French" in fr_res.get("prompt_hint", "")

    # Hindi input → Hindi lang code
    hi_res = mgr.process_input("कैसी हो?", input_source="text")
    assert hi_res["lang_code"] == "hi"

    # Status check
    status = mgr.get_status()
    assert status["detector"] is True
    assert status["translator"] is True


def test_adaptive_nllb_load_switching():
    """Verify HybridTranslationEngine inspects system resources and dynamically adapts NLLB CPU/CUDA execution."""
    from language.hybrid_translation_engine import HybridTranslationEngine
    engine = HybridTranslationEngine()

    # Verify resource inspection returns valid device decision without throwing errors or hardcoding
    target_device, compute_type, stats = engine._inspect_system_resources()
    assert target_device in ("cpu", "cuda"), f"Unexpected device target: {target_device}"
    assert isinstance(compute_type, str)
    assert stats["mode"] == "hybrid", f"Expected mode hybrid, got {stats.get('mode')}"

    # Ensure NLLB loads cleanly from local converted CTranslate2 path on the selected device
    loaded = engine._ensure_nllb_loaded()
    assert loaded is True, "Expected NLLB-200 to load successfully from converted CT2 directory."
    stats_post = engine.get_stats()
    assert stats_post["nllb_loaded"] is True
    assert stats_post["current_device"] in ("cpu", "cuda")

    # Perform sample real translation using NLLB on adapted device
    translated, conf = engine.translate("Thank you very much.", "en", "hi", force_engine="nllb")
    assert translated != "" and translated != "Thank you very much.", f"Translation failed: {translated}"
    assert conf > 0.0


def test_korean_romaji_and_conversational_favors_upgrade():
    """Verify Korean Romaji ('Gomawo') detection, polyglot competence rules, and natural conversational favors."""
    from language import get_language_detector
    from language.prompt_localizer import get_prompt_localizer
    from conversation import get_relational_dialogue_exemplars
    import time

    # 1. Verify Korean Romaji detection without hardcoding
    detector = get_language_detector()
    assert detector.default_lang == "en", "Default language must remain set to English"
    ko_res = detector.detect("Gomawo")
    assert ko_res["code"] == "ko", f"Expected 'ko', got {ko_res}"
    assert ko_res["name"] == "Korean"

    # 2. Verify Polyglot Competence directive prevents language hallucination
    loc = get_prompt_localizer()
    directive = loc.build_directive("ko", "Korean", {"tone": "warm_friendly", "formality": "casual", "writing_style": "concise"})
    assert "Polyglot Competence Rule" in directive
    assert "universal polyglot AI companion" in directive

    # 3. Verify everyday playful favors (e.g. 'can u make coffee for me') return warm human exemplars
    guidance, candidates = get_relational_dialogue_exemplars("can u make coffee for me", {"last_user_time": time.time()}, score=65.0)
    assert "playfully asking for an everyday companion favor" in guidance
    assert len(candidates) > 0
    assert not any("Somehow you always know how to get my attention" in c for c in candidates)
    assert any("reach out" in c or "virtual cup" in c for c in candidates)
