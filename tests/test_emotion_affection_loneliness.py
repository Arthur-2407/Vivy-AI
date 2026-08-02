import os
import sys
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from emotion.emotion_engine import EmotionEngine, get_emotion_engine
from affection.affection_system import AffectionSystem, get_affection_system
from loneliness.loneliness_system import LonelinessSystem, get_loneliness_system

def test_emotion_engine_vectors():
    engine = EmotionEngine()
    assert len(engine.vector) == 13
    assert "joy" in engine.vector
    assert "curiosity" in engine.vector

    # Test category reinforcement
    v1 = engine.update_vector(categories=["flirting", "joke"])
    assert v1["playfulness"] > 60.0
    assert v1["joy"] > 55.0

    # Test prompt formatting output
    instructions = engine.get_prompt_instructions()
    assert "primary_emotion" in instructions
    assert "pacing" in instructions

def test_affection_system_progression():
    aff = AffectionSystem(initial_level=15.0)
    assert aff.get_stage_label() == "New Acquaintance"

    # Test anti-spam filter (one word replies shouldn't increase affection)
    res_spam = aff.evaluate_interaction("hi", ["greeting"], {"conversation_count": 2})
    assert res_spam["delta"] == 0.0

    # Test genuine vulnerable interaction
    res_vuln = aff.evaluate_interaction(
        "I felt really overwhelmed at work today and wanted to talk to you.",
        ["vulnerable", "emotional"],
        {"conversation_count": 10}
    )
    assert res_vuln["delta"] > 0.0
    assert aff.level > 15.0

    # Test unlocked capabilities
    caps = aff.get_stage_capabilities()
    assert "memory_depth" in caps
    assert "greeting_personalization" in caps

def test_loneliness_system_drive():
    lon = LonelinessSystem(initial_level=10.0)
    assert "Low" in lon.get_social_drive_label()

    # Test loneliness growth after 24h
    mem = {"last_user_time": 1000.0}
    now_ts = 1000.0 + 90000.0  # 25 hours gap
    import time
    time_orig = time.time
    try:
        time.time = lambda: now_ts
        res = lon.update_loneliness(mem)
        assert res["loneliness_level"] > 30.0
        guidance = lon.get_planner_guidance()
        assert "forbidden_phrases_hint" in guidance
        assert "NEVER say 'I missed you'" in guidance["forbidden_phrases_hint"]
    finally:
        time.time = time_orig
