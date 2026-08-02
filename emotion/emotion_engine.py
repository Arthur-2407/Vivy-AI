import time
import math
from database.db_manager import get_db_manager

class EmotionEngine:
    """
    Modular Emotional Engine for Vivy AI.
    Maintains independent 12-dimensional short-term emotional vectors:
      joy, curiosity, empathy, calmness, excitement, sadness,
      energy, frustration, confidence, anxiety, focus, playfulness.

    Supports:
      - Exponential homeostasis decay toward dynamic baselines
      - Category-based reinforcement and recovery
      - Perception and Circadian modulation
      - Prompt formatting hints (wording, pacing, emoji usage, sentence length)
    """

    DEFAULT_BASELINE = {
        "joy": 55.0,
        "curiosity": 65.0,
        "empathy": 70.0,
        "calmness": 75.0,
        "excitement": 45.0,
        "sadness": 5.0,
        "energy": 65.0,
        "frustration": 0.0,
        "confidence": 75.0,
        "anxiety": 5.0,
        "focus": 70.0,
        "playfulness": 60.0,
        "initiative": 75.0,
    }

    def __init__(self, initial_vector: dict = None):
        self.vector = dict(self.DEFAULT_BASELINE)
        if initial_vector:
            for k, v in initial_vector.items():
                if k in self.vector:
                    self.vector[k] = float(max(0.0, min(100.0, v)))
        self.last_update_ts = time.time()
        
        # Neural Network Integration (GRU State Estimator)
        self.use_ml = False
        self.gru = None
        try:
            import torch
            import torch.nn as nn
            class EmotionGRU(nn.Module):
                def __init__(self, input_size=14):
                    super().__init__()
                    # Input: 13-dim current emotion baseline + 1-dim stimulus intensity = 14
                    self.gru = nn.GRU(input_size=input_size, hidden_size=12, num_layers=1, batch_first=True)
                def forward(self, x, h):
                    out, h = self.gru(x, h)
                    return out, h
            self.gru = EmotionGRU(input_size=len(self.DEFAULT_BASELINE) + 1)
            self.gru.eval()
            self.hidden_state = torch.zeros(1, 1, 12)
            self.use_ml = True
        except ImportError:
            pass
        except Exception:
            pass

    def update_vector(self, categories: list = None, perception_state: dict = None, circadian_state: dict = None, memory_context: dict = None) -> dict:
        """
        Updates the emotional vector based on interaction categories, perception, circadian, and time decay.
        """
        now = time.time()
        dt = max(0.0, now - self.last_update_ts)
        self.last_update_ts = now

        categories = categories or []

        # Neural Network Inference (GRU)
        if self.use_ml:
            try:
                import torch
                # Build current state vector
                state_vals = [self.vector[k] / 100.0 for k in self.DEFAULT_BASELINE.keys()]
                # Simplistic stimulus metric (number of emotional categories)
                stimulus = len([c for c in categories if c in ["joke", "compliment", "flirting", "frustration", "health", "emotional", "comfort"]]) / 5.0
                
                # Input: [13-dim emotion, 1-dim stimulus]
                x = torch.tensor([state_vals + [stimulus]], dtype=torch.float32).view(1, 1, len(self.DEFAULT_BASELINE) + 1)
                
                if self.gru is not None and getattr(self, "hidden_state", None) is not None:
                    with torch.no_grad():
                        out, self.hidden_state = self.gru(x, self.hidden_state)
                        # Gently modulate vector towards neural prediction without destabilizing heuristics
                        out_vals = out.squeeze().tolist()
                        idx = 0
                        for key in list(self.DEFAULT_BASELINE.keys())[:12]:
                            if idx < len(out_vals):
                                pred_delta = float(out_vals[idx]) * 2.0
                                self.vector[key] = round(max(0.0, min(100.0, self.vector[key] + pred_delta)), 2)
                            idx += 1
            except Exception as _err:
                # Fall back gracefully to heuristic homeostasis if torch inference fails
                print(f"[emotion_engine] ML evaluation warning: {_err}")

        # 1. Homeostasis Decay (exponential drift toward baseline)
        decay_factor = math.exp(-dt / 7200.0)  # half-life of ~2 hours
        for key, base_val in self.DEFAULT_BASELINE.items():
            current = self.vector[key]
            self.vector[key] = round(base_val + (current - base_val) * decay_factor, 2)

        # 2. Category Reinforcement & Recovery
        def adj(key, delta):
            self.vector[key] = round(max(0.0, min(100.0, self.vector[key] + delta)), 2)

        if "greeting" in categories:
            adj("joy", +5); adj("playfulness", +4); adj("energy", +3)
        if "compliment" in categories:
            adj("joy", +8); adj("confidence", +5); adj("calmness", +3); adj("anxiety", -3)
        if "flirting" in categories:
            adj("playfulness", +8); adj("joy", +6); adj("excitement", +7); adj("confidence", +4)
        if "joke" in categories:
            adj("joy", +10); adj("playfulness", +8); adj("energy", +4)
        if "emotional" in categories or "vulnerable" in categories:
            adj("empathy", +10); adj("calmness", -3); adj("curiosity", +5); adj("focus", +6)
        if "comfort" in categories:
            adj("empathy", +8); adj("calmness", +5); adj("sadness", -2)
        if "technical" in categories or "knowledge" in categories:
            adj("curiosity", +8); adj("focus", +9); adj("confidence", +4); adj("playfulness", -3)
        if "health" in categories:
            adj("empathy", +10); adj("calmness", -5); adj("focus", +8); adj("anxiety", +2)
        if "gratitude" in categories:
            adj("joy", +5); adj("empathy", +4); adj("calmness", +3)
        if "frustration" in categories or "teasing" in categories:
            adj("playfulness", +4); adj("frustration", +3); adj("calmness", -2)

        # 3. Perception Influence
        if perception_state and isinstance(perception_state, dict):
            eye_contact = perception_state.get("eye_contact_score", 0.0)
            presence = perception_state.get("presence_state", "User Present")
            gaze_dir = perception_state.get("gaze_direction", "Unknown")

            if presence in ("User Present", "User Returned"):
                if eye_contact > 0.75:
                    adj("confidence", +5); adj("empathy", +3); adj("joy", +2); adj("initiative", +5)
                elif gaze_dir in ("Looking Away", "Looking Down"):
                    adj("focus", +3); adj("curiosity", +2)
            elif presence == "User Missing":
                adj("energy", -5); adj("calmness", +3)

        # 4. Circadian & Sleep Influence
        if circadian_state and isinstance(circadian_state, dict):
            energy_level = float(circadian_state.get("energy", 0.7))
            phase = circadian_state.get("phase", "Afternoon")
            sleep_mode = circadian_state.get("sleep_mode", False)

            if sleep_mode or phase in ("LateNight", "PreDawn"):
                adj("energy", -6.0)
                adj("calmness", +5.0)
                # If interrupted during sleep state, increase temporary irritation softly
                if "sleep_interrupted" in categories or "wake_attempt" in categories or len(categories) > 0:
                    adj("frustration", +3.5)
                    adj("calmness", -3.0)
                    adj("anxiety", +2.0)
            elif phase in ("Morning", "Afternoon"):
                adj("energy", energy_level * 5.0)
            elif phase in ("Evening", "Night"):
                adj("energy", -4.0)
                adj("calmness", +3.0)

        # Log snapshot to SQLite database
        try:
            db = get_db_manager()
            snapshot = dict(self.vector)
            snapshot["primary_emotion"] = self.get_primary_emotion()
            db.log_emotion_snapshot(snapshot)
        except Exception as _err:
            print(f"[emotion_engine.py] Silenced exception: {_err}")

        return self.vector

    def get_primary_emotion(self) -> str:
        """Returns the dominant emotion label."""
        candidates = {}
        for k, v in self.vector.items():
            try:
                candidates[k] = float(v)
            except (ValueError, TypeError):
                candidates[k] = 0.0
        return max(candidates, key=candidates.get) if candidates else "joy"

    def get_prompt_instructions(self) -> dict:
        """Translates current emotional state into prompt formatting guidance."""
        primary = self.get_primary_emotion()
        joy = self.vector.get("joy", 50)
        energy = self.vector.get("energy", 50)
        empathy = self.vector.get("empathy", 50)
        curiosity = self.vector.get("curiosity", 50)

        pacing = "moderate"
        if energy > 75: pacing = "brisk and enthusiastic"
        elif energy < 40: pacing = "relaxed and soft-spoken"

        sentence_length = "medium"
        if energy > 80 or joy > 80: sentence_length = "varied, punchy, and expressive"
        elif empathy > 80: sentence_length = "warm, gentle, and thoughtful"

        emoji_frequency = "rare"
        if joy > 70 or self.vector.get("playfulness", 50) > 70:
            emoji_frequency = "moderate (1 playful emoji when natural)"

        return {
            "primary_emotion": primary,
            "pacing": pacing,
            "sentence_length": sentence_length,
            "emoji_frequency": emoji_frequency,
            "empathy_weight": round(empathy / 100.0, 2),
            "curiosity_weight": round(curiosity / 100.0, 2),
            "energy_weight": round(energy / 100.0, 2)
        }

_global_emotion_engine = None
def get_emotion_engine(initial_vector: dict = None) -> EmotionEngine:
    global _global_emotion_engine
    if _global_emotion_engine is None:
        _global_emotion_engine = EmotionEngine(initial_vector)
    return _global_emotion_engine
