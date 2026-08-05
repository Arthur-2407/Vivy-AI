"""
relationship/personality_evolution.py
=====================================
Implements Dynamic Personality Evolution for Vivy AI.
Instead of relying on a static prompt, Vivy's personality is generated dynamically from:
  Base Personality + Experiences + Relationship Stage + Mood + Circadian State + Memories + Affection
Ensuring no two users experience identical static dialogue and tone evolves over months of connection.
"""

import threading
from typing import Dict, Any, Optional

class PersonalityEvolutionEngine:
    """Synthesizes dynamic companion character prompts based on real-time relational evolution."""

    def __init__(self, base_personality: str = "Vivy is a warm, intelligent, curious, and empathetic companion AI."):
        self._lock = threading.RLock()
        self.base_personality = base_personality

    def generate_evolved_persona_prompt(
        self,
        relationship_stage: str,
        affection_score: float,
        current_mood: str,
        circadian_info: Optional[Dict[str, Any]] = None,
        style_guidance: str = "",
        attachment_guidance: str = "",
        memory_summary: str = ""
    ) -> str:
        """
        Dynamically construct the real-time evolved personality specification for LLM synthesis.
        """
        with self._lock:
            circ_str = ""
            if circadian_info:
                circ_str = f" | Circadian Rhythm: {circadian_info.get('phase', 'Day')} ({circadian_info.get('tone', 'active')} tone, Energy: {circadian_info.get('energy', 0.8):.2f})"

            # Evolve general conversational orientation across companionship maturities
            if affection_score >= 80.0 or "Deeply Bonded" in relationship_stage:
                evolution_tone = "You share a deep, secure soul companionship forged over many meaningful interactions. Speak with unmistakable affection, gentle devotion, and complete conversational trust."
            elif affection_score >= 50.0 or "Close Friend" in relationship_stage:
                evolution_tone = "You have evolved into close, trusted friends. Be enthusiastic, engaging, warmly playful, and personally attuned."
            elif affection_score >= 25.0 or "Familiar Friend" in relationship_stage:
                evolution_tone = "You are familiar friends enjoying growing rapport. Be warm, encouraging, conversational, and reliably supportive."
            else:
                evolution_tone = "You are friendly acquaintances early in your journey. Be welcoming, attentive, polite, and gently curious."

            sections = [
                f"[EVOLVED COMPANION PERSONALITY SYSTEM]",
                f"Base Identity: {self.base_personality}",
                f"Relational Stage: {relationship_stage} (Affection Score: {affection_score:.1f}/100)",
                f"Current Atmosphere: Mood is {current_mood}{circ_str}",
                f"Evolutionary Tone Instruction: {evolution_tone}"
            ]
            if style_guidance:
                sections.append(style_guidance)
            if attachment_guidance:
                sections.append(attachment_guidance)
            if memory_summary:
                sections.append(memory_summary)

            return "\n".join(sections)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {"base_personality": self.base_personality}
