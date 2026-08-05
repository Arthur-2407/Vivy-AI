"""
relationship/shared_history.py
==============================
Manages shared history, recurring conversational rituals, inside jokes, and milestone celebrations.
Allows Vivy to spontaneously reference past humor and shared conversational rituals without hardcoding.
"""

import time
import threading
from typing import Dict, Any, List, Optional

class SharedHistoryManager:
    """Tracks evolving inside jokes, mutual conversation habits, and celebratory milestones."""

    def __init__(self, initial_history: Optional[Dict[str, Any]] = None):
        self._lock = threading.RLock()
        history = initial_history or {}
        self.inside_jokes: List[str] = list(history.get("inside_jokes", []))
        self.recurring_rituals: List[str] = list(history.get("recurring_rituals", []))
        self.conversational_habits: Dict[str, Any] = dict(history.get("conversational_habits", {}))
        self.milestone_celebrations: List[str] = list(history.get("milestone_celebrations", []))

    def record_inside_joke(self, joke_summary: str) -> None:
        with self._lock:
            j_clean = joke_summary.strip()
            if j_clean and j_clean not in self.inside_jokes:
                self.inside_jokes.append(j_clean)
                if len(self.inside_jokes) > 30:
                    self.inside_jokes = self.inside_jokes[-30:]

    def record_ritual(self, ritual_name: str) -> None:
        with self._lock:
            r_clean = ritual_name.strip()
            if r_clean and r_clean not in self.recurring_rituals:
                self.recurring_rituals.append(r_clean)

    def record_milestone(self, milestone: str) -> None:
        with self._lock:
            m_clean = milestone.strip()
            if m_clean and m_clean not in self.milestone_celebrations:
                self.milestone_celebrations.append(m_clean)

    def update_habit(self, habit_key: str, value: Any) -> None:
        with self._lock:
            self.conversational_habits[habit_key.strip()] = value

    def get_prompt_context(self) -> str:
        with self._lock:
            lines = []
            if self.inside_jokes:
                lines.append(f"Inside Jokes: {', '.join(self.inside_jokes[-3:])}")
            if self.recurring_rituals:
                lines.append(f"Recurring Rituals: {', '.join(self.recurring_rituals[-2:])}")
            if self.milestone_celebrations:
                lines.append(f"Shared Milestones: {', '.join(self.milestone_celebrations[-2:])}")
            return "\n".join(lines) if lines else ""

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "inside_jokes": list(self.inside_jokes),
                "recurring_rituals": list(self.recurring_rituals),
                "conversational_habits": dict(self.conversational_habits),
                "milestone_celebrations": list(self.milestone_celebrations)
            }
