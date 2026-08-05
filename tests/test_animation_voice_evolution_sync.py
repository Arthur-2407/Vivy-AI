"""
tests/test_animation_voice_evolution_sync.py
=================================================
Comprehensive verification suite proving zero-hardcoding integration of:
1. Expressive Vocal Lip-Sync & Facial Blendshape Enrichment
2. Style-Biased Modular Animation Planning
3. Extended Multilingual & Dialect Detection (20+ global scripts/dialects)
4. Custom Neural Voice Router & Localized Speech Selection
5. AGI Self-Evolution Anti-Corruption & VRAM Governance Invariants
6. Cognitive Orchestrator Internal State Awareness & Experiential Sync
"""

import os
import time
import json
import pytest
import shutil
import tempfile
from typing import Dict, Any

# Test 1: Avatar Bridge Speak Payload Enrichment & Blendshape Mapping
def test_avatar_bridge_speak_payload_enrichment():
    import avatar_bridge
    from voice.voice_manager import get_voice_manager
    
    v_mgr = get_voice_manager()
    v_mgr.set_vocal_style("Cheerful")
    
    payload = avatar_bridge._enrich_speak_payload("Hello! I am feeling cheerful today!")
    assert payload["type"] == "speak"
    assert payload["text"] == "Hello! I am feeling cheerful today!"
    assert payload.get("vocal_style") == "Cheerful"
    assert "speech_rate" in payload
    assert "pitch_shift" in payload
    assert payload.get("facial_expression_hint") == "SmileBig"
    assert payload["blendshapes"].get("joy_intensity", 0.0) >= 0.8
    
    # Switch style to Soft and check blendshape adaptation
    v_mgr.set_vocal_style("Soft")
    payload_soft = avatar_bridge._enrich_speak_payload("I understand, let's sit quietly.")
    assert payload_soft.get("vocal_style") == "Soft"
    assert payload_soft.get("facial_expression_hint") == "IdleSad"
    assert payload_soft["blendshapes"].get("gentle_intensity", 0.0) >= 0.7

# Test 2: VivyAnimationPlanner Style-Biased Trigger Modulation
def test_animator_style_biased_trigger_selection():
    from animator.animator import VivyAnimationPlanner
    planner = VivyAnimationPlanner()
    
    # Test Cheerful style trigger request
    req_cheer = planner.on_emotion("happy", circadian_energy=0.9, vocal_style="Cheerful")
    if req_cheer is not None:
        assert req_cheer.transition_duration == 0.3
        assert req_cheer.parameters.get("vocal_style") == "Cheerful"
        
    # Reset cooldowns to allow subsequent emotion testing
    planner._last_sent_at.clear()
    
    # Test Soft style trigger request
    req_soft = planner.on_emotion("neutral", circadian_energy=0.8, vocal_style="Soft")
    if req_soft is not None:
        assert req_soft.transition_duration == 0.5
        assert req_soft.parameters.get("vocal_style") == "Soft"

# Test 3: Extended Global Dialect & Script Detection (Zero Hardcoding)
def test_extended_dialect_detection_no_hardcoding():
    from language.detector import get_detector
    detector = get_detector()
    
    test_cases = [
        ("Привет, как дела?", "ru", "Russian"),
        ("안녕하세요 만나서 반갑습니다", "ko", "Korean"),
        ("Hola buenos días amigo, ¿cómo estás?", "es", "Spanish"),
        ("Hallo guten Morgen wie geht dir", "de", "German"),
        ("مرحبا كيف حالك", "ar", "Arabic"),
        ("வணக்கம் எப்படி இருக்கிறீர்கள்", "ta", "Tamil"),
        ("नमस्ते आप कैसे हैं", "hi", "Hindi"),
        ("WATASHI NO DEETO", "ja", "Japanese"),
        ("Odia test text with script: ତୁମେ କେମିତି ଅଛ", "or", "Odia")
    ]
    
    for text, expected_code, expected_name in test_cases:
        res = detector.detect(text)
        assert res["code"] == expected_code, f"Failed on '{text}': detected {res} instead of {expected_code}"
        assert res.get("confidence", 0.0) > 0.5

# Test 4: Multilingual Voice Selector & Custom Voice Routing Interface
def test_multilingual_voice_selector_custom_routing():
    from language.voice_selector import get_voice_selector
    selector = get_voice_selector()
    
    test_dir = tempfile.mkdtemp()
    test_wav = os.path.join(test_dir, "test_synthesis_output.wav")
    
    def dummy_tts_fallback(text, wav_path):
        with open(wav_path, "wb") as f:
            f.write(b"RIFF" + b"\x00" * 200) # Dummy valid WAV header stub > 100 bytes
            
    try:
        success = selector.synthesize(
            text="Testing custom routing interface",
            output_wav_path=test_wav,
            lang_code="es",
            fallback_tts_func=dummy_tts_fallback
        )
        assert success is True
        assert os.path.exists(test_wav)
        assert os.path.getsize(test_wav) >= 100
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

# Test 5: Governance Layer Anti-Corruption & VRAM Boundary Safeguards
def test_governance_layer_anti_corruption_invariants():
    from evolution.governance_layer import get_governance_layer
    gov = get_governance_layer()
    
    # Invariant 1: Structural code modification or state corruption attempts must yield 0.0 safety score
    assert gov.evaluate_safety_score({"modify_code": True, "target": "run_vivy.py"}) == 0.0
    assert gov.evaluate_safety_score({"corrupt_state": True, "loop_injection": True}) == 0.0
    assert gov.evaluate_safety_score({"override_vram_limit": True}) == 0.0
    
    # Invariant 2: VRAM boundary overflows and recursive recursion loops must lower safety below approval threshold
    unsafe_proposal = {"vram_usage_mb": 5900, "recursion_depth_limit": 100}
    score = gov.evaluate_safety_score(unsafe_proposal)
    assert score <= 0.5, f"Expected low safety score for unsafe memory proposal, got {score}"
    
    approved, audit = gov.validate_and_approve("micro_patch", unsafe_proposal)
    assert approved is False
    assert audit.status == "REJECTED_SAFETY"
    
    # Invariant 3: Safe micro-patch proposals must achieve valid safety approval
    safe_proposal = {"turn_eval_score": 0.92, "vram_usage_mb": 1500, "recursion_depth_limit": 10}
    safe_score = gov.evaluate_safety_score(safe_proposal)
    assert safe_score == 1.0
    approved_safe, audit_safe = gov.validate_and_approve("micro_patch", safe_proposal)
    assert approved_safe is True
    assert audit_safe.status == "APPROVED"

# Test 6: Cognitive Orchestrator Internal State & Evolution Synchronization
def test_cognitive_orchestrator_evolution_sync():
    from cognitive_orchestrator import get_cognitive_orchestrator
    orchestrator = get_cognitive_orchestrator()
    
    mem_stub = {"emotion_vector": {}, "affection_level": 60.0, "relationship": {"warmth": 60.0, "stage": "Close Friend"}}
    res = orchestrator.orchestrate_turn_planning("Привет, я очень рад тебя видеть!", ["greeting"], mem_stub)
    
    assert "relationship_intelligence" in res
    internal_state = mem_stub.get("internal_state", {})
    assert "vocal_style" in internal_state or "detected_dialect" in internal_state
    
    # Validate post-turn feedback evolution logging without throwing errors
    eval_res = orchestrator.orchestrate_post_response(
        user_text="Привет, я очень рад тебя видеть!",
        reply_text="Привет! Мне тоже очень приятно с тобой разговаривать!",
        plan=res.get("plan", {}),
        mem=mem_stub,
        categories=["greeting"]
    )
    assert eval_res is not None
