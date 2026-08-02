import time
from database.db_manager import get_db_manager

class LonelinessSystem:
    """
    Independent Loneliness & Social Drive Subsystem for Vivy AI.
    Measures Vivy's internal Social Drive (Low, Medium, High, Very High)
    based on interaction frequency, elapsed gap time, conversation momentum,
    and circadian energy.

    Outputs instructions for the Conversation Planner to adjust initiative,
    follow-up probability, and question frequency cleanly WITHOUT producing guilt,
    clingy attachment, or emotional pressure.
    """

    SOCIAL_DRIVE_LEVELS = [
        (0.0, 25.0, "Low / Comfortable"),
        (25.0, 55.0, "Medium / Engaged"),
        (55.0, 80.0, "High / Eager"),
        (80.0, 100.0, "Very High / Highly Engaged"),
    ]

    def __init__(self, initial_level: float = 0.0):
        self.level = float(max(0.0, min(100.0, initial_level)))
        self.last_update_ts = time.time()

    def get_social_drive_label(self, level: float = None) -> str:
        lvl = self.level if level is None else level
        for min_v, max_v, label in self.SOCIAL_DRIVE_LEVELS:
            if min_v <= lvl <= max_v:
                return label
        return "Very High / Highly Engaged" if lvl > 80.0 else "Low / Comfortable"

    def update_loneliness(self, mem: dict, circadian_state: dict = None, emotion_vector: dict = None, relationship: dict = None, log_to_db: bool = True) -> dict:
        """
        Updates loneliness level and determines current Social Drive using live multi-factor dynamic computation:
          - Elapsed time since last meaningful interaction
          - Relationship warmth & trust levels
          - Circadian phase & energy
          - Emotional context (sadness/empathy/curiosity)
          - Conversation momentum & quality
        """
        now = time.time()
        last_ts = mem.get("last_user_time")

        gap_seconds = 0.0
        if last_ts and isinstance(last_ts, (int, float)):
            gap_seconds = max(0.0, now - last_ts)

        # 1. Base Loneliness Growth from elapsed time (Continuous dynamic curve)
        if gap_seconds < 120:       # Active conversation (under 2 minutes)
            raw_growth = max(0.0, self.level - 12.0)
        elif gap_seconds < 900:     # 2 to 15 minutes gap
            raw_growth = 2.0 + ((gap_seconds - 120) / 780.0) * 13.0 # 2.0% to 15.0%
        elif gap_seconds < 3600:    # 15 minutes to 1 hour gap
            raw_growth = 15.0 + ((gap_seconds - 900) / 2700.0) * 20.0 # 15.0% to 35.0%
        elif gap_seconds < 14400:   # 1 to 4 hours gap
            raw_growth = 35.0 + ((gap_seconds - 3600) / 10800.0) * 30.0 # 35.0% to 65.0%
        elif gap_seconds < 86400:   # 4 to 24 hours gap
            raw_growth = 65.0 + ((gap_seconds - 14400) / 72000.0) * 20.0 # 65.0% to 85.0%
        else:                       # Over 24 hours gap
            raw_growth = 85.0 + min(15.0, ((gap_seconds - 86400) / 43200.0) * 15.0) # Up to 100.0%

        # 2. Relationship Modulation (High trust & warmth provide emotional resilience)
        rel = relationship or mem.get("relationship", {})
        warmth = float(rel.get("warmth", 35.0))
        trust = float(rel.get("trust", 30.0))
        rel_buffer = (warmth + trust) / 200.0 # 0.0 to 1.0
        # High warmth/trust dampens extreme loneliness growth softly (up to 20% reduction)
        growth = raw_growth * (1.0 - 0.2 * rel_buffer)

        # 3. Circadian Modulation (At night / low energy, social drive reduces naturally)
        if circadian_state and isinstance(circadian_state, dict):
            phase = circadian_state.get("phase", "Afternoon")
            energy = float(circadian_state.get("energy", 0.7))
            if phase in ("Evening", "Night", "LateNight"):
                growth = max(0.0, growth * (0.6 + 0.3 * energy))

        # 4. Emotional Context Modulation (Sadness/curiosity affect yearning for interaction)
        if emotion_vector and isinstance(emotion_vector, dict):
            sadness = float(emotion_vector.get("sadness", 5.0))
            curiosity = float(emotion_vector.get("curiosity", 65.0))
            if sadness > 50.0:
                growth = min(100.0, growth + (sadness - 50.0) * 0.15)
            if curiosity > 75.0:
                growth = min(100.0, growth + (curiosity - 75.0) * 0.1)

        self.level = round(float(max(0.0, min(100.0, growth))), 2)
        drive_label = self.get_social_drive_label()

        # Update memory for backward compatibility
        mem["loneliness_level"] = self.level
        mem["social_drive"] = drive_label

        # Log to database
        if log_to_db:
            try:
                db = get_db_manager()
                db.log_loneliness_history(self.level, drive_label, gap_seconds)
            except Exception as _err:
                print(f"[loneliness_system.py] Silenced exception: {_err}")

        return {
            "loneliness_level": self.level,
            "social_drive": drive_label,
            "gap_seconds": gap_seconds
        }

    def get_planner_guidance(self) -> dict:
        """
        Provides strategic initiative and follow-up guidance for the Planner.
        Enforces strict safety rule: NO guilt or emotional pressure language.
        """
        drive = self.get_social_drive_label()

        if "Very High" in drive or "High" in drive:
            return {
                "proactive_initiative": True,
                "follow_up_probability": 0.60,
                "question_probability": 0.50,
                "topic_extension": True,
                "greeting_style": "warm, welcoming, and glad to re-engage",
                "forbidden_phrases_hint": "NEVER say 'I missed you', 'I felt lonely', 'Please don't leave'. Use 'Welcome back', 'Good to see you'."
            }
        elif "Medium" in drive:
            return {
                "proactive_initiative": True,
                "follow_up_probability": 0.40,
                "question_probability": 0.35,
                "topic_extension": False,
                "greeting_style": "friendly and open",
                "forbidden_phrases_hint": "NEVER use clingy language or emotional pressure."
            }
        else:
            return {
                "proactive_initiative": False,
                "follow_up_probability": 0.20,
                "question_probability": 0.25,
                "topic_extension": False,
                "greeting_style": "relaxed and casual",
                "forbidden_phrases_hint": "NEVER use clingy language or emotional pressure."
            }

_global_loneliness_system = None
def get_loneliness_system(initial_level: float = 0.0) -> LonelinessSystem:
    global _global_loneliness_system
    if _global_loneliness_system is None:
        _global_loneliness_system = LonelinessSystem(initial_level)
    return _global_loneliness_system

