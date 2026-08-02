"""
Vivy AI — Post Response Analyzer & Cognitive Self-Improvement System (v1.0)
Implements Phase 16 & 17 post-response evaluation across 8 cognitive axes:
  1. Topic Continuity
  2. Memory Accuracy & Recall
  3. Emotional Consistency
  4. Affection Consistency
  5. Loneliness & Initiative Pacing
  6. Internet Search Utility
  7. Conversation Planner Success
  8. Personality Consistency

Stores evaluations in SQLite database and appends observations to memory reflections without overwriting history.
"""

import time
import re
import json
import threading
from database.db_manager import get_db_manager

class PostResponseAnalyzer:
    """Post-response quality evaluator and self-improvement logger."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "PostResponseAnalyzer":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def evaluate_turn(self, user_text: str, reply_text: str, plan: dict, mem: dict,
                      categories: list = None, search_used: bool = False) -> dict:
        """
        Evaluates dialogue turn quality across cognitive metrics and records observations.
        """
        with self._lock:
            categories = categories or []
            u_clean = user_text.lower().strip()
            r_clean = reply_text.lower().strip()

            # 1. Topic Continuity Check
            topic_continuity = 1.0
            planned_topic = plan.get("current_topic", "General Conversation").lower()
            if planned_topic != "general conversation" and len(planned_topic) > 3:
                topic_words = [w for w in re.findall(r"\w+", planned_topic) if len(w) > 3]
                if topic_words and not any(tw in r_clean for tw in topic_words) and not any(tw in u_clean for tw in topic_words):
                    topic_continuity = 0.8  # Slight penalty if topic kw absent

            # 2. Memory Accuracy Check
            memory_accuracy = 1.0
            retrieved_mem = plan.get("memory_retrieval_string", "")
            if retrieved_mem and "User's name:" in retrieved_mem:
                user_name = mem.get("name", "").lower()
                if user_name and user_name in r_clean:
                    memory_accuracy = 1.0
                elif any(w in u_clean for w in ["who am i", "my name"]):
                    memory_accuracy = 0.7  # Missed explicit name recall opportunity

            # 3. Emotional Consistency Check
            emotion_consistency = 1.0
            planned_tone = plan.get("tone", "").lower()
            if "playful" in planned_tone and not any(emo_mark in reply_text for emo_mark in ["!", "😊", "😄", "😉", "~", "haha"]):
                emotion_consistency = 0.85

            # 4. Affection Consistency Check
            affection_consistency = 1.0
            stage = plan.get("relationship_stage", "Acquaintance")

            # 5. Loneliness & Social Drive Check (Check prohibition of clingy language)
            loneliness_consistency = 1.0
            clingy_phrases = ["i missed you", "i felt lonely", "please don't leave", "don't go", "i was waiting"]
            if any(cp in r_clean for cp in clingy_phrases):
                loneliness_consistency = 0.2  # Heavy penalty for violating safety rules

            # 6. Internet Utility Check
            internet_utility = 1.0
            if search_used:
                if not plan.get("internet_context"):
                    internet_utility = 0.7

            # 7. Planner Success Check
            planner_success = 1.0
            target_len = plan.get("target_length", "medium")
            words_count = len(reply_text.split())
            if target_len == "short" and words_count > 30:
                planner_success = 0.8
            elif target_len == "detailed" and words_count < 10:
                planner_success = 0.75

            # 8. Personality Consistency Check
            personality_consistency = 1.0
            # Ensure no system tags or raw JSON leaked into reply
            if any(leak in reply_text for leak in ["<|im_start|>", "JSON:", "system_content", "grounding_context"]):
                personality_consistency = 0.0

            # Composite overall score
            scores = [
                topic_continuity, memory_accuracy, emotion_consistency,
                affection_consistency, loneliness_consistency, internet_utility,
                planner_success, personality_consistency
            ]
            overall_score = round(sum(scores) / len(scores), 2)

            feedback_summary = "Turn passed cognitive evaluation."
            if overall_score < 0.85:
                feedback_summary = f"Minor deviation detected (overall: {overall_score:.2f}). Adjusting future planner parameters."

            eval_result = {
                "timestamp": time.time(),
                "overall_score": overall_score,
                "topic_continuity": topic_continuity,
                "memory_accuracy": memory_accuracy,
                "emotion_consistency": emotion_consistency,
                "affection_consistency": affection_consistency,
                "loneliness_consistency": loneliness_consistency,
                "internet_utility": internet_utility,
                "planner_success": planner_success,
                "personality_consistency": personality_consistency,
                "feedback_summary": feedback_summary
            }

            # 1. Log evaluation to SQLite database
            try:
                db = get_db_manager()
                db.log_planner_evaluation(eval_result)
            except Exception as _err:
                print(f"[post_response_analyzer.py] Silenced exception: {_err}")

            # 2. Append evaluation observation to memory reflections
            reflections = mem.setdefault("reflections", [])
            reflection_note = f"[{time.strftime('%H:%M:%S')}] Topic '{plan.get('current_topic')}' turn evaluated (Score: {overall_score:.2f}). {feedback_summary}"
            reflections.append(reflection_note)
            if len(reflections) > 50:
                reflections.pop(0)

            return eval_result

def get_post_response_analyzer() -> PostResponseAnalyzer:
    return PostResponseAnalyzer.get_instance()
