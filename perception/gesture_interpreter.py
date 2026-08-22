"""
perception/gesture_interpreter.py
=================================
Vivy AI - Air Gesture Interpreter
Listens to confirmed gestures and maps them to cognitive action intents via SmartManager.
"""

import logging
from typing import Dict, Any, Optional
import time

from perception.perception_events import get_event_hub, EVENT_GESTURE_CONFIRMED
from action.smart_manager import get_smart_manager
from action.intent_model import IntentModel, RiskLevel
from agi.blackboard import get_cognitive_blackboard

logger = logging.getLogger(__name__)

from enum import Enum, auto

class TaskViewState(Enum):
    NORMAL = auto()
    ENTERING = auto()
    ACTIVE = auto()
    EXITING = auto()

class GestureInterpreter:
    _instance: Optional["GestureInterpreter"] = None
    
    def __init__(self):
        self.event_hub = get_event_hub()
        self.smart_manager = get_smart_manager()
        self.blackboard = get_cognitive_blackboard()
        self.event_hub.subscribe(EVENT_GESTURE_CONFIRMED, self._on_gesture_confirmed)
        
        # Task View Mode: Enum based state machine
        self._task_view_state = TaskViewState.NORMAL
        self._task_view_opened_at = 0.0
        
        logger.info("[GestureInterpreter] Subscribed to confirmed gestures.")

    @classmethod
    def get_instance(cls) -> "GestureInterpreter":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _on_gesture_confirmed(self, event_type: str, payload: Dict[str, Any]):
        gesture = payload.get("gesture", "UNKNOWN")
        hand = payload.get("hand_label", "Unknown")
        
        logger.info(f"[GestureInterpreter] Received CONFIRMED gesture: {gesture} from {hand} hand.")
        
        intent = self._map_gesture_to_intent(gesture)
        if intent:
            # Inject to SmartManager for full risk-gated execution
            logger.info(f"[GestureInterpreter] Routing mapped intent '{intent.action}' to SmartManager.")
            self.smart_manager.handle(
                text=f"[Gesture] {gesture}", 
                context={"source": "gesture", "hand": hand},
                predetected_intent=intent
            )

    def _map_gesture_to_intent(self, gesture: str) -> Optional[IntentModel]:
        """Maps a static/dynamic gesture to a structured action intent."""
        
        # Pull current active context from AGI blackboard (e.g., if a browser or media is open)
        try:
            active_action = self.blackboard.get_state("active_action") or {}
        except Exception:
            active_action = {}
            
        domain = active_action.get("domain", "system")
        
        # Fetch contextual mapping rules provided by the active executor/domain
        context_rules = self.blackboard.get_state("gesture_context_rules") or {}
        
        semantic_gestures = [
            "OK_SIGN", "POINT", "PINCH", "OPEN_PALM", "FIST", 
            "THUMBS_UP", "THUMBS_DOWN", "SHAKA", "TWO_FINGERS"
        ]
        
        # 1. Blackboard Context Rules Override (e.g., Gaming Context)
        if gesture in semantic_gestures or "MOVE" in gesture or "SWIPE" in gesture:
            rule = context_rules.get(gesture)
            if rule:
                return IntentModel(
                    domain=rule.get("domain", "system"),
                    action=rule.get("action", "no_op"),
                    target=rule.get("target", "unknown"),
                    source="local_only",
                    confidence=rule.get("confidence", 0.9),
                    risk_level=RiskLevel.LOW_RISK.value,
                    raw_text=f"[Gesture] {gesture}"
                )
        
        # 2. Hardcoded Core Gesture Dictionary (Fallback)
        # --- Capture ---
        if gesture == "PALM_GRAB":
            return IntentModel(domain="system", action="screenshot", target="screen", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Screenshot")
        elif gesture == "CLAP":
            return IntentModel(domain="system", action="toggle_recording", target="screen", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Screen Record")
            
        # --- Navigation ---
        elif gesture == "POINT_MOVE_UP":
            if self._task_view_state == TaskViewState.ACTIVE:
                # Already open — ignore re-triggers to prevent toggle-close
                logger.debug("[GestureInterpreter] Task View already open, suppressing re-trigger.")
                return None
            self._task_view_state = TaskViewState.ACTIVE
            self._task_view_opened_at = time.time()
            return IntentModel(domain="system", action="task_view", target="desktop", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Task View")
        
        elif gesture == "POINT_MOVE_LEFT":
            if self._task_view_state == TaskViewState.ACTIVE:
                return None # Suppress outside navigation
            action = "previous_tab" if domain == "browser" else "previous_app"
            return IntentModel(domain=domain, action=action, target="app", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Point Left")
        
        elif gesture == "POINT_MOVE_RIGHT":
            if self._task_view_state == TaskViewState.ACTIVE:
                return None # Suppress outside navigation
            action = "next_tab" if domain == "browser" else "next_app"
            return IntentModel(domain=domain, action=action, target="app", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Point Right")
        
        elif gesture == "POINT_MOVE_DOWN":
            if self._task_view_state == TaskViewState.ACTIVE:
                time_since_open = time.time() - self._task_view_opened_at
                if time_since_open < 1.5:
                    # IGNORING: User is just returning their hand down after pointing up
                    logger.debug(f"[GestureInterpreter] Ignoring downward return movement (Time: {time_since_open:.2f}s).")
                    return None
                
                # Close task view cleanly using Escape
                self._task_view_state = TaskViewState.NORMAL
                return IntentModel(domain="system", action="escape", target="ui", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Close Task View")
            return IntentModel(domain="system", action="show_desktop", target="desktop", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Show Desktop")
            
        elif gesture == "TWO_FINGERS_MOVE_LEFT":
            if self._task_view_state == TaskViewState.ACTIVE:
                return IntentModel(domain="system", action="task_view_prev", target="desktop", source="local_only", confidence=0.95, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Task View Prev (2 Fingers)")
            return None
            
        elif gesture == "TWO_FINGERS_MOVE_RIGHT":
            if self._task_view_state == TaskViewState.ACTIVE:
                return IntentModel(domain="system", action="task_view_next", target="desktop", source="local_only", confidence=0.95, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Task View Next (2 Fingers)")
            return None
            
        elif gesture == "TWO_FINGERS_PUSH":
            if self._task_view_state == TaskViewState.ACTIVE:
                self._task_view_state = TaskViewState.NORMAL
                return IntentModel(domain="system", action="task_view_select", target="desktop", source="local_only", confidence=0.95, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Task View Select (Push)")
            return None
        
        elif gesture == "SWIPE_LEFT":
            if self._task_view_state == TaskViewState.ACTIVE:
                logger.debug("[GestureInterpreter] Suppressing SWIPE_LEFT while in Task View mode.")
                return None
            action = "previous_tab" if domain == "browser" else "previous_app"
            return IntentModel(domain=domain, action=action, target="app", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Swipe Left")
            
        elif gesture == "SWIPE_RIGHT":
            if self._task_view_state == TaskViewState.ACTIVE:
                logger.debug("[GestureInterpreter] Suppressing SWIPE_RIGHT while in Task View mode.")
                return None
            action = "next_tab" if domain == "browser" else "next_app"
            return IntentModel(domain=domain, action=action, target="app", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Swipe Right")
        elif gesture == "PREVIOUS_DESKTOP":
            return IntentModel(domain="system", action="previous_desktop", target="desktop", source="local_only", confidence=1.0, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Previous Desktop")
        elif gesture == "NEXT_DESKTOP":
            return IntentModel(domain="system", action="next_desktop", target="desktop", source="local_only", confidence=1.0, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Next Desktop")
            
        # --- Media & Reading ---
        elif gesture == "OPEN_PALM":
            return IntentModel(domain="media", action="play_pause", target="media", source="local_only", confidence=0.85, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Play/Pause")
        elif gesture == "SHAKA":
            return IntentModel(domain="system", action="mute_toggle", target="audio", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Mute")
        elif gesture == "PINCH_MOVE_UP":
            return IntentModel(domain="system", action="volume_up", target="audio", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Vol Up")
        elif gesture == "PINCH_MOVE_DOWN":
            return IntentModel(domain="system", action="volume_down", target="audio", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Vol Down")
        elif gesture == "PINCH_MOVE_RIGHT":
            return IntentModel(domain="media", action="seek_forward", target="media", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Seek Forward")
        elif gesture == "PINCH_MOVE_LEFT":
            return IntentModel(domain="media", action="seek_back", target="media", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Seek Back")
        elif gesture == "FIST_MOVE_RIGHT":
            return IntentModel(domain="media", action="next_track", target="media", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Next Track")
        elif gesture == "FIST_MOVE_LEFT":
            return IntentModel(domain="media", action="previous_track", target="media", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Prev Track")
        elif gesture == "PALM_MOVE_UP":
            return IntentModel(domain="system", action="scroll_up", target="ui", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Scroll Up")
        elif gesture == "PALM_MOVE_DOWN":
            return IntentModel(domain="system", action="scroll_down", target="ui", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Scroll Down")
            
        # --- General ---
        elif gesture == "OK_SIGN":
            return IntentModel(domain="system", action="confirm", target="ui", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Confirm")
        elif gesture == "THUMBS_UP":
            return IntentModel(domain="system", action="like", target="ui", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Like/Accept")
        elif gesture == "THUMBS_DOWN":
            return IntentModel(domain="system", action="cancel", target="ui", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Cancel/Reject")
        elif gesture == "FIST":
            return IntentModel(domain="system", action="escape", target="ui", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Escape")
        elif gesture == "POINT":
            if self._task_view_state == TaskViewState.ACTIVE:
                logger.debug("[GestureInterpreter] Suppressing POINT click while in Task View mode.")
                return None
            return IntentModel(domain="system", action="click", target="ui", source="local_only", confidence=0.9, risk_level=RiskLevel.LOW_RISK.value, raw_text="[Gesture] Click")
        
        return None

def get_gesture_interpreter() -> GestureInterpreter:
    return GestureInterpreter.get_instance()
