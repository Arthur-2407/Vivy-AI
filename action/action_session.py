"""
Vivy AI — Action System: Action Session State
==============================================
Maintains multi-turn action context inside the existing SessionManager's
temporary_context dict. Does NOT create independent storage.

Spec reference: §29 (contextual follow-up), §30 (multi-turn action state)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from action.intent_model import IntentModel


MAX_HISTORY = 20  # Bounded history — no unbounded growth


@dataclass
class ActionSession:
    """
    Per-session action state. Stored inside:
        SessionManager.get_active_session().temporary_context["action_session"]

    Never uses independent databases or files.
    Spec reference: §30
    """
    current_intent:      Optional[Dict[str, Any]] = None  # Serialised IntentModel
    current_target:      str = ""
    current_application: str = ""
    current_page:        str = ""

    # Visible candidates from the last search/browse action
    # Each: {"index": int, "label": str, "price": str, "rating": str, "url": str, ...}
    candidates: List[Dict[str, Any]] = field(default_factory=list)

    constraints: Dict[str, Any] = field(default_factory=dict)   # Budget, brand, etc.
    selected_item: Optional[Dict[str, Any]] = None

    last_action: str = ""
    last_observation: Dict[str, Any] = field(default_factory=dict)

    # Pending HIGH_RISK confirmation gate
    pending_confirmation: Optional[Dict[str, Any]] = None

    recovery_state: str = "ok"   # "ok" | "retrying" | "fallback" | "failed"
    retry_count: int = 0

    history: List[Dict[str, Any]] = field(default_factory=list)  # Bounded
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # ── Mutators ─────────────────────────────────────────────────────────────

    def set_intent(self, intent: IntentModel) -> None:
        self.current_intent = intent.to_dict()
        self.current_target = intent.target
        self.last_action = intent.action
        self.recovery_state = "ok"
        self.retry_count = 0
        self.updated_at = time.time()

    def set_candidates(self, candidates: List[Dict[str, Any]]) -> None:
        """Store visible candidates with sequential indexes for follow-up references."""
        self.candidates = []
        for idx, c in enumerate(candidates):
            entry = dict(c)
            entry["_index"] = idx + 1  # 1-based for natural language ("second one")
            self.candidates.append(entry)
        self.updated_at = time.time()

    def resolve_candidate_reference(self, ref: str) -> Optional[Dict[str, Any]]:
        """
        Resolve natural language references like "second", "2", "cheapest",
        "best rated", "the one you recommended" against the current candidate list.
        Spec reference: §17, §29
        """
        if not self.candidates:
            return None

        ref_lower = ref.strip().lower()

        # Ordinal → index map
        ordinal_map = {
            "first": 1, "1st": 1, "one": 1, "1": 1,
            "second": 2, "2nd": 2, "two": 2, "2": 2,
            "third": 3, "3rd": 3, "three": 3, "3": 3,
            "fourth": 4, "4th": 4, "four": 4, "4": 4,
            "fifth": 5, "5th": 5, "five": 5, "5": 5,
        }
        for word, idx in ordinal_map.items():
            if word in ref_lower:
                matches = [c for c in self.candidates if c.get("_index") == idx]
                if matches:
                    return matches[0]

        # Quality references
        if any(w in ref_lower for w in ["cheap", "cheapest", "lowest price", "budget"]):
            priced = [c for c in self.candidates if c.get("price")]
            if priced:
                try:
                    return min(priced, key=lambda c: float(
                        "".join(ch for ch in str(c.get("price", "999999")) if ch.isdigit() or ch == ".")
                    ) or 999999)
                except Exception:
                    return priced[0]

        if any(w in ref_lower for w in ["best rated", "highest rated", "top rated"]):
            rated = [c for c in self.candidates if c.get("rating")]
            if rated:
                try:
                    return max(rated, key=lambda c: float(
                        "".join(ch for ch in str(c.get("rating", "0")) if ch.isdigit() or ch == ".")
                    ) or 0)
                except Exception:
                    return rated[0]

        if any(w in ref_lower for w in ["recommend", "suggested", "you found"]):
            if self.selected_item:
                return self.selected_item
            return self.candidates[0] if self.candidates else None

        # Label / name match
        for c in self.candidates:
            label = str(c.get("label", "")).lower()
            if ref_lower in label or label in ref_lower:
                return c

        return None

    def record_action_step(self, action: str, result: Dict[str, Any]) -> None:
        """Append step to bounded history."""
        entry = {
            "action":    action,
            "result":    result,
            "timestamp": time.time(),
        }
        self.history.append(entry)
        if len(self.history) > MAX_HISTORY:
            self.history.pop(0)
        self.last_action = action
        self.last_observation = result.get("observation", {})
        self.updated_at = time.time()

    def set_pending_confirmation(self, payload: Dict[str, Any]) -> None:
        self.pending_confirmation = payload
        self.updated_at = time.time()

    def clear_pending_confirmation(self) -> None:
        self.pending_confirmation = None
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_intent":       self.current_intent,
            "current_target":       self.current_target,
            "current_application":  self.current_application,
            "current_page":         self.current_page,
            "candidates":           self.candidates,
            "constraints":          self.constraints,
            "selected_item":        self.selected_item,
            "last_action":          self.last_action,
            "last_observation":     self.last_observation,
            "pending_confirmation": self.pending_confirmation,
            "recovery_state":       self.recovery_state,
            "retry_count":          self.retry_count,
            "history":              self.history,
            "created_at":           self.created_at,
            "updated_at":           self.updated_at,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ActionSession":
        s = ActionSession()
        s.current_intent      = d.get("current_intent")
        s.current_target      = d.get("current_target", "")
        s.current_application = d.get("current_application", "")
        s.current_page        = d.get("current_page", "")
        s.candidates          = d.get("candidates", [])
        s.constraints         = d.get("constraints", {})
        s.selected_item       = d.get("selected_item")
        s.last_action         = d.get("last_action", "")
        s.last_observation    = d.get("last_observation", {})
        s.pending_confirmation= d.get("pending_confirmation")
        s.recovery_state      = d.get("recovery_state", "ok")
        s.retry_count         = d.get("retry_count", 0)
        s.history             = d.get("history", [])
        s.created_at          = d.get("created_at", time.time())
        s.updated_at          = d.get("updated_at", time.time())
        return s


# ── Session helpers ────────────────────────────────────────────────────────────

def get_action_session() -> ActionSession:
    """
    Retrieve (or create) the active ActionSession from the existing SessionManager.
    Spec: integrate with existing session/context infrastructure, not independent storage.
    """
    try:
        from session_manager import get_session_manager
        session = get_session_manager().get_active_session()
        raw = session.temporary_context.get("action_session")
        if raw is None:
            new_session = ActionSession()
            session.temporary_context["action_session"] = new_session.to_dict()
            return new_session
        return ActionSession.from_dict(raw)
    except Exception as err:
        print(f"[ActionSession] Falling back to in-memory session: {err}")
        return ActionSession()


def save_action_session(action_session: ActionSession) -> None:
    """Persist ActionSession back into the existing SessionManager's temporary_context."""
    try:
        from session_manager import get_session_manager
        session = get_session_manager().get_active_session()
        session.temporary_context["action_session"] = action_session.to_dict()
    except Exception as err:
        print(f"[ActionSession] Failed to save action session: {err}")
