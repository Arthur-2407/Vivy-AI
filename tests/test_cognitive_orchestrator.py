import pytest
import time
from cognitive_orchestrator import get_cognitive_orchestrator
from topic_tracker import get_topic_tracker, TopicTracker, ConversationStack
from conversation_planner import get_conversation_planner
from memory_orchestrator import get_memory_orchestrator
from post_response_analyzer import get_post_response_analyzer

def test_topic_tracker_and_stack():
    tracker = get_topic_tracker()
    mem = {}
    
    # 1. Process initial turn
    ctx1 = tracker.process_turn_topic("Let's talk about cooking recipes", ["recipe"], mem)
    assert "current_topic" in ctx1
    assert "Cooking" in ctx1["current_topic"] or "Recipes" in ctx1["current_topic"]
    assert ctx1["topic_depth"] >= 1

    # 2. Process subtopic shift
    ctx2 = tracker.process_turn_topic("What about spicy chicken version?", ["recipe"], mem)
    assert ctx2["topic_depth"] >= 1
    assert len(mem.get("conversation_stack", [])) >= 1

    # 3. Resolution & Stack pop
    ctx3 = tracker.process_turn_topic("Thanks, that answers it! Got it.", ["affirmative"], mem)
    assert ctx3["topic_status"] in ("active", "resolved")

def test_hierarchical_memory_retrieval():
    mem_orch = get_memory_orchestrator()
    mem_orch._memory_data["name"] = "Satyajeet"
    mem_orch._memory_data["long_term_facts"]["favorite_tool"] = "Python"
    
    retrieval = mem_orch.retrieve_relevant_memories(
        user_input="What is my name and favorite tool?",
        relationship_stage="Close Friend",
        topic_context={"current_topic": "Technical & Programming", "topic_stack": ["Technical & Programming"]}
    )
    assert "Hierarchical Memory Context" in retrieval
    assert "Satyajeet" in retrieval or "Python" in retrieval

def test_cognitive_orchestrator_turn():
    orchestrator = get_cognitive_orchestrator()
    mem = {"conversation_count": 5}
    
    # Pre-turn planning
    pkg = orchestrator.orchestrate_turn_planning(
        user_text="Can you explain python decorators?",
        categories=["technical"],
        mem=mem
    )
    assert "plan" in pkg
    plan = pkg["plan"]
    assert plan["depth"] in ("simple", "thoughtful", "comprehensive")
    assert "current_topic" in plan

    # Post-turn orchestration
    eval_res = orchestrator.orchestrate_post_response(
        user_text="Can you explain python decorators?",
        reply_text="Python decorators are functions that modify the behavior of another function.",
        plan=plan,
        mem=mem,
        categories=["technical"]
    )
    assert "overall_score" in eval_res
    assert eval_res["overall_score"] > 0.0
