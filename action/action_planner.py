"""
Vivy AI — Action System: Action Planner
=========================================
Builds an ActionPlan (list of ActionSteps) from an IntentModel.
Simple single-step intents are executed directly.
Multi-step intents use a structured plan. Reuses agi/long_horizon_planner.py
for complex autonomous goal decomposition when needed.

Spec reference: §25 (Action Plan Examples), §26 (Observation+Verification Loop)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from action.intent_model import ActionResult, IntentModel


@dataclass
class ActionStep:
    """A single step in an ActionPlan."""
    step_id: int
    description: str
    executor_name: str          # Which executor handles this step
    action: str
    target: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    expected_result: str = ""   # Expected outcome for verification
    requires_observation: bool = True
    is_final: bool = False


@dataclass
class ActionPlan:
    """An ordered sequence of ActionSteps for an intent."""
    intent: IntentModel
    steps: List[ActionStep] = field(default_factory=list)
    description: str = ""

    def is_single_step(self) -> bool:
        return len(self.steps) == 1


class ActionPlanner:
    """
    Builds execution plans from IntentModels.
    Single-step intents go directly to their executor.
    Multi-step intents (media search with online fallback, shopping workflow) get
    a structured plan.

    Spec reference: §25
    """
    _instance: Optional["ActionPlanner"] = None
    _lock: threading.RLock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "ActionPlanner":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def build_plan(self, intent: IntentModel) -> ActionPlan:
        """
        Build an execution plan for an intent.
        Plans are domain-specific and data-driven, not hardcoded command strings.
        Spec reference: §25
        """
        # Phase 10 Integration: Circadian Intelligence
        try:
            from circadian.circadian_manager import get_circadian_manager
            circ_mgr = get_circadian_manager()
            phase = getattr(circ_mgr, "current_phase", "Day")
            if phase in ["Deep-night", "Night"] and intent.domain in ["media", "device"]:
                if intent.parameters is None:
                    intent.parameters = {}
                intent.parameters["_circadian_volume_constraint"] = "low"
        except Exception as _circ_err:
            pass

        domain = intent.domain
        action = intent.action.lower()

        if domain == "media" and action in ("play", "search", "find"):
            return self._plan_media(intent)
        if domain == "shopping" and action in ("search", "find", "buy", "open"):
            return self._plan_shopping(intent)
        if domain == "file":
            return self._plan_file(intent)
        if domain == "app":
            return self._plan_app(intent)
        if domain == "browser":
            return self._plan_browser(intent)
        if domain == "device":
            return self._plan_device(intent)
        if domain == "system":
            return self._plan_system(intent)

        # Default: single step, dispatch to registered capability executor
        return ActionPlan(
            intent=intent,
            description=f"Execute {action} on {intent.target}",
            steps=[ActionStep(
                step_id=1,
                description=f"{action.title()} {intent.target}",
                executor_name="generic",
                action=action,
                target=intent.target,
                expected_result=intent.expected_result,
                is_final=True,
            )],
        )

    # ── Domain-specific plans ─────────────────────────────────────────────────

    def _plan_media(self, intent: IntentModel) -> ActionPlan:
        """
        Music/Video plan:
        1. Search local
        2. If found → play local → verify
        3. If not found → online fallback → verify
        Spec reference: §8
        """
        return ActionPlan(
            intent=intent,
            description=f"Play '{intent.target}' (local-first, online fallback)",
            steps=[
                ActionStep(
                    step_id=1,
                    description=f"Search and play '{intent.target}'",
                    executor_name="media",
                    action="play",
                    target=intent.target,
                    parameters=dict(intent.parameters),
                    expected_result="playback_started",
                    requires_observation=True,
                    is_final=True,
                ),
            ],
        )

    def _plan_shopping(self, intent: IntentModel) -> ActionPlan:
        """
        Shopping plan:
        1. Select provider → open search URL
        2. Capture UI state / product candidates
        3. Apply constraints
        4. Present to user
        Spec reference: §12, §13, §14
        """
        return ActionPlan(
            intent=intent,
            description=f"Search for '{intent.target}' on a shopping platform",
            steps=[
                ActionStep(
                    step_id=1,
                    description=f"Search '{intent.target}' on shopping platform",
                    executor_name="shopping",
                    action="search",
                    target=intent.target,
                    parameters=dict(intent.parameters),
                    expected_result="candidates_loaded",
                    requires_observation=True,
                    is_final=True,
                ),
            ],
        )

    def _plan_file(self, intent: IntentModel) -> ActionPlan:
        """File open/search plan."""
        return ActionPlan(
            intent=intent,
            description=f"File action: {intent.action} {intent.target}",
            steps=[
                ActionStep(
                    step_id=1,
                    description=f"{intent.action.title()} '{intent.target}'",
                    executor_name="file",
                    action=intent.action,
                    target=intent.target,
                    parameters=dict(intent.parameters),
                    expected_result="file_opened",
                    requires_observation=True,
                    is_final=True,
                ),
            ],
        )

    def _plan_app(self, intent: IntentModel) -> ActionPlan:
        """App launch/close/switch plan."""
        return ActionPlan(
            intent=intent,
            description=f"App action: {intent.action} {intent.target}",
            steps=[
                ActionStep(
                    step_id=1,
                    description=f"{intent.action.title()} '{intent.target}'",
                    executor_name="app",
                    action=intent.action,
                    target=intent.target,
                    parameters=dict(intent.parameters),
                    expected_result="app_running",
                    requires_observation=True,
                    is_final=True,
                ),
            ],
        )

    def _plan_browser(self, intent: IntentModel) -> ActionPlan:
        """Browser navigation/search plan."""
        return ActionPlan(
            intent=intent,
            description=f"Browser: {intent.action} {intent.target}",
            steps=[
                ActionStep(
                    step_id=1,
                    description=f"Open '{intent.target}' in browser",
                    executor_name="browser",
                    action=intent.action,
                    target=intent.target,
                    parameters=dict(intent.parameters),
                    expected_result="page_loaded",
                    requires_observation=True,
                    is_final=True,
                ),
            ],
        )

    def _plan_device(self, intent: IntentModel) -> ActionPlan:
        """Device action plan (volume, screen, etc.)."""
        return ActionPlan(
            intent=intent,
            description=f"Device: {intent.action} {intent.target}",
            steps=[
                ActionStep(
                    step_id=1,
                    description=f"{intent.action.title()} {intent.target}",
                    executor_name="media",
                    action=intent.action,
                    target=intent.target,
                    parameters=dict(intent.parameters),
                    expected_result="device_adjusted",
                    requires_observation=False,
                    is_final=True,
                ),
            ],
        )


    def _plan_system(self, intent: IntentModel) -> ActionPlan:
        """System action plan."""
        return ActionPlan(
            intent=intent,
            description=f"System: {intent.action} {intent.target}",
            steps=[
                ActionStep(
                    step_id=1,
                    description=f"{intent.action.title()} {intent.target}",
                    executor_name="system",
                    action=intent.action,
                    target=intent.target,
                    parameters=dict(intent.parameters),
                    expected_result="system_action_completed",
                    requires_observation=False,
                    is_final=True,
                ),
            ],
        )

# ── Singleton ──────────────────────────────────────────────────────────────────

def get_action_planner() -> ActionPlanner:
    return ActionPlanner.get_instance()
