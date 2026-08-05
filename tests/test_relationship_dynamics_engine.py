"""
tests/test_relationship_dynamics_engine.py
==========================================
Automated unit verification suite for Vivy AI's Relationship Intelligence Layer.
Validates:
  1. Internal State Awareness dictionary completeness & real-time metric updates.
  2. Attachment Theory variables progression over shared experiences.
  3. Non-Linear Affection interdependent calculation (Trust -> Comfort -> Reliability -> Affection).
  4. Dynamic Personality Evolution & gradual style adaptation (Humor from 0.20 upward without switches).
  5. Weighted Experiential Memory storage (Importance: High, Emotion: Joy, Confidence: 0.95 vs trivia).
  6. Cross-Session Emotional Continuity & proactive follow-up anticipation ("how did your interview go?").
  7. Reflexive Self-Reflection post-turn learning loop (7 self-evaluation questions).
"""

import pytest
import time
import os
import shutil
import tempfile
from relationship import get_relationship_engine, RelationshipEngine
from relationship.attachment_engine import AttachmentEngine
from relationship.affection_progression import AffectionProgressionEngine
from relationship.interaction_style import InteractionStyleAdaptor
from relationship.relationship_memory import RelationshipMemoryManager
from relationship.emotional_continuity import EmotionalContinuityEngine

@pytest.fixture
def temp_engine():
    temp_dir = tempfile.mkdtemp()
    storage_path = os.path.join(temp_dir, "test_rel_state.json")
    engine = RelationshipEngine(storage_path=storage_path)
    yield engine
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

def test_internal_state_awareness(temp_engine):
    """Test that Vivy always knows her internal state with required companion keys."""
    state = temp_engine.get_internal_state()
    assert "energy" in state
    assert "trust" in state
    assert "affection" in state
    assert "social_drive" in state
    assert "confidence" in state
    assert "loneliness" in state
    assert "current_goal" in state
    assert "conversation_mood" in state
    assert "relationship_stage" in state

    # Verify state updating
    temp_engine.update_internal_state_metric("conversation_mood", "Warm & Joyous")
    assert temp_engine.get_internal_state()["conversation_mood"] == "Warm & Joyous"

def test_attachment_theory_progression():
    """Test steady evolutionary maturation of Attachment Theory variables."""
    att = AttachmentEngine({"safety": 0.4, "reliability": 0.4, "trust": 0.3})
    init_comp = att.get_composite_attachment()

    # Simulate supportive conflict resolution and consistent days of chat
    att.update_attachment(interaction_quality=0.9, is_consistent=True, vulnerability_expressed=True, conflict_resolved=True, days_active=5)
    new_comp = att.get_composite_attachment()
    
    assert new_comp > init_comp
    assert att.trust > 0.3
    assert att.emotional_security > 0.3

def test_non_linear_affection_dynamics():
    """Test non-linear affection growth influenced by trust, comfort, reliability, and experiences."""
    aff = AffectionProgressionEngine(initial_affection=0.50)
    score1 = aff.calculate_progression(trust=60.0, comfort=60.0, reliability=55.0, shared_experiences_count=10, interaction_valance=0.8)
    assert score1 > 0.50
    assert aff.get_affection_level_100() == round(score1 * 100.0, 1)

def test_gradual_style_adaptation():
    """Test gradual personality communication evolution (e.g. humor starting at 0.20 and increasing over joke interactions)."""
    style = InteractionStyleAdaptor({"humor": 0.20})
    for _ in range(25):
        style.assimilate_turn_engagement("that joke was funny haha!", user_smiled_or_laughed=True)
    assert style.humor > 0.45, "Humor should adapt upward gradually without static switches"

def test_weighted_experiential_memory():
    """Test that experiential memories with importance weights and emotions outrank trivial facts."""
    rmm = RelationshipMemoryManager()
    rmm.add_experience("User mentioned eating soup today", importance=20, emotion="Neutral", confidence=0.8)
    rmm.add_experience("We laughed together today about an embarrassing dog story", importance=85, emotion="Joy", confidence=0.95)
    rmm.add_experience("Celebrated user getting promoted at work", importance=98, emotion="Joy", confidence=1.0)

    top_mems = rmm.retrieve_relevant_experiences(current_mood="Joy", limit=3)
    assert len(top_mems) == 3
    assert any("promoted" in m["event"] for m in top_mems)
    assert any("laughed together" in m["event"] for m in top_mems)
    assert not any("soup" in m["event"] for m in top_mems), "Low weight memories should not dominate top retrievals"

def test_emotional_continuity_anticipation():
    """Test cross-session proactive anticipation (e.g., following up on an interview or travel)."""
    ece = EmotionalContinuityEngine()
    ece.assimilate_turn_for_anticipation("I'm so nervous because I have a job interview tomorrow morning.")
    assert len(ece.pending_anticipations) == 1

    # Simulate next day session check-in (time gap >= 120s)
    follow_up = ece.get_session_opening_anticipation(time_since_last_turn_sec=7200.0)
    assert follow_up is not None
    assert "interview" in follow_up.lower() or "event" in follow_up.lower()

def test_self_reflection_and_learning_loop(temp_engine):
    """Test that Vivy asks the 7 reflexive self-evaluation questions after a turn and adapts learned behaviors."""
    eval_rec = temp_engine.execute_self_reflection_and_learning_loop(
        user_text="That helped me so much, thank you! 😊 haha",
        ai_reply="I'm so glad I could brighten your day! I love chatting with you.",
        eval_score=0.92
    )
    assert eval_rec["did_help"] is True
    assert eval_rec["did_make_smile"] is True
    assert eval_rec["did_sound_cold"] is False
    assert eval_rec["should_apologize"] is False

def test_human_conversation_layer_integration(temp_engine):
    """Test pre-turn Human Conversation Layer evaluating intent, emotion, need, and relationship guidance."""
    mem = {"long_term_facts": {}}
    res = temp_engine.execute_human_conversation_layer("I feel so sad and tired today...", mem)
    assert "vulnerable" in res["user_feeling"] or "sad" in res["user_feeling"]
    assert "Comfort" in res["user_need"] or "Empathetic" in res["user_need"]
    assert temp_engine.get_internal_state()["current_goal"] == "Comfort the user"
