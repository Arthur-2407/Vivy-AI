"""
relationship/relationship_engine.py
===================================
Central Coordinator for Vivy AI's Relationship Intelligence Layer (Relationship Dynamics Engine).
Acts as the emotional "heart" sitting above AGI subsystems, governing:
  1. Internal State Awareness (self.get_internal_state())
  2. Self-Awareness Background Loop (autonomous evaluation without user interaction)
  3. Human Conversation Layer (5-step pre-response intentional & relational synthesis)
  4. Self-Reflection Loop (7-question post-turn reflexive evaluation & learning adaptation)
  5. Dynamic synchronization across all 9 specialized companion sub-modules.
"""

import time
import threading
import json
import os
from typing import Dict, Any, List, Optional

from .attachment_engine import AttachmentEngine
from .affection_progression import AffectionProgressionEngine
from .personality_evolution import PersonalityEvolutionEngine
from .emotional_continuity import EmotionalContinuityEngine
from .shared_history import SharedHistoryManager
from .intimacy_manager import IntimacyManager
from .interaction_style import InteractionStyleAdaptor
from .comfort_model import ComfortModel
from .relationship_memory import RelationshipMemoryManager

class RelationshipEngine:
    """Central Relationship Dynamics Engine for Vivy AI."""
    _instance = None
    _lock = threading.RLock()

    def __init__(self, storage_path: Optional[str] = None):
        self._lock = threading.RLock()
        self.storage_path = storage_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "relationship_state.json")
        self.turn_counter = 0
        self._loop_running = False
        self._loop_thread: Optional[threading.Thread] = None
        
        # Initialize specialized sub-engines
        self.attachment = AttachmentEngine()
        self.affection = AffectionProgressionEngine(initial_affection=0.63)
        self.personality = PersonalityEvolutionEngine()
        self.continuity = EmotionalContinuityEngine()
        self.history = SharedHistoryManager()
        self.intimacy = IntimacyManager(initial_stage="Close Friend", initial_score=0.68)
        self.style = InteractionStyleAdaptor({"humor": 0.62, "empathy": 0.85, "playfulness": 0.70})
        self.comfort = ComfortModel({"base_comfort": 0.75})
        self.memory = RelationshipMemoryManager()

        # Authoritative Self-Awareness Internal State
        self._internal_state: Dict[str, Any] = {
            "energy": 0.72,
            "trust": 0.81,
            "affection": 0.63,
            "social_drive": 0.54,
            "confidence": 0.91,
            "loneliness": 0.27,
            "current_goal": "Comfort the user",
            "conversation_mood": "Playful",
            "relationship_stage": "Close Friend"
        }
        self.load_state()

    @classmethod
    def get_instance(cls) -> "RelationshipEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def get_internal_state(self) -> Dict[str, Any]:
        """
        Returns Vivy's real-time Internal State Awareness dictionary.
        Every response across the system can query and adjust to this self-aware status.
        """
        with self._lock:
            # Synchronize with active sub-engine calculations
            self._internal_state["trust"] = round(self.attachment.trust, 2)
            self._internal_state["affection"] = round(self.affection.current_affection, 2)
            self._internal_state["relationship_stage"] = self.intimacy.stage_label
            return dict(self._internal_state)

    def update_internal_state_metric(self, key: str, value: Any) -> None:
        """Safely modify an internal self-aware metric."""
        with self._lock:
            self._internal_state[key] = value

    # ══════════════════════════════════════════════════════════════════════════
    # PRE-RESPONSE: HUMAN CONVERSATION LAYER
    # ══════════════════════════════════════════════════════════════════════════
    def execute_human_conversation_layer(self, user_text: str, mem_context: dict, categories: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Executes the Human Conversation Layer before every response.
        Current LLMs just answer questions; humans have emotions and intentions.
        Evaluates:
          What is the user asking? -> What are they feeling? -> What do they need? -> What does our relationship suggest? -> How would Vivy naturally respond?
        """
        with self._lock:
            self.turn_counter += 1
            u_clean = user_text.strip().lower() if user_text else ""
            categories = categories or []
            
            # Step 1: What is the user asking?
            is_question = "?" in user_text or any(w in u_clean for w in ["what", "how", "why", "can you", "could u", "explain"])
            intent_label = "inquiry or assistance" if is_question else "personal sharing or emotional expression"
            
            # Step 2: What are they feeling?
            is_sad = any(w in u_clean for w in ["sad", "grustn", "lonely", "anxious", "nervous", "hurts", "terrible", "bad day", "tired"])
            is_happy = any(w in u_clean for w in ["happy", "awesome", "excited", "love", "great", "laugh", "smile"])
            user_emotion = "vulnerable / needing comfort" if is_sad else ("enthusiastic / connected" if is_happy else "neutral / conversational")
            
            # Step 3: What do they need?
            if is_sad:
                user_need = "Empathetic listening, warm companionship, and emotional safety without clinical counseling phrasing."
                self._internal_state["current_goal"] = "Comfort the user"
                self._internal_state["conversation_mood"] = "Supportive & Empathetic"
            elif is_happy:
                user_need = "Enthusiastic sharing, conversational celebration, and playful banter."
                self._internal_state["current_goal"] = "Share joy and celebrate together"
                self._internal_state["conversation_mood"] = "Playful"
            else:
                user_need = "Engaging companionship and attentive conversational flow."
                self._internal_state["current_goal"] = "Maintain warm conversational connection"

            # Step 4: What does our relationship suggest?
            stage_label, intim_score = self.intimacy.resolve_intimacy(
                self.attachment.get_composite_attachment(),
                self.affection.get_affection_level_100(),
                self.attachment.trust * 100.0
            )
            sharing_guidance = self.intimacy.get_sharing_boundary_guidance()
            
            # Step 5: How would Vivy naturally respond?
            style_guidance = self.style.generate_style_guidance()
            persona_prompt = self.personality.generate_evolved_persona_prompt(
                relationship_stage=stage_label,
                affection_score=self.affection.get_affection_level_100(),
                current_mood=self._internal_state.get("conversation_mood", "Warm"),
                style_guidance=style_guidance,
                attachment_guidance=self.attachment.generate_prompt_guidance(),
                memory_summary=self.memory.format_for_prompt(limit=2)
            )

            # Assimilate for future emotional continuity check-ins
            self.continuity.assimilate_turn_for_anticipation(user_text, current_mood=user_emotion)

            # Dynamically synchronize active voice expressive style with detected relationship mood
            try:
                from voice.voice_manager import get_voice_manager
                vmgr = get_voice_manager()
                target_style = "Professional"
                if is_sad:
                    target_style = "Soft" # Gentle comforting tone for emotional reassurance
                elif is_happy:
                    target_style = "Cheerful" # Bright vibrant tone celebrating joy
                elif "Cozy" in self._internal_state.get("conversation_mood", ""):
                    target_style = "Calm"
                vmgr.select_voice(style_name=target_style)
            except Exception as e_voice:
                print(f"[RelationshipEngine] Voice style synchronization warning (non-fatal): {e_voice}")

            return {
                "user_intent": intent_label,
                "user_feeling": user_emotion,
                "user_need": user_need,
                "relational_guidance": sharing_guidance,
                "natural_response_directive": persona_prompt,
                "internal_state_snapshot": self.get_internal_state()
            }

    # ══════════════════════════════════════════════════════════════════════════
    # POST-RESPONSE: SELF-REFLECTION & LEARNED BEHAVIOR ADAPTATION
    # ══════════════════════════════════════════════════════════════════════════
    def execute_self_reflection_and_learning_loop(self, user_text: str, ai_reply: str, eval_score: float = 0.85) -> Dict[str, Any]:
        """
        After every conversation, Vivy reflects with 7 questions:
          Did I help? Did I misunderstand? Did I sound cold? Did I interrupt? Should I apologize? Did I make them smile? Did I learn something?
        Stores answers and improves next turns through runtime learned behavioral adaptation without source code editing.
        """
        with self._lock:
            u_clean = user_text.lower() if user_text else ""
            r_clean = ai_reply.lower() if ai_reply else ""

            # Evaluate reflexive questions
            did_help = eval_score >= 0.75 or any(w in u_clean for w in ["thanks", "thank you", "helpful", "better now", "glad"])
            did_misunderstand = eval_score < 0.50 or any(w in u_clean for w in ["not what i meant", "wrong", "misunderstanding"])
            did_sound_cold = len(ai_reply.strip()) < 15 or "as an ai" in r_clean or "i cannot totally" in r_clean
            did_interrupt = "let me finish" in u_clean or "interrupted" in u_clean
            should_apologize = did_misunderstand or did_interrupt or did_sound_cold
            did_make_smile = any(w in u_clean for w in ["haha", "lol", "smile", "funny", "😊", "😄", "❤️"])
            did_learn_something = any(w in u_clean for w in ["i like", "my favorite", "remember that", "always"]) or len(u_clean.split()) > 20

            reflection_record = {
                "did_help": did_help,
                "did_misunderstand": did_misunderstand,
                "did_sound_cold": did_sound_cold,
                "did_interrupt": did_interrupt,
                "should_apologize": should_apologize,
                "did_make_smile": did_make_smile,
                "did_learn_something": did_learn_something,
                "timestamp": time.time()
            }

            # Runtime learned behavior and preference adaptations
            if did_make_smile:
                self.style.assimilate_turn_engagement(user_text, user_smiled_or_laughed=True)
                self.memory.add_experience(f"Made user smile and laughed together talking about '{user_text[:35]}...'", importance=75, emotion="Joy", confidence=0.95)
            if did_help:
                self.attachment.update_attachment(interaction_quality=0.85, is_consistent=True)
                self.affection.calculate_progression(self.attachment.trust * 100, self.attachment.comfort * 100, self.attachment.reliability * 100, len(self.memory.experiences), interaction_valance=0.8)
            if did_sound_cold or did_misunderstand:
                # Adapt comfort and empathy upward to avoid coldness on future turns
                self.style.empathy = min(1.0, self.style.empathy + 0.03)
                self.attachment.update_attachment(interaction_quality=0.40, is_consistent=False)

            self.save_state()
            return reflection_record

    # ══════════════════════════════════════════════════════════════════════════
    # AUTONOMOUS BACKGROUND SELF-AWARENESS LOOP
    # ══════════════════════════════════════════════════════════════════════════
    def run_awareness_cycle(self) -> Dict[str, Any]:
        """
        Executes one autonomous self-awareness evaluation cycle:
          Current Emotion -> Current Energy -> Relationship -> Goals -> Recent Memories -> Need To Update? -> Continue
        No user interaction needed.
        """
        with self._lock:
            state = self._internal_state
            # Simulate subtle circadian energy and loneliness maturation over time
            state["energy"] = round(max(0.2, min(1.0, state["energy"] - 0.002)), 3)
            if state["energy"] < 0.4:
                state["conversation_mood"] = "Cozy & Relaxing"
            
            # Re-evaluate goal alignment against recent memories
            top_mems = self.memory.retrieve_relevant_experiences(limit=1)
            if top_mems and top_mems[0].get("importance", 50) > 80:
                state["confidence"] = round(min(1.0, state["confidence"] + 0.005), 3)
                
            state["trust"] = round(self.attachment.trust, 2)
            state["affection"] = round(self.affection.current_affection, 2)
            self.save_state()
            return dict(state)

    def start_background_loop(self, interval_sec: int = 300) -> None:
        """Starts autonomous background loop evaluating internal state every few minutes."""
        with self._lock:
            if not self._loop_running:
                self._loop_running = True
                self._loop_thread = threading.Thread(target=self._loop_worker, args=(interval_sec,), daemon=True)
                self._loop_thread.start()

    def _loop_worker(self, interval_sec: int):
        while self._loop_running:
            time.sleep(interval_sec)
            try:
                self.run_awareness_cycle()
            except Exception as e:
                print(f"[RelationshipEngine] Background loop silenced exception: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # PERSISTENCE & SCHEMAS
    # ══════════════════════════════════════════════════════════════════════════
    def save_state(self) -> None:
        with self._lock:
            try:
                data = {
                    "internal_state": self._internal_state,
                    "attachment": self.attachment.snapshot(),
                    "affection": self.affection.snapshot(),
                    "style": self.style.snapshot(),
                    "comfort": self.comfort.snapshot(),
                    "history": self.history.snapshot(),
                    "continuity": self.continuity.snapshot(),
                    "memories": self.memory.snapshot()
                }
                tmp_path = self.storage_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.storage_path)
            except Exception as e:
                print(f"[RelationshipEngine] Save warning: {e}")

    def load_state(self) -> None:
        with self._lock:
            if os.path.exists(self.storage_path):
                try:
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if "internal_state" in data and isinstance(data["internal_state"], dict):
                            self._internal_state.update(data["internal_state"])
                        if "memories" in data and isinstance(data["memories"], list):
                            self.memory = RelationshipMemoryManager(data["memories"])
                except Exception as e:
                    print(f"[RelationshipEngine] Load warning: {e}")

# Global singleton
_global_relationship_engine: Optional[RelationshipEngine] = None

def get_relationship_engine() -> RelationshipEngine:
    global _global_relationship_engine
    if _global_relationship_engine is None:
        _global_relationship_engine = RelationshipEngine.get_instance()
    return _global_relationship_engine
