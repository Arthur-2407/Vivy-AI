import random
import time
from database.db_manager import get_db_manager

class ConversationPlanner:
    """
    Central Cognitive Planner for Vivy AI (Upgraded v2.0).
    Synthesizes independent signals from:
      - EmotionEngine (12-dim vector, primary emotion)
      - AffectionSystem (0-100 level, stage label & capabilities)
      - LonelinessSystem (social drive, initiative, follow-up)
      - CircadianEngine (phase, energy, tone deltas)
      - MemoryOrchestrator (hierarchical contextual retrieval)
      - TopicTracker & ConversationStack (persistent topic nodes, subtopics, stack)
      - Internet Intelligence / DuckDuckGo context
      - Message Categories / Intent

    Outputs a unified Conversation Strategy Plan containing:
      - topic_state (current_topic, previous_topic, stack, subtopics, depth, momentum)
      - conversation_goal, pending_question, expected_user_reply
      - topic_completion_status, natural_exit_conditions, fallback_strategies
      - greeting_style, tone, empathy_level, curiosity_level, depth, target_length
      - question_probability, callback_probability, topic_continuation
      - memory_retrieval_string, internet_context, proactive_engagement
      - system_prompt_directives
    """

    def plan_turn(self, user_text: str, categories: list, mem: dict,
                  emotion_state: dict, affection_state: dict, loneliness_state: dict,
                  circadian_state: dict, memory_context: str = "", internet_context: str = "",
                  topic_context: dict = None) -> dict:

        categories = categories or []
        topic_context = topic_context or {}
        user_words = len(user_text.strip().split())

        # 1. Subsystem Signals
        primary_emotion = emotion_state.get("primary_emotion", "calmness")
        empathy_weight = emotion_state.get("empathy_weight", 0.50)
        energy_weight = emotion_state.get("energy_weight", 0.65)
        curiosity_weight = emotion_state.get("curiosity_weight", 0.65)

        affection_level = affection_state.get("affection_level", 30.0)
        stage_label = affection_state.get("stage_label", "Acquaintance")
        stage_caps = affection_state.get("capabilities", {})

        social_drive = loneliness_state.get("social_drive", "Low / Comfortable")
        loneliness_guidance = loneliness_state.get("guidance", {})

        circ_phase = (circadian_state or {}).get("phase", "Afternoon")
        circ_energy = (circadian_state or {}).get("energy", 0.70)

        # 2. Topic State & Momentum Analysis
        current_topic = topic_context.get("current_topic") or mem.get("current_topic") or "General Conversation"
        previous_topic = topic_context.get("previous_topic")
        conv_stack = topic_context.get("topic_stack") or mem.get("conversation_stack") or [current_topic]
        topic_depth = topic_context.get("topic_depth") or len(conv_stack)
        subtopics = topic_context.get("subtopics") or []
        topic_status = topic_context.get("topic_status") or "active"

        # Calculate momentum based on recent turn frequency and length
        momentum = "steady"
        if user_words >= 15:
            momentum = "high"
        elif user_words <= 3:
            momentum = "low"

        # Goal Determination
        conversation_goal = mem.get("conversation_goal") or "socializing and building rapport"
        if "technical" in categories or "knowledge" in categories:
            conversation_goal = "providing technical clarity and knowledge sharing"
        elif "recipe" in categories:
            conversation_goal = "assisting with culinary guidance"
        elif "health" in categories:
            conversation_goal = "empathetic health and well-being support"
        elif "vulnerable" in categories or "comfort" in categories:
            conversation_goal = "deep emotional support and active listening"

        # Pending question and expected reply tracking
        pending_question = topic_context.get("waiting_question")
        expected_user_reply = topic_context.get("expected_reply")

        # Natural exit conditions
        exit_conditions = [
            "User expresses gratitude or closure ('thanks', 'got it')",
            "Topic stack resolved naturally",
            "User explicitly switches topic"
        ]

        # Fallback strategies
        fallback_strategies = [
            "Acknowledge with empathetic statement",
            "Offer relevant follow-up question related to current topic stack",
            "Bridge to previous topic if current subtopic resolved"
        ]

        # 3. Synthesize Tone & Personality Register
        tone = "warm and friendly"
        if stage_label in ("Stranger", "New Acquaintance"):
            tone = "polite, reserved, and warm"
        elif stage_label in ("Close Friend", "Trusted Companion", "Deeply Bonded"):
            tone = "deeply affectionate, comfortable, and intuitive"

        if primary_emotion == "playfulness":
            tone += ", playful and teasing"
        elif primary_emotion == "empathy":
            tone += ", gentle and deeply caring"

        # 4. Synthesize Response Length & Complexity (Depth)
        target_length = "medium"
        depth = "simple"

        if user_words <= 3 and any(cat in categories for cat in ["greeting", "affirmative", "casual"]):
            target_length = "short"
            depth = "simple"
        elif "technical" in categories or "knowledge" in categories or "recipe" in categories:
            target_length = "detailed"
            depth = "comprehensive"
        elif user_words >= 15 or "vulnerable" in categories:
            target_length = "detailed"
            depth = "thoughtful"

        # Apply Circadian & Energy Modulation to Length
        if circ_energy < 0.35 and target_length == "detailed":
            target_length = "medium"

        # 5. Synthesize Question & Callback Probabilities
        question_prob = loneliness_guidance.get("question_probability", 0.35)
        callback_prob = stage_caps.get("callback_frequency", 0.20)

        if "vulnerable" in categories or "comfort" in categories:
            question_prob = min(0.30, question_prob)  # Don't interrogate during emotional beats

        # 6. Proactive Initiative Determination
        proactive_engagement = loneliness_guidance.get("proactive_initiative", False) and stage_caps.get("proactive_follow_up", False)

        # 7. Build Synthesized System Directives
        directives = []
        directives.append(f"Current Topic: {current_topic} (Stack: {' -> '.join(conv_stack)}). Goal: {conversation_goal}.")
        directives.append(f"Relationship Stage: {stage_label} ({affection_level:.1f}/100). Personalization: {stage_caps.get('greeting_personalization', 'friendly')}.")
        directives.append(f"Internal Mood: {primary_emotion}. Pacing: {emotion_state.get('pacing', 'moderate')}. Expression: {emotion_state.get('sentence_length', 'varied')}.")
        directives.append(f"Social Drive: {social_drive}. {loneliness_guidance.get('forbidden_phrases_hint', '')}")
        directives.append("Continuous Dialogue Rule: Every reply MUST connect directly to what was just said in a natural human conversational flow. Respond directly to the user with warmth, emotional presence, and genuine human companionship. NEVER generate developer logs, internal reasoning, third-person commentary, or analytical explanations like 'Okay, the user just said...' or 'Since I'm supposed to be a companion...'. Internalize your emotional state and relationship level silently, and speak directly to the user as a real human friend without ever voicing internal analyses.")

        if memory_context:
            directives.append(f"Retrieved Memory Context:\n{memory_context}")

        if internet_context:
            directives.append(f"Real-Time Internet Intelligence Context:\n{internet_context}")

        plan = {
            # Core planner parameters (Backwards compatible)
            "greeting_style": loneliness_guidance.get("greeting_style", "friendly"),
            "tone": tone,
            "empathy_level": empathy_weight,
            "curiosity_level": curiosity_weight,
            "depth": depth,
            "target_length": target_length,
            "question_probability": question_prob,
            "callback_probability": callback_prob,
            "topic_continuation": loneliness_guidance.get("topic_extension", False),
            "memory_retrieval_string": memory_context,
            "internet_context": internet_context,
            "proactive_engagement": proactive_engagement,
            "system_prompt_directives": "\n".join(directives),

            # Stateful Topic & Orchestration parameters (Upgraded)
            "current_topic": current_topic,
            "previous_topic": previous_topic,
            "conversation_stack": conv_stack,
            "topic_depth": topic_depth,
            "subtopics": subtopics,
            "conversation_goal": conversation_goal,
            "pending_question": pending_question,
            "expected_user_reply": expected_user_reply,
            "conversation_momentum": momentum,
            "topic_completion_status": topic_status,
            "natural_exit_conditions": exit_conditions,
            "fallback_strategies": fallback_strategies
        }

        # Persist planner state in memory
        mem["planner_state"] = {
            "primary_goal": conversation_goal,
            "current_topic": current_topic,
            "momentum": momentum,
            "target_length": target_length
        }

        # Log decision to SQLite database
        try:
            db = get_db_manager()
            db.log_planner_decision(plan)
        except Exception as _err:
            print(f"[conversation_planner.py] Silenced exception: {_err}")

        return plan

_global_planner = None
def get_conversation_planner() -> ConversationPlanner:
    global _global_planner
    if _global_planner is None:
        _global_planner = ConversationPlanner()
    return _global_planner
