"""
perception/gesture_state_machine.py
===================================
Vivy AI - Air Gesture State Machine
Handles debouncing and state transitions for recognized gestures to prevent event storms.
(IDLE -> CANDIDATE -> CONFIRMED -> COOLDOWN -> IDLE)
"""

import time
import logging

from perception.gesture_suppression_gate import GestureSuppressionGate

logger = logging.getLogger(__name__)

class GestureStateMachine:
    def __init__(self, debounce_frames: int = 10, cooldown_seconds: float = 1.0):
        self.state = "IDLE"
        self.current_gesture = None
        
        # Replaced frames_detected with candidate_start_time for timestamp-based confirmation
        self.candidate_start_time = 0.0
        self.last_confirmed_time = 0.0
        self.cooldown_seconds = cooldown_seconds
        
        self.suppression_gate = GestureSuppressionGate()
        
        self.pending_combo = None
        self.pending_combo_time = 0.0
        self.pending_combo_meta = None
        self.combo_window = 1.0
        self.emitted_queue = []
        
        # Track history of recently confirmed gestures for double-tap detection
        self.history_queue = []
        self.frames_lost = 0
        
        # Bug #2 fix: proper miss counter for CANDIDATE state
        # Allows up to N consecutive missed frames before dropping to IDLE
        self.candidate_miss_count = 0
        self.candidate_miss_tolerance = 4  # frames (~133ms at 30fps)
        
        self.last_fired_times = {}
        
        try:
            import json, os
            cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "vivy_config.json")
            if os.path.exists(cfg_path):
                with open(cfg_path, "r") as f:
                    cfg = json.load(f)
                    self.combo_window = cfg.get("gesture", {}).get("combo", {}).get("window_ms", 1000) / 1000.0
        except Exception:
            pass
        
        # Temporal confirmation thresholds in seconds (replacing frame counts)
        self.gesture_thresholds_sec = {
            "SWIPE_LEFT": 0.0,
            "SWIPE_RIGHT": 0.0,
            "SWIPE_UP": 0.0,
            "SWIPE_DOWN": 0.0,
            "PINCH_MOVE_UP": 0.0,
            "PINCH_MOVE_DOWN": 0.0,
            "PINCH_MOVE_LEFT": 0.0,
            "PINCH_MOVE_RIGHT": 0.0,
            "FIST_MOVE_UP": 0.0,
            "FIST_MOVE_DOWN": 0.0,
            "FIST_MOVE_LEFT": 0.0,
            "FIST_MOVE_RIGHT": 0.0,
            "TWO_FINGERS_MOVE_UP": 0.0,
            "TWO_FINGERS_MOVE_DOWN": 0.0,
            "TWO_FINGERS_MOVE_LEFT": 0.0,
            "TWO_FINGERS_MOVE_RIGHT": 0.0,
            "WAVE": 0.2,
            "PUSH": 0.0,
            "PULL": 0.0,
            "POINT_MOVE_UP": 0.0,
            "POINT_MOVE_DOWN": 0.0,
            "POINT_MOVE_LEFT": 0.0,
            "POINT_MOVE_RIGHT": 0.0,
            "TWO_FINGERS_PUSH": 0.0,
            "PALM_MOVE_UP": 0.0,
            "PALM_MOVE_DOWN": 0.0,
            # Static Gestures require a firm temporal hold (0.1s is the minimum for stability, can scale up dynamically)
            "OPEN_PALM": 0.15,
            "FIST": 0.15,
            "THUMBS_UP": 0.15,
            "THUMBS_DOWN": 0.15,
            "OK_SIGN": 0.15,
            "POINT": 0.15,
            "PINCH": 0.15,
            "PALM_GRAB": 0.15,
            "CLAP": 0.15,
            "SHAKA": 0.15,
            "PEACE": 0.15
        }
        
        # Dynamic cooldowns to prevent locking the system for too long.
        # Bug #1 fix: removed duplicate keys (OPEN_PALM, FIST, THUMBS_UP, THUMBS_DOWN, OK_SIGN
        # previously appeared twice; the 2.0s entries silently overwrote to 0.5s anyway).
        # Now consolidated into a single clean dict with correct responsive values.
        self.gesture_cooldowns = {
            # Static gesture cooldowns (must re-hold to re-trigger)
            "OPEN_PALM": 0.5,
            "FIST": 0.5,
            "THUMBS_UP": 0.5,
            "THUMBS_DOWN": 0.5,
            "OK_SIGN": 0.5,
            "POINT": 0.5,
            "PINCH": 0.5,
            "PALM_GRAB": 0.5,
            "CLAP": 0.5,
            "SHAKA": 0.5,
            # Swipe gesture cooldowns (short to allow rapid re-swipe)
            "SWIPE_LEFT": 0.3,
            "SWIPE_RIGHT": 0.3,
            "SWIPE_UP": 0.3,
            "SWIPE_DOWN": 0.3,
            # Continuous movement gesture cooldowns (very short for smooth repeated actions)
            "PINCH_MOVE_UP": 0.15,
            "PINCH_MOVE_DOWN": 0.15,
            "PINCH_MOVE_LEFT": 0.25,
            "PINCH_MOVE_RIGHT": 0.25,
            "FIST_MOVE_UP": 0.15,
            "FIST_MOVE_DOWN": 0.15,
            "FIST_MOVE_LEFT": 0.25,
            "FIST_MOVE_RIGHT": 0.25,
            "TWO_FINGERS_MOVE_UP": 0.15,
            "TWO_FINGERS_MOVE_DOWN": 0.15,
            "TWO_FINGERS_MOVE_LEFT": 0.25,
            "TWO_FINGERS_MOVE_RIGHT": 0.25,
            "PALM_MOVE_UP": 0.15,
            "PALM_MOVE_DOWN": 0.15,
            "POINT_MOVE_UP": 0.35,
            "POINT_MOVE_DOWN": 0.35,
            "POINT_MOVE_LEFT": 0.25,
            "POINT_MOVE_RIGHT": 0.25,
        }

    def process_frame(self, detected_gesture: str, metadata: dict = None) -> tuple[str, str, bool, dict]:
        """
        Process a single frame's detected gesture.
        Returns: (state, current_gesture, is_newly_confirmed, metadata)
        """
        now = time.time()
        
        # Check for gesture suppression via Object-in-hand
        holding_item = metadata.get("holding_item", False) if metadata else False
        gate_state = self.suppression_gate.process_frame(holding_item)
        
        if self.suppression_gate.is_suppressed():
            self.state = "GESTURE_SUPPRESSED"
            self.current_gesture = "OBJECT_IN_HAND"
            self.candidate_miss_count = 0
            self.frames_lost = 0
            return (self.state, self.current_gesture, False, metadata)
        elif self.state == "GESTURE_SUPPRESSED":
            # Bug #7 fix: emitted_queue was never populated, so pop() always crashed.
            # Suppressed gestures are correctly dropped (not queued). Simply return to IDLE.
            self.state = "IDLE"
            self.current_gesture = None
            self.candidate_miss_count = 0
            return (self.state, None, False, metadata)
        
        if self.pending_combo:
            if now - self.pending_combo_time > self.combo_window:
                expired = self.pending_combo
                expired_meta = self.pending_combo_meta
                self.pending_combo = None
                self.pending_combo_meta = None
                self.state = "COOLDOWN"
                self.last_confirmed_time = now
                # Emit fallbacks
                if expired == "SWIPE_DOWN":
                    return ("CONFIRMED", "SHOW_DESKTOP", True, expired_meta)
                elif expired == "SWIPE_UP":
                    return ("CONFIRMED", "TASK_VIEW", True, expired_meta)
                return ("CONFIRMED", expired, True, expired_meta)
        
        if self.state == "COOLDOWN":
            active_cooldown = self.gesture_cooldowns.get(self.current_gesture, self.cooldown_seconds)
            if now - self.last_confirmed_time >= active_cooldown:
                self.state = "IDLE"
                self.current_gesture = None
            else:
                return (self.state, self.current_gesture, False, metadata)

        if not detected_gesture or detected_gesture == "UNKNOWN":
            # If nothing detected, apply miss tolerance before dropping back to IDLE.
            if self.state == "CANDIDATE":
                # Bug #2 fix: the old logic (candidate_start_time += 0.05) was inverted:
                # adding to start_time always made `now < candidate_start_time` true immediately,
                # resetting to IDLE on the very first missed frame.
                # Now uses a proper miss counter with tolerance for camera jitter/motion blur.
                self.candidate_miss_count += 1
                if self.candidate_miss_count > self.candidate_miss_tolerance:
                    self.state = "IDLE"
                    self.current_gesture = None
                    self.candidate_miss_count = 0
            elif self.state == "CONFIRMED":
                self.frames_lost += 1
                if self.frames_lost > 3:
                    self.state = "IDLE"
                    self.current_gesture = None
                    self.frames_lost = 0
            return (self.state, self.current_gesture, False, metadata)

        # We have a valid detection — reset miss counter since we got a real frame
        self.candidate_miss_count = 0
        
        if self.state == "IDLE":
            self.state = "CANDIDATE"
            self.current_gesture = detected_gesture
            self.candidate_start_time = now
            return (self.state, self.current_gesture, False, metadata)

        if self.state == "CANDIDATE":
            if self.current_gesture == detected_gesture:
                threshold = self.gesture_thresholds_sec.get(detected_gesture, 0.15)
                
                if (now - self.candidate_start_time) >= threshold:
                    active_cooldown = self.gesture_cooldowns.get(detected_gesture, self.cooldown_seconds)
                    if now - self.last_fired_times.get(detected_gesture, 0) < active_cooldown:
                        return (self.state, self.current_gesture, False, metadata)

                    self.state = "CONFIRMED"
                    self.last_confirmed_time = now
                    self.last_fired_times[detected_gesture] = now
                    
                    # --- Combo Check: SWIPE_DOWN/UP followed by SWIPE_LEFT/RIGHT = Desktop switch ---
                    if detected_gesture in ["SWIPE_DOWN", "SWIPE_UP"]:
                        self.pending_combo = detected_gesture
                        self.pending_combo_time = now
                        self.pending_combo_meta = dict(metadata) if metadata else {}
                        self.state = "IDLE"
                        self.current_gesture = None
                        return (self.state, None, False, metadata)
                        
                    if self.pending_combo in ["SWIPE_DOWN", "SWIPE_UP"]:
                        if self.current_gesture == "SWIPE_LEFT":
                            self.pending_combo = None
                            meta_copy = dict(metadata) if metadata else {}
                            return (self.state, "PREVIOUS_DESKTOP", True, meta_copy)
                        elif self.current_gesture == "SWIPE_RIGHT":
                            self.pending_combo = None
                            meta_copy = dict(metadata) if metadata else {}
                            return (self.state, "NEXT_DESKTOP", True, meta_copy)
                        else:
                            # Unrelated gesture cleared the combo
                            self.pending_combo = None
                            self.pending_combo_meta = None
                    
                    # --- Combo Check: Grab (Open Palm -> Fist) ---
                    # Only allow FIST to trigger PALM_GRAB if OPEN_PALM was confirmed recently (< 1.0s)
                    self.history_queue = [(g, t) for g, t in self.history_queue if now - t < 1.0]
                    if self.current_gesture == "FIST":
                        if self.history_queue and self.history_queue[-1][0] == "OPEN_PALM":
                            self.history_queue.clear()
                            # Override the confirmed gesture with PALM_GRAB
                            return (self.state, "PALM_GRAB", True, metadata)
                                
                    # Store in history for future combo checks
                    if not self.history_queue or self.current_gesture != self.history_queue[-1][0]:
                        self.history_queue.append((self.current_gesture, now))
                    else:
                        # Update timestamp if it's the same gesture
                        self.history_queue[-1] = (self.current_gesture, now)
                        
                    return (self.state, self.current_gesture, True, metadata) # newly confirmed
            else:
                # Gesture changed before confirmation. Switch tracking and reset miss count.
                self.current_gesture = detected_gesture
                self.candidate_start_time = now
                self.candidate_miss_count = 0
                
        elif self.state == "CONFIRMED":
            # If they hold it, stay in confirmed but do not re-trigger.
            if self.current_gesture == detected_gesture:
                self.frames_lost = 0
            else:
                is_dynamic = any(x in (detected_gesture or "") for x in ["MOVE", "SWIPE", "PUSH", "PULL", "CLAP"])
                is_grab = (self.current_gesture == "OPEN_PALM" and detected_gesture == "FIST")
                
                # Dynamic gestures and intentional grabs break the lock immediately
                if is_dynamic or is_grab:
                    self.frames_lost = 999
                else:
                    self.frames_lost += 1
                    
                # Reduced from 3 → 1: with static→static transitions, 3 frames (≈100ms)
                # is enough for a transitional pose to confirm and fire a wrong action.
                # 1 frame gives one grace frame for motion blur but no longer.
                if self.frames_lost > 1:
                    if is_grab or is_dynamic:
                        self.state = "IDLE"
                        self.current_gesture = None
                    else:
                        self.state = "COOLDOWN"
                        self.last_confirmed_time = now
                    self.frames_lost = 0
                
        return (self.state, self.current_gesture, False, metadata)
