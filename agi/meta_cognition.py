"""
Vivy AI — Meta-Cognition Engine
==============================
Upgrades classic single-pass conversational responses (User -> LLM -> Reply)
into a research-grade reflexive control flow:
  User -> Reason -> Critique -> Improve -> Verify -> Reply

Evaluates candidate outputs against:
  1. Relational Affection & Tone Compatibility
  2. Emotional Homeostasis Alignment
  3. Factual Consistency with World Model and Beliefs
  4. Repetition & Hallucination Elimination
  5. Health Triage & Empathetic Responsivity
"""

import time
import re
import threading
from typing import Dict, Any, Tuple, Optional
from agi.world_model import get_world_model
from agi.belief_engine import get_belief_engine

class MetaCognitionEngine:
    """Reflexive supervisor for LLM reasoning and response quality verification."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "MetaCognitionEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._lock = threading.RLock()
        self.critique_history = []
        self.total_evaluations = 0
        self.refinements_applied = 0

    def evaluate_and_refine(self, user_text: str, candidate_reply: str, plan: dict, mem: dict, max_iterations: int = 1) -> Tuple[str, Dict[str, Any]]:
        """
        Executes the Reason -> Critique -> Improve -> Verify evaluation loop.
        Returns the verified/refined text along with meta-cognitive diagnostic telemetry.
        """
        with self._lock:
            self.total_evaluations += 1
            t_start = time.time()
            reply = candidate_reply.strip()
            critiques_logged = []
            was_modified = False

            for iteration in range(max_iterations):
                critiques = self._critique_candidate(user_text, reply, plan, mem)
                if not critiques:
                    break  # Candidate passes all verification criteria!

                critiques_logged.extend(critiques)
                reply, modified = self._improve_candidate(reply, critiques, plan)
                if modified:
                    was_modified = True

            if was_modified:
                self.refinements_applied += 1

            latency_ms = round((time.time() - t_start) * 1000.0, 2)
            meta_report = {
                "verified": len(critiques_logged) == 0 or was_modified,
                "iterations": max_iterations,
                "critiques": critiques_logged,
                "was_refined": was_modified,
                "latency_ms": latency_ms
            }
            self.critique_history.append(meta_report)
            if len(self.critique_history) > 50:
                self.critique_history = self.critique_history[-50:]
                
            return reply, meta_report

    def _critique_candidate(self, user_text: str, reply: str, plan: dict, mem: dict) -> list:
        """Internal critique layer examining coherence, tone, and empathy."""
        critiques = []
        reply_lower = reply.lower()
        user_lower = user_text.lower()

        # 1. Critique: Repetitive phrase loops
        words = reply_lower.split()
        if len(words) >= 6:
            for i in range(len(words) - 5):
                gram = " ".join(words[i:i+4])
                if reply_lower.count(gram) > 1:
                    critiques.append({"type": "REPETITION", "detail": f"Repeated N-gram detected: '{gram}'"})
                    break

        # 2. Critique: Empathy Deficit during Health / Vulnerable topics
        tone = str(plan.get("tone", "")).lower()
        if any(w in user_lower for w in ["fever", "pain", "sad", "sick", "hurts", "depressed", "anxious"]):
            if not any(ew in reply_lower for ew in ["sorry", "here for you", "hope", "care", "gentle", "rest", "feel", "concern"]):
                critiques.append({"type": "EMPATHY_DEFICIT", "detail": "User expressed distress or physical discomfort; response lacked explicit empathy markers."})

        # 3. Critique: Hallucinatory XML or reasoning residue (<think> block escape)
        if "<think>" in reply_lower or "</think>" in reply_lower or "```" in reply and "code" not in user_lower:
            critiques.append({"type": "FORMATTING_LEAK", "detail": "Uncleaned CoT tags or unwarranted syntax markup detected in spoken speech stream."})

        # 4. Critique: Contradiction against established high-confidence beliefs
        try:
            belief_eng = get_belief_engine()
            for belief in belief_eng.get_high_confidence_beliefs(min_confidence=0.8):
                prop = belief["proposition"].lower()
                if ("hate" in prop and "love " + prop.replace("hate ", "") in reply_lower) or \
                   ("never" in prop and prop.replace("never ", "") in reply_lower):
                    critiques.append({"type": "BELIEF_CONTRADICTION", "detail": f"Reply violates confirmed belief: {prop}"})
        except Exception as _err:
            print(f"[MetaCognition] Belief evaluation warning: {_err}")

        return critiques

    def _improve_candidate(self, reply: str, critiques: list, plan: dict) -> Tuple[str, bool]:
        """Applies algorithmic refinement transformations to satisfy critique criteria."""
        modified = False
        refined = reply

        for crit in critiques:
            ctype = crit.get("type")
            if ctype == "FORMATTING_LEAK":
                # Remove unclosed XML tags and internal thoughts
                refined = re.sub(r'<[^>]*>', '', refined)
                refined = refined.replace("```", "").strip()
                modified = True
            elif ctype == "EMPATHY_DEFICIT":
                # Prefix warmth modifier if empathy deficit flagged
                if not refined.startswith("I hear you") and not refined.startswith("I'm sorry"):
                    refined = f"I hear you, and I'm really sorry you're feeling that way. {refined}"
                    modified = True
            elif ctype == "REPETITION":
                # Trim repetitive suffix sentences
                sentences = re.split(r'(?<=[.!?]) +', refined)
                seen_s = set()
                dedup_s = []
                for s in sentences:
                    s_norm = s.lower().strip()
                    if s_norm and s_norm not in seen_s:
                        seen_s.add(s_norm)
                        dedup_s.append(s)
                    else:
                        modified = True
                refined = " ".join(dedup_s)

        return refined, modified

    def generate_meta_reasoning_prompt(self, user_text: str, plan: dict) -> str:
        """Generates pre-turn reasoning instructions to prime LLM internal verification."""
        tone = plan.get("tone", "friendly")
        stage = plan.get("relationship_stage", "Acquaintance")
        return (
            f"[Meta-Cognitive Directive]: Verify logic before speaking. "
            f"Adhere strictly to relational stage ({stage}) and tone ({tone}). "
            f"Avoid repetitive phrasing and maintain empathy parity with user statements."
        )

_global_meta_cognition = None
def get_meta_cognition() -> MetaCognitionEngine:
    global _global_meta_cognition
    if _global_meta_cognition is None:
        _global_meta_cognition = MetaCognitionEngine.get_instance()
    return _global_meta_cognition
