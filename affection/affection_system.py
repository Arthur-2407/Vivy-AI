import time
import math
from database.db_manager import get_db_manager

class AffectionSystem:
    """
    Independent long-term Affection System for Vivy AI.
    Tracks affection level (0.0 to 100.0) across weeks and months.

    Relationship Stages:
      0–10: Stranger
      10–25: New Acquaintance
      25–45: Acquaintance
      45–60: Familiar Friend
      60–75: Close Friend
      75–90: Trusted Companion
      90–100: Deeply Bonded
    """

    STAGES = [
        (0.0, 10.0, "Stranger"),
        (10.0, 25.0, "New Acquaintance"),
        (25.0, 45.0, "Acquaintance"),
        (45.0, 60.0, "Familiar Friend"),
        (60.0, 75.0, "Close Friend"),
        (75.0, 90.0, "Trusted Companion"),
        (90.0, 100.0, "Deeply Bonded"),
    ]

    def __init__(self, initial_level: float = 30.0, relationship_dict: dict = None):
        self.level = float(max(0.0, min(100.0, initial_level)))
        rel = relationship_dict or {}
        self.warmth = float(rel.get("warmth", 35.0))
        self.trust = float(rel.get("trust", 30.0))
        self.familiarity = float(rel.get("familiarity", 22.0))
        self.comfort = float(rel.get("comfort", 30.0))
        self.playfulness = float(rel.get("playfulness", 30.0))
        self.last_update_ts = time.time()

    def get_stage_label(self, level: float = None) -> str:
        lvl = self.level if level is None else level
        for min_v, max_v, label in self.STAGES:
            if min_v <= lvl <= max_v:
                return label
        return "Deeply Bonded" if lvl > 100.0 else "Stranger"

    def update_from_memory(self, level: float, relationship_dict: dict):
        """Syncs the singleton state from shared memory for real-time UI accuracy."""
        self.level = float(max(0.0, min(100.0, level)))
        rel = relationship_dict or {}
        self.warmth = float(rel.get("warmth", self.warmth))
        self.trust = float(rel.get("trust", self.trust))
        self.familiarity = float(rel.get("familiarity", self.familiarity))
        self.comfort = float(rel.get("comfort", self.comfort))
        self.playfulness = float(rel.get("playfulness", self.playfulness))

    def evaluate_interaction(self, user_text: str, categories: list, mem: dict) -> dict:
        """
        Evaluates a turn's contribution to long-term affection.
        Applies strict filters to ignore spam, math, single-word greetings, or low-effort prompts.
        """
        now = time.time()
        last_ts = mem.get("last_user_time")
        gap_days = 0.0
        if last_ts and isinstance(last_ts, (int, float)):
            gap_days = max(0.0, (now - last_ts) / 86400.0)

        # 1. Apply Natural Slow Time Decay (~0.01 per day)
        decay_delta = gap_days * 0.01
        self.level = max(0.0, self.level - decay_delta)

        # 2. Strict Filter: Check if message is meaningful
        user_words = len(user_text.strip().split())
        categories = categories or []

        is_spam_or_math = False
        if user_words <= 2 and any(cat in categories for cat in ["greeting", "affirmative", "casual"]):
            is_spam_or_math = True
        elif any(c in categories for c in ["math", "calculation"]):
            is_spam_or_math = True

        delta = 0.0
        reason = "standard turn"

        if not is_spam_or_math:
            # Positive relational signals
            if "vulnerable" in categories or "expressing_vulnerability" in categories:
                delta += 0.25
                self.trust = min(100.0, self.trust + 0.5)
                self.warmth = min(100.0, self.warmth + 0.4)
                reason = "expressed vulnerability"
            elif "seeking_closeness" in categories or "comfort" in categories:
                delta += 0.15
                self.warmth = min(100.0, self.warmth + 0.3)
                self.comfort = min(100.0, self.comfort + 0.3)
                reason = "seeking closeness/comfort"
            elif "compliment" in categories:
                delta += 0.10
                self.warmth = min(100.0, self.warmth + 0.2)
                reason = "compliment"
            elif "flirting" in categories or "intimacy" in categories:
                delta += 0.12
                self.playfulness = min(100.0, self.playfulness + 0.3)
                self.warmth = min(100.0, self.warmth + 0.2)
                reason = "flirting/intimacy"
            elif user_words >= 15:
                # Sustained personal conversation
                delta += 0.05
                self.familiarity = min(100.0, self.familiarity + 0.1)
                reason = "sustained dialogue"

            # Negative relational signals (Insults, hostility, manipulation)
            if any(insult in user_text.lower() for insult in ["stupid", "idiot", "dumb", "hate you", "useless"]):
                delta -= 0.50
                self.trust = max(0.0, self.trust - 1.0)
                self.warmth = max(0.0, self.warmth - 0.8)
                reason = "hostility/disrespect"

        # Cap max gain per single turn to prevent rapid jumps
        delta = max(-1.0, min(0.35, delta))

        # Check total conversation count threshold for stage promotions
        conv_count = mem.get("conversation_count", 0)
        max_allowed_level = 35.0
        if conv_count >= 60: max_allowed_level = 100.0
        elif conv_count >= 30: max_allowed_level = 80.0
        elif conv_count >= 15: max_allowed_level = 60.0
        elif conv_count >= 5: max_allowed_level = 45.0

        prev_stage = self.get_stage_label()
        self.level = round(float(min(max_allowed_level, max(0.0, self.level + delta))), 2)
        new_stage = self.get_stage_label()

        # Update memory structures for backward compatibility
        mem["affection_level"] = self.level
        mem["relationship"] = {
            "score": int(self.level),
            "warmth": self.warmth,
            "trust": self.trust,
            "familiarity": self.familiarity,
            "comfort": self.comfort,
            "playfulness": self.playfulness
        }

        # Log history to database
        try:
            db = get_db_manager()
            db.log_affection_history(
                level=self.level,
                stage=new_stage,
                warmth=self.warmth,
                trust=self.trust,
                familiarity=self.familiarity,
                delta=delta,
                reason=reason
            )
            if prev_stage != new_stage:
                db.log_relationship_milestone(
                    milestone=f"Relationship stage progressed to {new_stage}",
                    details=f"Affection level reached {self.level}",
                    stage_unlocked=new_stage
                )
        except Exception as _err:
            print(f"[affection_system.py] Silenced exception: {_err}")

        return {
            "affection_level": self.level,
            "stage_label": new_stage,
            "delta": delta,
            "reason": reason
        }

    def get_stage_capabilities(self) -> dict:
        """
        Translates current relationship stage into unlocked behavior capabilities.
        Does NOT script responses; unlocks capabilities for Planner.
        """
        label = self.get_stage_label()

        capabilities = {
            "Stranger": {
                "memory_depth": 3,
                "greeting_personalization": "polite and reserved",
                "proactive_follow_up": False,
                "callback_frequency": 0.05,
                "preference_confidence": 0.3
            },
            "New Acquaintance": {
                "memory_depth": 5,
                "greeting_personalization": "warm and friendly",
                "proactive_follow_up": False,
                "callback_frequency": 0.10,
                "preference_confidence": 0.5
            },
            "Acquaintance": {
                "memory_depth": 8,
                "greeting_personalization": "familiar and energetic",
                "proactive_follow_up": True,
                "callback_frequency": 0.15,
                "preference_confidence": 0.65
            },
            "Familiar Friend": {
                "memory_depth": 12,
                "greeting_personalization": "comfortable and casual",
                "proactive_follow_up": True,
                "callback_frequency": 0.25,
                "preference_confidence": 0.8
            },
            "Close Friend": {
                "memory_depth": 15,
                "greeting_personalization": "close and attentive",
                "proactive_follow_up": True,
                "callback_frequency": 0.35,
                "preference_confidence": 0.9
            },
            "Trusted Companion": {
                "memory_depth": 20,
                "greeting_personalization": "deeply familiar and intuitive",
                "proactive_follow_up": True,
                "callback_frequency": 0.45,
                "preference_confidence": 0.95
            },
            "Deeply Bonded": {
                "memory_depth": 25,
                "greeting_personalization": "profoundly tuned and supportive",
                "proactive_follow_up": True,
                "callback_frequency": 0.50,
                "preference_confidence": 1.0
            }
        }

        return capabilities.get(label, capabilities["Acquaintance"])

    def get_progression_details(self) -> dict:
        """
        Returns rich dynamic relationship progression data for the UI panel:
          - Current Stage & XP Progress
          - Next Stage & Level Gap
          - Growth Trend & Trust Contribution
          - Detailed Relational Factors (Warmth, Trust, Familiarity, Comfort, Playfulness)
          - Recent Milestones & Shared Memories
        """
        curr_label = self.get_stage_label()
        curr_min, curr_max, next_stage_name = 0.0, 100.0, "Max Level"
        
        for idx, (min_v, max_v, label) in enumerate(self.STAGES):
            if min_v <= self.level <= max_v:
                curr_min, curr_max = min_v, max_v
                if idx + 1 < len(self.STAGES):
                    next_stage_name = self.STAGES[idx + 1][2]
                break

        stage_span = max(1.0, curr_max - curr_min)
        xp_progress = round(max(0.0, min(100.0, ((self.level - curr_min) / stage_span) * 100.0)), 1)

        milestones = []
        try:
            db = get_db_manager()
            if hasattr(db, "get_recent_milestones"):
                milestones = db.get_recent_milestones(limit=5)
        except Exception as _err:
            print(f"[affection_system.py] Silenced exception: {_err}")

        if not milestones:
            milestones = [
                {"milestone": f"Achieved {curr_label} stage", "timestamp": self.last_update_ts}
            ]

        return {
            "affection_level": self.level,
            "current_stage": curr_label,
            "next_stage": next_stage_name,
            "xp_progress": xp_progress,
            "stage_min": curr_min,
            "stage_max": curr_max,
            "growth_trend": "Positive (+0.15 avg)" if self.trust > 35 else "Developing",
            "trust_contribution": round(self.trust * 0.4, 1),
            "warmth": self.warmth,
            "trust": self.trust,
            "familiarity": self.familiarity,
            "comfort": self.comfort,
            "playfulness": self.playfulness,
            "recent_milestones": milestones
        }

_global_affection_system = None
def get_affection_system(initial_level: float = 30.0, relationship_dict: dict = None) -> AffectionSystem:
    global _global_affection_system
    if _global_affection_system is None:
        _global_affection_system = AffectionSystem(initial_level, relationship_dict)
    return _global_affection_system

