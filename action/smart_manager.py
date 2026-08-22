"""
Vivy AI — Action System: Smart Manager
========================================
Central orchestration engine for the Voice Assistant Action System.
Implements the full Intent → Capability → Plan → Execute → Observe → Verify → Report loop.

Integrates with:
  - CognitiveOrchestrator (detects intent early in pipeline, Stage 9.6)
  - AutonomousToolRouter (routes action intents from existing tool dispatch)
  - EventBus (publishes action lifecycle events)
  - SessionManager (reads/writes ActionSession via temporary_context)
  - InternetManager (online fallback for resource resolution)
  - TelemetryManager (health reporting)

Spec reference: §27 (Smart Manager Architecture), §26 (Observation+Verification),
                §28 (Clarification Policy), §55 (Decision Authority)
"""

from __future__ import annotations

import re
import time
import threading
from typing import Any, Dict, List, Optional, Tuple

from action.intent_model import (
    ActionDomain, ActionResult, ActionVerb, IntentModel, RiskLevel
)


# ─── Intent Detection Patterns ─────────────────────────────────────────────────
# These are heuristic triggers, not the final interpretation.
# Matched patterns lead to a structured IntentModel, never hardcoded commands.

_INTENT_PATTERNS: List[Dict[str, Any]] = [
    # ── MEDIA ────────────────────────────────────────────────────────────────
    {"domain": "media", "action": "play",
     "patterns": [r"play\s+(.+)", r"(?:put on|start playing)\s+(.+)",
                  r"i want to (?:listen|hear)\s+(.+)", r"play me\s+(.+)"],
     "source": "local_then_online", "risk": "LOW_RISK",
     "expected": "playback_started"},

    {"domain": "media", "action": "pause",
     "patterns": [r"pause\b", r"stop (?:the )?music\b", r"pause (?:the )?(?:music|video|playback)"],
     "target_fixed": "media_player", "source": "local_only", "risk": "LOW_RISK",
     "expected": "playback_paused"},

    {"domain": "device", "action": "adjust",
     "patterns": [r"(?:set|turn|adjust)?\s*volume\s+(?:to\s+)?(\w+)",
                  r"(?:volume\s+)?(?:up|down|louder|quieter|mute|unmute)"],
     "source": "local_only", "risk": "LOW_RISK",
     "expected": "device_adjusted"},

    # ── FILE ─────────────────────────────────────────────────────────────────
    {"domain": "file", "action": "open",
     "patterns": [r"open\s+(?:the\s+)?(?:file\s+)?(.+\.(?:pdf|docx?|xlsx?|pptx?|txt|csv|py|js|json|png|jpg|mp3|mp4))",
                  r"(?:show|display|read)\s+(?:me\s+)?(?:the\s+)?file\s+(.+)"],
     "source": "local_only", "risk": "LOW_RISK",
     "expected": "file_opened"},

    {"domain": "file", "action": "open",
     "patterns": [r"open\s+(?:the\s+)?(?:my\s+)?(.+?)(?:\s+folder|\s+directory)"],
     "source": "local_only", "risk": "LOW_RISK",
     "expected": "folder_opened"},

    {"domain": "file", "action": "find",
     "patterns": [r"(?:find|search for|locate)\s+(?:the\s+)?(?:file\s+)?(.+)",
                  r"(?:where is|where's)\s+(?:my\s+)?(.+)"],
     "source": "local_only", "risk": "LOW_RISK",
     "expected": "file_found"},

    # ── APP ───────────────────────────────────────────────────────────────────
    {"domain": "app", "action": "open",
     "patterns": [r"open\s+(.+?)(?:\s+app|\s+application|\s+program)?\s*$",
                  r"launch\s+(.+)", r"start\s+(.+?)(?:\s+app|\s+application)?\s*$"],
     "source": "local_only", "risk": "LOW_RISK",
     "expected": "app_running"},

    {"domain": "app", "action": "close",
     "patterns": [r"close\s+(.+)", r"quit\s+(.+)", r"exit\s+(.+)"],
     "source": "local_only", "risk": "MEDIUM_RISK",
     "expected": "app_closed"},

    {"domain": "app", "action": "switch",
     "patterns": [r"switch to\s+(.+)", r"go to\s+(.+)", r"bring up\s+(.+)"],
     "source": "local_only", "risk": "LOW_RISK",
     "expected": "app_focused"},

    # ── BROWSER ───────────────────────────────────────────────────────────────
    {"domain": "browser", "action": "open",
     "patterns": [r"(?:open|go to|navigate to|visit)\s+(https?://\S+)",
                  r"(?:open|go to|visit)\s+(?:the\s+)?website\s+(.+)",
                  r"(?:open|go to|visit)\s+(.+\.(?:com|net|org|io|in|co|uk|gov))"],
     "source": "online_only", "risk": "LOW_RISK",
     "expected": "page_loaded"},

    {"domain": "browser", "action": "search",
     "patterns": [r"search (?:the web |online |internet )?for\s+(.+)",
                  r"look up\s+(.+) online", r"google\s+(.+)",
                  r"find (?:information|info|details) (?:about|on)\s+(.+)"],
     "source": "online_only", "risk": "LOW_RISK",
     "expected": "page_loaded"},

    # ── SHOPPING ─────────────────────────────────────────────────────────────
    {"domain": "shopping", "action": "search",
     "patterns": [r"(?:i want|i need|find|buy|get|order|shop for)\s+(?:a\s+|an\s+)?(.+?)(?:\s+for\s+me)?$",
                  r"(?:show me|find me|search for)\s+(.+?)(?:\s+to\s+buy|\s+online)?\s*$",
                  r"(?:i'm looking for|looking to buy)\s+(.+)"],
     "source": "online_only", "risk": "LOW_RISK",
     "expected": "candidates_loaded"},

    {"domain": "shopping", "action": "recommend",
     "patterns": [r"(?:which|what)\s+(?:one|product|speaker|phone|laptop)\s+(?:do you recommend|should i buy|is better)",
                  r"(?:recommend|suggest)\s+(?:a|the\s+best|the\s+cheapest)?(.*)"],
     "source": "online_only", "risk": "LOW_RISK",
     "expected": "recommendation_given"},

    # ── OBJECT IDENTIFICATION ────────────────────────────────────────────────
    {"domain": "object", "action": "identify",
     "patterns": [r"what\s+is\s+in\s+my\s+hand", r"what\s+am\s+i\s+holding", 
                  r"identify\s+this\s+object", r"what\s+is\s+this"],
     "source": "local_then_online", "risk": "LOW_RISK",
     "expected": "object_identified"},
]


# ─── Follow-up patterns (contextual references to prior action state) ──────────
_FOLLOWUP_PATTERNS: List[Dict[str, Any]] = [
    # Selection references
    {"domain": "auto", "action": "select",
     "patterns": [r"(?:open|show me|select|pick)\s+the\s+(?:first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|\d+(?:st|nd|rd|th)?)\s+(?:one|result|option|product)?",
                  r"(?:the\s+)?(?:first|second|third|\d+(?:st|nd|rd|th)?)\s+(?:one|result|option|product)"]},
    # Filter/budget updates
    {"domain": "auto", "action": "filter",
     "patterns": [r"(?:under|below|within|less than)\s+[\₹\$\€£]?\s*[\d,]+",
                  r"(?:my\s+budget\s+is|budget\s+of)\s+[\₹\$\€£]?\s*[\d,]+",
                  r"(?:filter|show only|keep)\s+(?:the\s+)?(?:cheap|affordable|premium|best)"]},
    # Recommendation requests
    {"domain": "auto", "action": "recommend",
     "patterns": [r"which (?:one|do you|should i)",
                  r"what (?:would you|do you)\s+recommend",
                  r"(?:which is|what's)\s+the\s+best"]},
]


class SmartManager:
    """
    Central Voice Assistant Action System orchestrator.
    Spec reference: §27
    """
    _instance: Optional["SmartManager"] = None
    _lock: threading.RLock = threading.RLock()

    def __init__(self):
        self._enabled = True
        self._config_loaded = False
        self._active_intents: Dict[str, Dict[str, Any]] = {}
        self._load_config()

    def cancel_action(self, intent_id: str) -> bool:
        """Phase 9: Explicit cancellation mechanism."""
        with self._lock:
            if intent_id in self._active_intents:
                self._active_intents[intent_id]["cancelled"] = True
                print(f"[SmartManager] Action {intent_id} marked for cancellation.")
                self._publish_event("action.cancelled", {"intent_id": intent_id})
                return True
            return False

    @classmethod
    def get_instance(cls) -> "SmartManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _load_config(self) -> None:
        if self._config_loaded:
            return
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            self._enabled = cfg.get("action_system.enabled", True)
            self._confidence_threshold = float(
                cfg.get("action_system.clarification_confidence_threshold", 0.55)
            )
            self._max_retries = int(cfg.get("action_system.max_retries", 3))
        except Exception:
            self._confidence_threshold = 0.55
            self._max_retries = 3
        self._config_loaded = True

    # ── Primary entry points ──────────────────────────────────────────────────

    def try_route(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Called from AutonomousToolRouter. Returns {"handled": True, ...} if this
        is an action intent; {"handled": False} otherwise.
        Spec reference: §27 integration with tool_router.py
        """
        if not self._enabled:
            return {"handled": False}
        if not query or not query.strip():
            return {"handled": False}

        intent = self.detect_intent_only(query, context or {})
        if intent is None or intent.domain == ActionDomain.UNKNOWN.value:
            return {"handled": False}

        # Execute the intent
        result = self.handle(query, context or {}, predetected_intent=intent)
        return {
            "handled": True,
            "domain": result.domain,
            "action": result.action,
            "success": result.success,
            "message": result.to_natural_language(),
            "result": result.to_dict(),
        }

    def detect_intent_only(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[IntentModel]:
        """
        Lightweight intent detection — reads only (no execution).
        Called from CognitiveOrchestrator Stage 9.6 to inject intent metadata
        into the turn plan without executing it yet.
        Returns None if no action intent detected.
        Spec reference: §27, Stage 9.6 integration
        """
        if not self._enabled:
            return None
        if not text or len(text.strip()) < 3:
            return None

        # Check for follow-up intent first (using existing ActionSession context)
        followup = self._detect_followup(text, context or {})
        if followup:
            return followup

        # Primary intent detection
        return self._detect_primary_intent(text)

    def handle(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
        predetected_intent: Optional[IntentModel] = None,
    ) -> ActionResult:
        """
        Full action handling pipeline:
        detect → plan → execute → observe → verify → report

        Spec reference: §27
        """
        if not self._enabled:
            return ActionResult(
                success=False, domain="unknown", action="unknown", target=text,
                message="The action system is currently disabled.",
            )

        context = context or {}
        text = text.strip()

        # Phase 9: Formal Action State Machine
        from action.intent_model import ActionState
        
        def _set_state(new_state: ActionState, res: Optional[ActionResult] = None):
            if intent:
                intent.state = new_state.value
            self._publish_event("action.state_changed", {
                "state": new_state.value,
                "intent": intent.to_dict() if intent else None
            })
            if res:
                res.state = new_state.value

        # ── Intent detection ──────────────────────────────────────────────────
        intent = predetected_intent or self.detect_intent_only(text, context)
        if intent is None:
            return ActionResult(
                success=False, domain="unknown", action="unknown", target=text,
                message="I couldn't determine what action you want me to take.",
                error="No intent detected",
                state=ActionState.FAILED.value
            )
            
        _set_state(ActionState.UNDERSTANDING)

        # ── Explicit global cancellation intercept ──────────────────────────────
        if self._is_cancellation(text):
            # If there's an active executing action, we would cancel it here.
            # In Phase 9, we introduce the cancel_action API.
            from action.action_session import get_action_session
            sess = get_action_session()
            if sess.current_intent:
                self.cancel_action(sess.current_intent.get("id", ""))
            _set_state(ActionState.CANCELLED)
            return ActionResult(
                success=True, domain="system", action="cancel", target="all",
                message="Action cancelled successfully.",
                state=ActionState.CANCELLED.value
            )

        # ── Check pending confirmation gate ───────────────────────────────────
        from action.action_session import get_action_session, save_action_session
        session = get_action_session()

        pending = session.pending_confirmation
        if pending and self._is_confirmation(text):
            _set_state(ActionState.AUTHORIZED)
            return self._execute_confirmed_action(pending, session)

        # ── Extract constraints ───────────────────────────────────────────────
        if not intent.constraints:
            from action.constraint_extractor import get_constraint_extractor
            intent.constraints = get_constraint_extractor().extract(text)

        self._publish_event("action.intent_detected", intent.to_dict())

        # ── Risk gate ─────────────────────────────────────────────────────────
        from action.risk_policy import evaluate_risk
        evaluate_risk(intent)
        if intent.confirmation_required and not session.pending_confirmation:
            payload = {
                "action": intent.action,
                "item_name": intent.target,
                "risk_level": intent.risk_level,
                "message": f"This action ({intent.action} {intent.target}) is HIGH RISK. Are you sure?"
            }
            session.set_pending_confirmation(payload)
            res = ActionResult(
                success=False, domain=intent.domain, action=intent.action, target=intent.target,
                message=payload["message"],
                requires_confirmation=True,
                confirmation_payload=payload
            )
            _set_state(ActionState.WAITING_FOR_USER, res)
            return res

        # ── Resolve capability ─────────────────────────────────────────────────
        from action.capability_registry import get_capability_registry
        cap = get_capability_registry().discover(intent.domain, intent.action)
        if cap is None:
            res = ActionResult(
                success=False, domain=intent.domain, action=intent.action,
                target=intent.target,
                message=f"I don't know how to '{intent.action}' {intent.domain} items yet.",
                error="No capability registered",
                state=ActionState.FAILED.value
            )
            _set_state(ActionState.FAILED, res)
            return res

        # ── Build plan ────────────────────────────────────────────────────────
        _set_state(ActionState.PLANNED)
        from action.action_planner import get_action_planner
        plan = get_action_planner().build_plan(intent)

        # ── Execute ───────────────────────────────────────────────────────────
        _set_state(ActionState.EXECUTING)
        self._publish_event("action.plan_started", {"plan": plan.description})
        
        # 7. 3D Anime Avatar Integration
        try:
            import os
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            trig_file = os.path.join(base_dir, "shared", "animation_trigger.txt")
            os.makedirs(os.path.dirname(trig_file), exist_ok=True)
            with open(trig_file, "w", encoding="utf-8") as f:
                f.write("ActionExecute")
        except Exception as _anim_err:
            print(f"[SmartManager] Avatar trigger warning: {_anim_err}")

        # Track the active intent for cancellation
        intent_id = str(intent.detected_at)
        self._active_intents[intent_id] = {"intent": intent, "cancelled": False}
        intent.parameters["_intent_id"] = intent_id
        
        result = self._execute_plan(plan, intent, session)
        
        # Cleanup active intent
        self._active_intents.pop(intent_id, None)

        if result.requires_confirmation:
            _set_state(ActionState.WAITING_FOR_USER, result)
        elif result.success:
            _set_state(ActionState.SUCCESS, result)
        else:
            _set_state(ActionState.FAILED, result)

        # ── Record step in session history ────────────────────────────────────
        session.record_action_step(intent.action, result.to_dict())
        save_action_session(session)

        # ── Publish result event ──────────────────────────────────────────────
        self._publish_event("action.result", {
            "success": result.success,
            "domain": result.domain,
            "verified": result.verified,
        })

        # Deep Integration: AGI, Memory, Evolution, Neural
        self._integrate_post_execution(intent, result, session)

        return result

    def _execute_plan(
        self, plan: "ActionPlan", intent: IntentModel, session: Any
    ) -> ActionResult:
        """Execute each step of the plan, with retry and fallback logic."""
        from action.action_session import save_action_session

        for step in plan.steps:
            # Dispatch to the correct executor
            result = self._dispatch_to_executor(step, intent)

            # Check for confirmation requirement (HIGH_RISK gate)
            if result.requires_confirmation:
                return result

            # Retry on failure (up to max_retries)
            if not result.success:
                for attempt in range(self._max_retries - 1):
                    time.sleep(0.5)
                    result = self._dispatch_to_executor(step, intent)
                    if result.success:
                        result.recovery_attempted = True
                        break

            # Final result for this step
            if step.is_final:
                return result

        return result

    def _dispatch_to_executor(self, step: "ActionStep", intent: IntentModel) -> ActionResult:
        """Route step to the correct executor class."""
        name = step.executor_name
        try:
            if name == "file":
                from action.executors.file_executor import get_file_executor
                return get_file_executor().execute(intent)
            if name == "app":
                from action.executors.app_executor import get_app_executor
                return get_app_executor().execute(intent)
            if name == "media":
                from action.executors.media_executor import get_media_executor
                return get_media_executor().execute(intent)
            if name == "browser":
                from action.executors.browser_executor import get_browser_executor
                return get_browser_executor().execute(intent)
            if name == "shopping":
                from action.executors.shopping_executor import get_shopping_executor
                return get_shopping_executor().execute(intent)
            if name == "object":
                from action.executors.object_executor import get_object_executor
                return get_object_executor().execute(intent)
            if name == "system":
                from action.executors.system_executor import get_system_executor
                return get_system_executor().execute(intent)
        except Exception as err:
            return ActionResult(
                success=False, domain=intent.domain, action=intent.action,
                target=intent.target,
                message=f"I encountered an error while executing the action.",
                error=str(err),
            )
        return ActionResult(
            success=False, domain=intent.domain, action=intent.action,
            target=intent.target,
            message=f"No executor available for '{name}'.",
            error="Executor not found",
        )

    # ── Intent detection ──────────────────────────────────────────────────────

    def _detect_primary_intent(self, text: str) -> Optional[IntentModel]:
        """
        Match text against heuristic patterns to build an IntentModel.
        Returns None if no pattern fires above the confidence threshold.
        Spec reference: §23
        """
        text_l = text.lower().strip()
        best_intent: Optional[IntentModel] = None
        best_score = 0.0

        for entry in _INTENT_PATTERNS:
            for pat in entry["patterns"]:
                m = re.search(pat, text_l, re.IGNORECASE)
                if m:
                    # Confidence: longer match = higher confidence
                    match_len = len(m.group(0))
                    score = min(1.0, 0.60 + (match_len / max(len(text_l), 1)) * 0.40)

                    if score > best_score:
                        best_score = score
                        # Extract target from first capture group if present
                        target = entry.get("target_fixed", "")
                        if not target:
                            groups = m.groups()
                            target = groups[0].strip() if groups else text.strip()

                        best_intent = IntentModel(
                            domain=entry["domain"],
                            action=entry["action"],
                            target=target,
                            source=entry.get("source", "local_then_online"),
                            confidence=score,
                            risk_level=entry.get("risk", RiskLevel.LOW_RISK.value),
                            expected_result=entry.get("expected", ""),
                            raw_text=text,
                            is_followup=False,
                        )

        if best_intent is not None and best_score >= self._confidence_threshold:
            return best_intent

        # Phase 8: Semantic Intent Fallback
        # If keyword heuristics return low confidence or no match, fallback to LLM.
        return self._semantic_intent_fallback(text, context)

    def _semantic_intent_fallback(
        self, text: str, context: Dict[str, Any]
    ) -> Optional[IntentModel]:
        """
        Use the existing LLM context to determine if this is a structured action.
        This provides a robust, semantic fallback when regex heuristics fail
        (e.g., "take me somewhere I can buy a small speaker").
        """
        # We use a lightweight local LLM or API call here.
        # For this implementation, we will route to a fast LLM extraction.
        # To prevent circular imports or heavy blocking, we use a timeout-bound request
        # or the ML Cognition Classifier if available.
        try:
            from config.config_manager import get_config_manager
            import json
            cfg = get_config_manager()
            # In a full deployment, this would use Vivy's `llm` proxy directly.
            # Here we simulate the semantic structural extraction:
            text_l = text.lower()
            if any(w in text_l for w in ["buy", "purchase", "shopping", "store"]):
                return IntentModel(
                    domain="shopping", action="search", target=text,
                    source="online_only", confidence=0.85, risk_level=RiskLevel.LOW_RISK.value,
                    raw_text=text, is_followup=False
                )
            if any(w in text_l for w in ["browser", "website", "internet", "web"]):
                return IntentModel(
                    domain="browser", action="search", target=text,
                    source="online_only", confidence=0.85, risk_level=RiskLevel.LOW_RISK.value,
                    raw_text=text, is_followup=False
                )
        except Exception as _llm_err:
            print(f"[SmartManager] Semantic fallback error: {_llm_err}")

        return None

    def _detect_followup(
        self, text: str, context: Dict[str, Any]
    ) -> Optional[IntentModel]:
        """
        Detect follow-up intents that reference prior action session state
        (e.g. "open the second one", "under 1000", "which do you recommend").
        Spec reference: §29 (Contextual follow-up), §17 (Visual selection)
        """
        try:
            from action.action_session import get_action_session
            session = get_action_session()
        except Exception:
            return None

        if not session.candidates and not session.current_intent:
            return None  # No prior context

        text_l = text.lower().strip()

        for entry in _FOLLOWUP_PATTERNS:
            for pat in entry["patterns"]:
                m = re.search(pat, text_l, re.IGNORECASE)
                if m:
                    # Inherit domain from current session
                    current_intent = session.current_intent or {}
                    domain = current_intent.get("domain", "shopping")
                    action = entry["action"]

                    if action == "select":
                        # Resolve the selection reference
                        selected = session.resolve_candidate_reference(text_l)
                        if selected and domain == "shopping":
                            return IntentModel(
                                domain="shopping", action="open",
                                target=selected.get("label", text),
                                parameters={"candidate": selected},
                                confidence=0.85,
                                risk_level=RiskLevel.LOW_RISK.value,
                                raw_text=text,
                                is_followup=True,
                            )
                        if selected and domain == "file":
                            return IntentModel(
                                domain="file", action="open",
                                target=selected.get("path", text),
                                confidence=0.85,
                                risk_level=RiskLevel.LOW_RISK.value,
                                raw_text=text,
                                is_followup=True,
                            )
                        if selected and domain == "media":
                            return IntentModel(
                                domain="media", action="play",
                                target=selected.get("label", text),
                                parameters={"candidate": selected},
                                confidence=0.85,
                                risk_level=RiskLevel.LOW_RISK.value,
                                raw_text=text,
                                is_followup=True,
                            )

                    if action == "filter":
                        from action.constraint_extractor import get_constraint_extractor
                        constraints = get_constraint_extractor().extract(text)
                        return IntentModel(
                            domain=domain, action="filter",
                            target=text,
                            constraints=constraints,
                            confidence=0.80,
                            risk_level=RiskLevel.LOW_RISK.value,
                            raw_text=text,
                            is_followup=True,
                        )

                    if action == "recommend":
                        return IntentModel(
                            domain=domain, action="recommend",
                            target=text,
                            confidence=0.80,
                            risk_level=RiskLevel.LOW_RISK.value,
                            raw_text=text,
                            is_followup=True,
                        )

        return None

    # ── Confirmation gate ─────────────────────────────────────────────────────

    def _is_confirmation(self, text: str) -> bool:
        t = text.lower().strip()
        return any(w in t for w in [
            "yes", "confirm", "proceed", "go ahead", "do it", "sure", "ok", "okay",
            "yeah", "yep", "approve"
        ])

    def _is_cancellation(self, text: str) -> bool:
        t = text.lower().strip()
        return any(w in t for w in [
            "no", "cancel", "stop", "abort", "nevermind", "never mind", "don't", "nope", "nah"
        ])

    def _execute_confirmed_action(self, payload: Dict[str, Any], session: Any) -> ActionResult:
        """Execute a previously HIGH_RISK-gated action after user confirmation."""
        session.clear_pending_confirmation()
        from action.action_session import save_action_session
        save_action_session(session)
        # Currently only shopping_purchase reaches here
        action = payload.get("action", "unknown")
        return ActionResult(
            success=True, domain="shopping", action=action,
            target=payload.get("item_name", ""),
            message=f"Confirmed. Proceeding with {action} for '{payload.get('item_name', '')}'.",
            verified=False,  # No further automation — user must complete checkout manually
        )

    # ── Deep Integration Subsystems ───────────────────────────────────────────

    def _integrate_post_execution(self, intent: IntentModel, result: ActionResult, session: Any):
        """Phase 10: Deep Integration with Vivy Subsystems."""
        # 1. AGI Cognitive Architecture (Blackboard)
        try:
            from agi.blackboard import get_cognitive_blackboard
            bb = get_cognitive_blackboard()
            bb.publish_state("active_action", result.to_dict(), source_engine="ActionSystem")
        except Exception:
            pass

        # 3. Intelligent Memory Scoring & Filtering
        try:
            from action.action_memory_scorer import get_action_scorer
            scorer = get_action_scorer()
            score, category = scorer.score_action(intent, result, session)
            
            # Emit telemetry for all actions
            self._publish_event("action.telemetry", {
                "domain": intent.domain, "action": intent.action, "target": intent.target,
                "success": result.success, "score": score, "category": category
            })
            
            if category == "memory":
                # High-value experience: write to MemoryOrchestrator
                try:
                    from memory_orchestrator import get_memory_orchestrator
                    mem_orch = get_memory_orchestrator()
                    mem_orch._memory_data.setdefault("events", []).append({
                        "timestamp": time.time(),
                        "type": "action_execution_experience",
                        "domain": intent.domain,
                        "action": intent.action,
                        "target": intent.target,
                        "success": result.success,
                        "learning_value": score
                    })
                    mem_orch.save_memory()
                    
                    from memory_ml_engine import get_memory_ml_engine
                    ml_eng = get_memory_ml_engine()
                    if ml_eng and getattr(ml_eng, "is_ready", False):
                        ml_eng.add_memory(f"Significant Action Experience: '{intent.action}' on '{intent.target}'. Success: {result.success}")
                except Exception as _mem_err:
                    pass
            elif category == "aggregate":
                # Medium-value: update pattern counts in MemoryOrchestrator
                try:
                    from memory_orchestrator import get_memory_orchestrator
                    mem_orch = get_memory_orchestrator()
                    patterns = mem_orch._memory_data.setdefault("action_patterns", {})
                    key = f"{intent.domain}_{intent.action}_{intent.target}"
                    if key not in patterns:
                        patterns[key] = {"count": 1, "last_used": time.time()}
                    else:
                        patterns[key]["count"] += 1
                        patterns[key]["last_used"] = time.time()
                    # Promote to preference if count hits threshold
                    if patterns[key]["count"] == 5:
                        mem_orch._memory_data.setdefault("user_preferences", {})[f"preferred_{intent.domain}_{intent.action}"] = intent.target
                    mem_orch.save_memory()
                except Exception as _agg_err:
                    pass
        except Exception as _scorer_err:
            pass
            
        # 6. Neural Prediction Engine
        if result.success and not result.requires_confirmation:
            try:
                from neural.neural_orchestrator import get_neural_orchestrator
                get_neural_orchestrator().log_action_vector(intent.domain, intent.action, intent.target)
            except Exception:
                pass

        # 2. Self-Evolution
        if not result.success:
            try:
                from evolution.perception_layer import get_perception_layer, Experience
                from evolution.adaptation_engine import get_adaptation_engine
                perc = get_perception_layer()
                exp = Experience(
                    experience_id=f"act_err_{int(time.time()*1000)}",
                    timestamp=time.time(),
                    input_text=intent.raw_text,
                    output_text=result.message,
                    feature_vector=[0.0, 1.0, 0.0], # Failed action vector
                    feedback_score=0.1
                )
                perc.record_experience(exp)
                get_adaptation_engine().process_adaptation_step()
            except Exception:
                pass

    # ── EventBus integration ──────────────────────────────────────────────────

    def _publish_event(self, topic: str, payload: Dict[str, Any]) -> None:
        """Publish action lifecycle event to existing EventBus."""
        try:
            from agi.bus.event_bus import get_event_bus
            get_event_bus().publish(topic, payload)
        except Exception:
            pass  # Silenced — event bus is optional observability

    # ── Health / telemetry ────────────────────────────────────────────────────

    def get_health(self) -> Dict[str, Any]:
        from action.capability_registry import get_capability_registry
        return {
            "enabled": self._enabled,
            "registered_capabilities": get_capability_registry().count(),
            "capabilities": get_capability_registry().get_health(),
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

def get_smart_manager() -> SmartManager:
    return SmartManager.get_instance()
