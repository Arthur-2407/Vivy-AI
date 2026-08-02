import os
import sys
import copy
import time
import pytest

# Ensure Vivy root path is accessible
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import conversation
from cognitive_orchestrator import CognitiveOrchestrator
from conversation_planner import get_conversation_planner


@pytest.fixture
def base_memory():
    return copy.deepcopy(conversation.DEFAULT_MEMORY)


def test_no_cognition_ml_name_error(base_memory):
    """
    Verify that autonomous_search_decision does not raise NameError for '_cognition_ml'
    and executes smoothly for greetings and general inquiries.
    """
    should_search, query = conversation.autonomous_search_decision(
        "how are u feeling today", ["You: hi", "Vivy: Hey!"], base_memory, ["casual"]
    )
    assert isinstance(should_search, bool)
    
    should_search_coffee, _ = conversation.autonomous_search_decision(
        "how about going on a coffee", ["You: hi", "Vivy: Hey!"], base_memory, ["casual"]
    )
    assert isinstance(should_search_coffee, bool)


def test_safe_emotion_vector_adjust(base_memory):
    """
    Verify that updating emotion vectors does not crash with KeyError when keys are missing or modified.
    """
    base_memory["emotion_vector"] = {"custom_mood": 60.0}  # Intentionally missing standard keys like 'happiness'
    # Calling update_emotion_vector should safely default and update without exception
    conversation.update_emotion_vector(base_memory, ["greeting", "joke", "health"], history=["You: happy to see you"])
    assert "happiness" in base_memory["emotion_vector"]
    assert "affection" in base_memory["emotion_vector"]


def test_cognitive_orchestrator_prompt_wiring(base_memory):
    """
    Verify that outputs from CognitiveOrchestrator (planner_decision, system_prompt_directives)
    are directly injected into the LLM system prompt assembled by build().
    """
    orch = CognitiveOrchestrator()
    user_msg = "how about going on a coffee"
    orch_pkg = orch.orchestrate_turn_planning(
        user_text=user_msg,
        categories=["casual"],
        mem=base_memory,
        perception_state={}
    )
    assert "plan" in orch_pkg
    base_memory["planner_decision"] = orch_pkg["plan"]
    
    prompt = conversation.build(base_memory, [], user_msg, categories=["casual"])
    assert "[COGNITIVE DIALOGUE & RELATIONSHIP DIRECTIVES]" in prompt
    assert "- Social Invitation Guidance:" in prompt


def test_relationship_progression_invitation_handling(base_memory):
    """
    Verify that social invitations (coffee, hangout) adapt dynamically based on affection stage and score.
    """
    user_msg = "how about going on a coffee together"
    
    # Stage 1: New / Stranger (low affection)
    base_memory["relationship"]["score"] = 10
    base_memory["affection_level"] = 10.0
    base_memory["planner_decision"] = {"system_prompt_directives": ["Be polite."]}
    prompt_stranger = conversation.build(base_memory, [], user_msg, categories=["casual"])
    assert "maintaining comfortable boundaries" in prompt_stranger
    
    # Stage 2: Close Friend / Partner (high affection)
    base_memory["relationship"]["score"] = 75
    base_memory["affection_level"] = 75.0
    prompt_close = conversation.build(base_memory, [], user_msg, categories=["casual"])
    assert "respond enthusiastically and naturally to the invitation" in prompt_close
    assert "Do NOT brush it off, change the subject, or respond with generic deflection" in prompt_close


def test_unified_grounding_validator_completeness(base_memory):
    """
    Verify that the merged validate_perception_grounding function enforces both frame age/OCR validity
    AND visual hallucination prevention without overwriting one another.
    """
    now = time.time()
    # Test 1: Stale frame detection (from initial validator logic)
    p_stale = {"screen_sharing_active": True, "written_at": now - 10.0}
    valid, reason = conversation.validate_perception_grounding("I see your browser open.", "what is on my screen?", base_memory, p_stale, now)
    assert not valid
    assert reason == "stale_frame_data"
    
    # Test 2: Camera Hallucination check (from second validator logic)
    p_cam_off = {"camera_active": False}
    valid_halluc, reason_halluc = conversation.validate_perception_grounding("i see you smiling brightly at me!", "can you see me right now?", base_memory, p_cam_off, now)
    assert not valid_halluc
    assert "Hallucinates" in reason_halluc


def test_api_compatibility_and_module_integrity():
    """
    Verify that all architectural modules remain intact, fully functional, and accessible without disruption or removal.
    """
    assert hasattr(conversation, "generate_reply_internal")
    assert hasattr(conversation, "autonomous_search_decision")
    assert hasattr(conversation, "_pick_fallback")
    assert hasattr(conversation, "update_emotion_vector")
    assert hasattr(conversation, "build")
    
    # Verify submodules load cleanly
    from affection.affection_system import get_affection_system
    from emotion.emotion_engine import get_emotion_engine
    from topic_tracker import get_topic_tracker
    assert get_affection_system() is not None
    assert get_emotion_engine() is not None
    assert get_topic_tracker() is not None


def test_resource_manager_stream_restoration(tmp_path):
    """
    Verify that when sys.stdout or sys.stderr is redirected to a registered log file,
    calling ResourceManager.shutdown_all() cleanly restores sys.stdout and sys.stderr
    before closing the file, preventing 'Error in sys.excepthook: I/O operation on closed file'.
    """
    from resource_manager import get_resource_manager
    rm = get_resource_manager()
    log_path = os.path.join(str(tmp_path), "test_stream.log")
    test_log = open(log_path, "w", encoding="utf-8")
    rm.register_file(test_log, name="test_log")
    
    old_stdout, old_stderr = sys.stdout, sys.stderr
    try:
        sys.stdout = test_log
        sys.stderr = test_log
        rm.shutdown_all()
        # After shutdown_all, sys.stdout and sys.stderr should no longer point to the closed test_log
        assert not sys.stderr.closed
        assert not sys.stdout.closed
        assert sys.stderr != test_log
        assert sys.stdout != test_log
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
