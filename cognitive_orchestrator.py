"""
Vivy AI — Cognitive Orchestrator (v1.0)
Central Intelligence Coordinator executing the complete 20-stage upgraded cognitive pipeline:

User Input -> Input Normalization -> Intent Analyzer -> Conversation State Manager ->
Topic Tracker -> Conversation Stack -> Goal Manager -> Emotion Engine -> Affection Engine ->
Loneliness Engine -> Circadian Intelligence -> Hierarchical Memory Retrieval ->
Preference Retrieval -> Relationship Manager -> Internet Decision Layer -> DuckDuckGo Retrieval ->
Context Builder -> Conversation Planner -> LLM -> Response Optimizer -> Human Language Refinement ->
Memory Update -> Relationship Update -> Emotion Update -> Post-Response Evaluation ->
Database -> Telemetry -> Output
"""

import time
import json
import threading
from typing import Dict, Tuple, Optional, Any

from topic_tracker import get_topic_tracker
from emotion.emotion_engine import get_emotion_engine
from affection.affection_system import get_affection_system
from loneliness.loneliness_system import get_loneliness_system
from memory_orchestrator import get_memory_orchestrator
from conversation_planner import get_conversation_planner
from post_response_analyzer import get_post_response_analyzer
from database.db_manager import get_db_manager
try:
    from agi.cognitive_core import get_cognitive_core
except ImportError:
    pass

class CognitiveOrchestrator:
    """Central Intelligence Coordinator for Vivy AI."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "CognitiveOrchestrator":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def orchestrate_turn_planning(self, user_text: str, categories: list, mem: dict, perception_state: dict = None) -> dict:
        """
        Executes pre-LLM cognitive pipeline stages (Input -> Intent -> Topic -> Stack -> Subsystems -> Memory -> Planner).
        Returns complete orchestration package for LLM generation.
        """
        with self._lock:
            categories = categories or []
            perception_state = perception_state or {}

            # Stage 1: Input Normalization
            normalized_text = user_text.strip()

            # Stage 2 & 3: Topic Tracker & Active Conversation Stack
            topic_tracker = get_topic_tracker()
            topic_context = topic_tracker.process_turn_topic(normalized_text, categories, mem)

            # Stage 4: Circadian Intelligence & Human State
            circ_info = {}
            try:
                from circadian.circadian_engine import get_state as _get_circ_state
                circ = _get_circ_state()
                human_st = mem.get("human_state", "Awake")
                if circ and circ.enabled:
                    circ_info = {
                        "phase": circ.phase_name,
                        "energy": circ.energy,
                        "tone": circ.tone_label,
                        "sleep_mode": circ.sleep_mode,
                        "human_state": human_st
                    }
                    mem["circadian_phase"]  = circ.phase_name
                    mem["circadian_energy"] = circ.energy
                    mem["circadian_tone"]   = circ.tone_label
                    mem["circadian_sleep"]  = circ.sleep_mode
            except Exception as _err:
                print(f"[cognitive_orchestrator.py] Silenced exception: {_err}")

            # Stage 5: Emotion Engine Vector Update
            emo_engine = get_emotion_engine(mem.get("emotion_vector"))
            ev = emo_engine.update_vector(categories=categories, perception_state=perception_state, circadian_state=circ_info)
            mem["emotion_vector"] = ev
            emo_instructions = emo_engine.get_prompt_instructions()

            # Stage 6: Affection System & Relationship Stage Progression
            aff_sys = get_affection_system(mem.get("affection_level", 48.0), mem.get("relationship"))
            aff_res = aff_sys.evaluate_interaction(normalized_text, categories, mem)
            stage_caps = aff_sys.get_stage_capabilities()
            aff_info = {
                "affection_level": aff_res["affection_level"],
                "stage_label": aff_res["stage_label"],
                "capabilities": stage_caps
            }

            # Stage 7: Loneliness System & Social Drive Pacing
            lon_sys = get_loneliness_system(mem.get("loneliness_level", 0.0))
            lon_res = lon_sys.update_loneliness(mem, circadian_state=circ_info)
            lon_info = {
                "loneliness_level": lon_res["loneliness_level"],
                "social_drive": lon_res["social_drive"],
                "guidance": lon_sys.get_planner_guidance()
            }

            # Stage 8: Hierarchical Contextual Memory Retrieval
            mem_orchestrator = get_memory_orchestrator()
            mem_retrieval_str = mem_orchestrator.retrieve_relevant_memories(
                user_input=normalized_text,
                relationship_stage=aff_res["stage_label"],
                topic_context=topic_context
            )

            # Stage 9: Central Cognitive Conversation Planner Synthesis
            planner = get_conversation_planner()
            plan = planner.plan_turn(
                user_text=normalized_text,
                categories=categories,
                mem=mem,
                emotion_state=emo_instructions,
                affection_state=aff_info,
                loneliness_state=lon_info,
                circadian_state=circ_info,
                memory_context=mem_retrieval_str,
                topic_context=topic_context
            )

            mem["planner_decision"] = plan

            # Stage 9.5: AGI General Cognitive Architecture Evaluation & Synthesis
            try:
                from agi.cognitive_core import get_cognitive_core
                cog_core = get_cognitive_core()
                plan = cog_core.evaluate_pre_turn_cognition(normalized_text, mem, perception_state, plan)
                mem["planner_decision"] = plan
            except Exception as _err:
                print(f"[cognitive_orchestrator] AGI pre-turn evaluation warning: {_err}")

            return {
                "plan": plan,
                "topic_context": topic_context,
                "memory_context": mem_retrieval_str,
                "emotion_state": emo_instructions,
                "affection_state": aff_info,
                "loneliness_state": lon_info,
                "circadian_state": circ_info
            }

    def orchestrate_post_response(self, user_text: str, reply_text: str, plan: dict, mem: dict,
                                  categories: list = None, search_used: bool = False, t_start: float = None) -> dict:
        """
        Executes post-LLM cognitive pipeline stages (Evaluation -> Memory Update -> Database -> Telemetry).
        """
        with self._lock:
            categories = categories or []
            t_start = t_start or time.time()
            latency_ms = round((time.time() - t_start) * 1000.0, 2)

            # Post-response quality evaluation & self-improvement logging
            analyzer = get_post_response_analyzer()
            eval_result = analyzer.evaluate_turn(
                user_text=user_text,
                reply_text=reply_text,
                plan=plan,
                mem=mem,
                categories=categories,
                search_used=search_used
            )

            # Register turn telemetry in SQLite database
            try:
                db = get_db_manager()
                db.log_orchestrator_turn(
                    user_text=user_text,
                    reply_text=reply_text,
                    topic=plan.get("current_topic", "General"),
                    stage=plan.get("relationship_stage", "Acquaintance"),
                    primary_emotion=plan.get("tone", "friendly"),
                    search_used=search_used,
                    latency_ms=latency_ms
                )
            except Exception as _err:
                print(f"[cognitive_orchestrator.py] Silenced exception: {_err}")

            # Safe Online Learning / Offline Tuning Dataset Collection (GPU-Ready)
            try:
                import models.learning.api as learning_api
                reward = 1.0 if "friendly" in plan.get("tone", "") else 0.0
                learning_api.log_experience(
                    user_input=user_text,
                    ai_response=reply_text,
                    context=plan,
                    emotion=plan.get("tone", "friendly"),
                    reward=reward
                )
            except ImportError:
                pass
            except Exception as _err:
                print(f"[cognitive_orchestrator.py] Learning logging failed: {_err}")

            # AGI Post-Turn Experiential & Reflective Evaluation
            try:
                from agi.cognitive_core import get_cognitive_core
                cog_core = get_cognitive_core()
                eval_score = eval_result.get("score", 0.85) if isinstance(eval_result, dict) else 0.85
                cog_core.evaluate_post_turn_cognition(user_text, reply_text, plan, mem, eval_score=eval_score)
            except Exception as _err:
                print(f"[cognitive_orchestrator.py] AGI post-turn evaluation failed: {_err}")

            return eval_result

_global_orchestrator = None
def get_cognitive_orchestrator() -> CognitiveOrchestrator:
    global _global_orchestrator
    if _global_orchestrator is None:
        _global_orchestrator = CognitiveOrchestrator()
    return _global_orchestrator
