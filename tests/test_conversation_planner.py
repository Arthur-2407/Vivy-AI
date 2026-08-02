import os
import sys
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from conversation_planner import ConversationPlanner, get_conversation_planner

def test_conversation_planner_synthesis():
    planner = ConversationPlanner()

    user_text = "What is the capital of France?"
    categories = ["knowledge"]
    mem = {"conversation_count": 12, "last_user_time": 1000.0}

    emotion_state = {
        "primary_emotion": "curiosity",
        "empathy_weight": 0.50,
        "energy_weight": 0.70,
        "curiosity_weight": 0.85,
        "pacing": "moderate",
        "sentence_length": "medium"
    }

    affection_state = {
        "affection_level": 45.0,
        "stage_label": "Acquaintance",
        "capabilities": {
            "memory_depth": 5,
            "greeting_personalization": "friendly",
            "proactive_follow_up": True,
            "callback_frequency": 0.15
        }
    }

    loneliness_state = {
        "loneliness_level": 20.0,
        "social_drive": "Low / Comfortable",
        "guidance": {
            "proactive_initiative": False,
            "follow_up_probability": 0.20,
            "question_probability": 0.25,
            "topic_extension": False,
            "greeting_style": "casual",
            "forbidden_phrases_hint": "NEVER use clingy language."
        }
    }

    circadian_state = {"phase": "Afternoon", "energy": 0.80}

    plan = planner.plan_turn(
        user_text=user_text,
        categories=categories,
        mem=mem,
        emotion_state=emotion_state,
        affection_state=affection_state,
        loneliness_state=loneliness_state,
        circadian_state=circadian_state,
        memory_context="Fact: Likes geography",
        internet_context="Paris is the capital of France."
    )

    assert "tone" in plan
    assert "target_length" in plan
    assert "system_prompt_directives" in plan
    assert "Relationship Stage: Acquaintance" in plan["system_prompt_directives"]
    assert "Real-Time Internet Intelligence Context" in plan["system_prompt_directives"]
