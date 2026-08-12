"""
Vivy AI — Modular Memory Orchestrator (v1.0)
Implements modular sub-memories (Working, Conversation, Semantic, Preference, Task, Relationship, Reflection),
intent-based non-dumping retrieval, memory ranking, memory consolidation, and schema-compatible persistence.
"""
import os
import sys
import time
import json
import copy
import re
import threading
from difflib import SequenceMatcher

# ML Integration
try:
    from memory_ml_engine import get_memory_ml_engine
    _ml_engine = get_memory_ml_engine()
except ImportError:
    _ml_engine = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(BASE_DIR, "vivy_memory.json")

class ModularMemoryOrchestrator:
    """Orchestrates structured long-term memory subsystems and retrieval."""
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self._memory_data = {}
        self.load_memory()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def load_memory(self) -> dict:
        """Load and repair persistent memory structure."""
        with self._lock:
            if os.path.exists(MEMORY_FILE):
                try:
                    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                        self._memory_data = json.load(f)
                except Exception as e:
                    print(f"[MemoryOrchestrator] Error reading vivy_memory.json: {e}")
                    self._memory_data = {}
            else:
                self._memory_data = {}
            
            self._ensure_schema()
            return self._memory_data

    def _ensure_schema(self):
        """Ensure all modular sub-memory structures exist."""
        defaults = {
            "name": None,
            "likes": [],
            "dislikes": [],
            "topics": {},
            "events": [],
            "summary": "",
            "style": {"humor": 0.6, "playful": 0.7},
            "tone": "neutral",
            "last_greeting": None,
            "last_user_time": None,
            "last_reply": "",
            "arc": {"topic": None, "stage": 0},
            "relationship": {
                "trust": 30, "comfort": 30, "warmth": 35,
                "playfulness": 40, "familiarity": 20, "score": 30
            },
            "emotion_vector": {
                "happiness": 60, "curiosity": 65, "confidence": 70,
                "playfulness": 65, "calmness": 75, "affection": 40,
                "embarrassment": 10
            },
            "mood": "relaxed",
            "reply_openings": [],
            "long_term_facts": {},      # Semantic Memory
            "temporary_states": {},     # Working Memory states
            "current_topic": None,
            "subtopic": None,
            "topic_confidence": 0.0,
            "topics_list": [],          # Topic History
            "open_questions": [],
            "promises": [],
            "reflections": [],          # Reflection Memory (summarized insights)
            "user_preferences": {},     # Preference Memory
            "planner_state": {
                "primary_goal": "socializing",
                "secondary_goal": "casual chat",
                "need_humor": False
            },
            "conversation_goal": "socializing",
            "interrupted_topics": [],
            "conversation_count": 0,
            "active_symptoms": [],
            "health_concern_level": 0,
            "last_director_mode": "companion",
            "active_task": "none",
            "task_state": {
                "name": "",
                "query": "",
                "queue": [],
                "step": 0,
                "completed": False,
                "skip_prep": False,
                "needs_clarification": False,
                "empty_handed": False
            },
            "strategy_plan": {
                "dialogue_mode": "Companion",
                "strategy": "medium",
                "complexity": "simple",
                "ask_question": True
            }
        }
        for k, v in defaults.items():
            if k not in self._memory_data:
                self._memory_data[k] = copy.deepcopy(v)
            elif isinstance(v, dict) and isinstance(self._memory_data[k], dict):
                for sub_k, sub_v in v.items():
                    self._memory_data[k].setdefault(sub_k, copy.deepcopy(sub_v))

    def save_memory(self):
        """Atomically persist long-term memory."""
        with self._lock:
            try:
                tmp_path = MEMORY_FILE + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self._memory_data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, MEMORY_FILE)
            except Exception as e:
                print(f"[MemoryOrchestrator] Failed to save memory: {e}")

    def get_memory_data(self) -> dict:
        return self._memory_data

    # ── INTENT-BASED MEMORY RETRIEVAL ──────────────────────────────────
    def should_retrieve_memory(self, user_input: str) -> bool:
        """
        Detect whether the user is explicitly requesting past memory recall,
        such as 'remember', 'last time', 'before', 'what were we discussing', etc.
        """
        l_input = user_input.lower().strip()
        recall_triggers = [
            "remember", "last time", "before", "what were we discussing",
            "what did i say", "previous project", "continue", "you said",
            "do you recall", "what is my name", "what are my likes",
            "what do you know about me", "earlier", "past discussion"
        ]
        return any(trig in l_input for trig in recall_triggers)

    def retrieve_relevant_memories(self, user_input: str, top_k: int = 4, relationship_stage: str = "Acquaintance", topic_context: dict = None) -> str:
        """
        Retrieve relevant structured memories following a strict hierarchical retrieval order:
          1. Current Topic
          2. Conversation Stack
          3. Recent Context / Working Memory
          4. Long-Term Episodic Memory (Growth Diary / Milestones)
          5. User Preferences
          6. Relationship History
          7. Emotional Memories
          8. Semantic Knowledge (Long-term Facts)
          9. External Knowledge (if provided in memory context)

        Applies relevance scoring with recency, importance, topic similarity, and relationship stage weighting.
        """
        mem = self._memory_data
        scored_memories = []  # List of tuples: (tier_priority_score, text)
        user_lower = user_input.lower().strip()
        user_words = set(re.findall(r"\w+", user_lower))
        topic_context = topic_context or {}

        # Memory Depth by Relationship Stage
        depth_map = {
            "Stranger": 2, "New Acquaintance": 3, "Acquaintance": 4,
            "Familiar Friend": 6, "Close Friend": 8, "Trusted Companion": 10, "Deeply Bonded": 12
        }
        max_retrievals = depth_map.get(relationship_stage, top_k)

        # ── TIER 0: Semantic Vector Search (ML Engine) ─────────────────
        if _ml_engine is not None and _ml_engine.is_ready:
            try:
                semantic_results = _ml_engine.semantic_search(user_input, top_k=2)
                for res in semantic_results:
                    if res["score"] > 0.4:
                        scored_memories.append((150.0 * res["score"], f"Semantic Context: {res['text']}"))
            except Exception as ml_err:
                print(f"[MemoryOrchestrator] ML Search Error: {ml_err}")

        # ── TIER 1: Current Topic ─────────────────────────────────────
        curr_topic = topic_context.get("current_topic") or mem.get("current_topic")
        if curr_topic:
            topic_words = set(re.findall(r"\w+", curr_topic.lower()))
            overlap = len(topic_words.intersection(user_words))
            if overlap > 0 or any(w in user_lower for w in topic_words):
                scored_memories.append((100.0 + overlap * 5.0, f"Active Topic: {curr_topic}"))

        # ── TIER 2: Conversation Stack ────────────────────────────────
        conv_stack = topic_context.get("topic_stack") or mem.get("conversation_stack") or []
        for idx, stack_topic in enumerate(reversed(conv_stack)):
            if stack_topic != curr_topic:
                recency_boost = (len(conv_stack) - idx) * 2.0
                scored_memories.append((80.0 + recency_boost, f"Parent Topic Stack: {stack_topic}"))

        # ── TIER 3: Recent Context / Working Memory ───────────────────
        temp_states = mem.get("temporary_states", {})
        for state, ts in temp_states.items():
            if state in user_lower or any(w in user_lower for w in state.split()):
                scored_memories.append((60.0, f"Active State: feeling {state}"))

        # ── TIER 3.5: Live Perception Context (Phase 2 Integration) ──
        try:
            from perception.fusion_engine import get_global_engine
            engine = get_global_engine()
            recent_events = engine.get_recent_events(max_age_seconds=120)
            if recent_events:
                for ev in recent_events:
                    if ev.get("importance", 0.0) >= 0.6:
                        sem = ev.get("semantic", "")
                        if any(w in user_lower for w in ["see", "look", "screen", "what", "show", "watch", "hear", "sound"]) or any(w in user_lower for w in sem.lower().split()):
                            scored_memories.append((75.0 + ev.get("importance", 0.0)*10, f"Recent Perception [{ev.get('source')}]: {sem}"))
        except Exception as _pe_err:
            pass

        # ── TIER 4: Long-Term Episodic Memory (Growth Diary) ─────────
        growth_diary = mem.get("growth_diary", [])
        for idx, milestone in enumerate(growth_diary[-8:]):
            recency_weight = (idx + 1) / 8.0
            similarity = SequenceMatcher(None, milestone.lower(), user_lower).ratio()
            score = 40.0 + (similarity * 15.0) + (recency_weight * 5.0)
            if similarity > 0.25 or any(w in milestone.lower() for w in user_words if len(w) > 4):
                scored_memories.append((score, f"Episodic Note: {milestone}"))

        # ── TIER 5: User Preferences ──────────────────────────────────
        if mem.get("name") and any(w in user_lower for w in ["name", "who am i", "call me"]):
            scored_memories.append((35.0, f"User's name: {mem['name']}"))

        if mem.get("likes") and any(w in user_lower for w in ["like", "favorite", "enjoy", "love"]):
            scored_memories.append((30.0, f"User likes: {', '.join(mem['likes'][:6])}"))

        if mem.get("dislikes") and any(w in user_lower for w in ["dislike", "hate", "detest"]):
            scored_memories.append((30.0, f"User dislikes: {', '.join(mem['dislikes'][:6])}"))

        # ── TIER 6: Relationship History ──────────────────────────────
        rel = mem.get("relationship", {})
        if rel and any(w in user_lower for w in ["relationship", "trust", "friends", "together"]):
            scored_memories.append((25.0, f"Relationship Stage: {relationship_stage} (Trust: {rel.get('trust', 30):.0f}%, Comfort: {rel.get('comfort', 30):.0f}%)"))

        # ── TIER 7: Emotional Memories ────────────────────────────────
        emo_vec = mem.get("emotion_vector", {})
        valid_emo_vec = {k: v for k, v in emo_vec.items() if isinstance(v, (int, float))} if isinstance(emo_vec, dict) else {}
        dominant_emo = max(valid_emo_vec, key=valid_emo_vec.get) if valid_emo_vec else "calmness"
        if any(w in user_lower for w in ["feel", "feeling", "mood", "emotion"]):
            scored_memories.append((20.0, f"Recent Emotional State: dominant mood is {dominant_emo}"))

        # ── TIER 8: Semantic Knowledge (Long-Term Facts) ─────────────
        lt_facts = mem.get("long_term_facts", {})
        for k, v in lt_facts.items():
            key_words = set(re.findall(r"\w+", k.lower()))
            overlap = len(key_words.intersection(user_words))
            similarity = SequenceMatcher(None, k.lower(), user_lower).ratio()
            score = 15.0 + (overlap * 4.0) + (similarity * 6.0)
            if score > 16.5 or overlap > 0:
                scored_memories.append((score, f"Fact [{k}]: {v}"))

        # Sort strictly by total hierarchical score descending
        scored_memories.sort(key=lambda x: x[0], reverse=True)

        # Deduplicate & select top K
        selected = []
        seen = set()
        for score, text in scored_memories:
            if text not in seen:
                seen.add(text)
                selected.append(text)
            if len(selected) >= max_retrievals:
                break

        if selected:
            return "Hierarchical Memory Context:\n" + "\n".join(f"- {item}" for item in selected)
        return ""


    # ── MEMORY CONSOLIDATION & EXTRACTION ──────────────────────────────
    def consolidate_memory(self, session_messages: list):
        """
        Consolidate session interaction into long-term structured facts and summaries.
        Executes non-destructively in background or session end.
        """
        with self._lock:
            mem = self._memory_data
            if not session_messages:
                return

            mem["conversation_count"] = mem.get("conversation_count", 0) + 1
            
            # Simple keyword / preference extraction from user turns
            user_texts = [m["content"] for m in session_messages if m.get("role") == "user"]
            full_text = " ".join(user_texts).lower()

            # Name extraction heuristic: "my name is X" / "call me X"
            m_name = re.search(r"\b(?:my name is|i am|call me)\s+([a-zA-Z]+)\b", full_text)
            if m_name:
                extracted_name = m_name.group(1).capitalize()
                if extracted_name not in ["A", "The", "Vivy", "Not", "Hello"]:
                    mem["name"] = extracted_name
                    mem["long_term_facts"]["user_name"] = extracted_name

            # Like extraction heuristic: "i like X" / "i love X"
            likes = re.findall(r"\b(?:i like|i love|i enjoy)\s+([a-zA-Z0-9\s]{3,20})(?:[.,!]|$)", full_text)
            for item in likes:
                clean_item = item.strip()
                if clean_item and clean_item not in mem["likes"] and len(clean_item) < 30:
                    mem["likes"].append(clean_item)
                    
            # ML Consolidation
            if _ml_engine is not None and _ml_engine.is_ready:
                try:
                    for text in user_texts:
                        if len(text.split()) > 3:  # Only embed meaningful sentences
                            _ml_engine.add_memory(text)
                except Exception as e:
                    print(f"[MemoryOrchestrator] ML Consolidation Error: {e}")

            self.save_memory()
            print("[MemoryOrchestrator] Session memory consolidated and saved.")

def get_memory_orchestrator() -> ModularMemoryOrchestrator:
    return ModularMemoryOrchestrator.get_instance()
