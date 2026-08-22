"""
perception/gesture_engine.py
============================
Vivy AI - Air Gesture Recognition Engine
Analyzes raw MediaPipe hand landmarks to classify static and dynamic gestures.
"""

import math
import logging
from collections import deque

from perception.gesture_state_machine import GestureStateMachine

logger = logging.getLogger(__name__)

class TrajectoryTracker:
    def __init__(self, history_size=45, ema_alpha=0.35):
        # EMA alpha=0.35 is used for POSITION SMOOTHING (noise filtering).
        # The history stores BOTH raw position (for accurate displacement) AND
        # EMA position (for smooth z-depth push/pull estimation).
        # This prevents EMA under-convergence from masking real swipe displacement.
        self.history = deque(maxlen=history_size)
        self.ema_alpha = ema_alpha
        self.ema_x = None
        self.ema_y = None
        self.ema_size = None
    
    def add_point(self, x: float, y: float, timestamp: float, hand_size: float = 0.0):
        if self.ema_x is None:
            self.ema_x, self.ema_y, self.ema_size = x, y, hand_size
        else:
            self.ema_x = self.ema_alpha * x + (1 - self.ema_alpha) * self.ema_x
            self.ema_y = self.ema_alpha * y + (1 - self.ema_alpha) * self.ema_y
            self.ema_size = self.ema_alpha * hand_size + (1 - self.ema_alpha) * self.ema_size
        
        # Store (raw_x, raw_y, timestamp, ema_size, ema_x, ema_y)
        # raw x,y used for displacement (accurate); ema_size used for z-depth push/pull.
        self.history.append((x, y, timestamp, self.ema_size, self.ema_x, self.ema_y))
    
    def clear(self):
        self.history.clear()
        self.ema_x = None
        self.ema_y = None
        self.ema_size = None
        
    def detect_swipe(self, min_distance_scalar=1.2, max_duration=0.4, min_speed=0.08) -> tuple[str, float]:
        """Detect rapid linear movement by finding max displacement in history.
        
        Uses RAW positions for dx/dy (accurate displacement) and EMA size for dz (smooth depth).
        min_distance_scalar: swipe must travel this multiple of hand_size
        max_duration: only consider points within this many seconds
        min_speed: minimum normalized speed (units/s) to qualify as intentional movement
        """
        if len(self.history) < 3:
            return "", 0.0
        
        # Unpack current point: (raw_x, raw_y, timestamp, ema_size, ema_x, ema_y)
        # Support both old 4-tuple and new 6-tuple format for backward compatibility
        end_entry = self.history[-1]
        end_x, end_y, end_t = end_entry[0], end_entry[1], end_entry[2]
        end_size = end_entry[3]  # ema_size for z-depth
        
        best_dx, best_dy, best_dz = 0, 0, 0
        best_duration = 0.1
        max_dist_sq = 0
        max_dz_abs = 0
        in_window_count = 0
        
        # Scan history for the point of maximum displacement relative to current frame
        for i in range(len(self.history) - 1):
            h_entry = self.history[i]
            hx, hy, ht, hsize = h_entry[0], h_entry[1], h_entry[2], h_entry[3]
            duration = end_t - ht
            
            if duration > max_duration or duration <= 0:
                continue
            
            in_window_count += 1
            
            # Use raw x,y for displacement (accurate, not EMA-attenuated)
            dx = end_x - hx
            dy = end_y - hy
            # Use EMA size for z-depth estimation (benefits from smoothing)
            dz = end_size - hsize
            dist_sq = dx*dx + dy*dy
            
            if dist_sq > max_dist_sq:
                max_dist_sq = dist_sq
                best_dx = dx
                best_dy = dy
                best_duration = duration
                
            if abs(dz) > max_dz_abs:
                max_dz_abs = abs(dz)
                best_dz = dz
        
        # Require minimum 2 in-window comparison points for a valid swipe.
        # The loop compares history[0..N-2] against the endpoint (history[N-1]).
        # With 3 total history points, in_window_count can be at most 2.
        # This threshold prevents single-outlier false swipes (1 in-window point)
        # while correctly accepting real 3-point swipes (2 in-window comparisons).
        if in_window_count < 2:
            return "", 0.0
                
        # Scale-invariant thresholds based on hand size
        scaled_z_threshold = max(0.015, end_size * 0.3)
        
        # Evaluate Z-axis (Push/Pull) first if it's dominant
        if max_dz_abs > scaled_z_threshold and max_dz_abs > (abs(best_dx) * 0.5) and max_dz_abs > (abs(best_dy) * 0.5):
            speed = max_dz_abs / best_duration
            if best_dz > 0:
                return "PUSH", speed
            else:
                return "PULL", speed
        
        # A swipe must travel a distance relative to the hand's own size
        scaled_min_distance = max(0.03, end_size * min_distance_scalar)
        # Vertical swipes use 60% of the horizontal threshold (for smoother scroll detection).
        # The early-exit guard must use the SAME thresholds as the detection branches below,
        # otherwise valid vertical swipes get cut off before reaching the vertical branch.
        min_dist_y = scaled_min_distance * 0.6
        
        abs_dx = abs(best_dx)
        abs_dy = abs(best_dy)
        
        # Exit early only if BOTH thresholds fail (using axis-specific minimums)
        if abs_dx < scaled_min_distance and abs_dy < min_dist_y:
            return "", 0.0
            
        dist = math.sqrt(max_dist_sq)
        speed = dist / max(0.01, best_duration)
        
        # Minimum speed guard: slow drift must not cancel static gesture candidates
        if speed < min_speed:
            return "", 0.0
            
        # Determine dominant axis
        if abs_dx > abs_dy:
            if best_dx > scaled_min_distance:
                return "SWIPE_RIGHT", speed
            elif best_dx < -scaled_min_distance:
                return "SWIPE_LEFT", speed
        else:
            # min_dist_y already computed above at 60% of horizontal threshold
            if best_dy > min_dist_y:
                return "SWIPE_DOWN", speed
            elif best_dy < -min_dist_y:
                return "SWIPE_UP", speed
                
        return "", 0.0

class GestureEngine:
    def __init__(self):
        self.state_machine = GestureStateMachine()
        self.trajectory = TrajectoryTracker()
        self.last_valid_static = "UNKNOWN"
        # Bug #3 & #4 fix: track previous SM state to detect transitions to IDLE
        # so we can clear trajectory history and reset last_valid_static
        self._prev_sm_state = "IDLE"
        
    def process_hand(self, hand_landmarks=None, handedness_label: str = "Right", w: int = 640, h: int = 480, timestamp: float = 0.0, x_coords: list = None, y_coords: list = None, holding_item: bool = False) -> tuple[str, str, float, bool]:
        """
        Process single hand landmarks.
        Returns (final_gesture, phase, confidence, newly_confirmed)
        """
        # Extract normalized (0..1) coords from hand_landmarks if provided
        if hand_landmarks is not None and hasattr(hand_landmarks, 'landmark'):
            x_coords = [lm.x for lm in hand_landmarks.landmark]
            y_coords = [lm.y for lm in hand_landmarks.landmark]

        if not x_coords or not y_coords:
            state, gest, _, _ = self.state_machine.process_frame("UNKNOWN", {"holding_item": holding_item})
            return gest or "UNKNOWN", state, 0.0, False

        # Calculate hand size using distance from wrist (0) to middle finger MCP (9)
        hand_size = math.hypot(x_coords[0] - x_coords[9], y_coords[0] - y_coords[9])

        # Add wrist point (normalized) to trajectory tracker
        self.trajectory.add_point(x_coords[0], y_coords[0], timestamp, hand_size)
        
        # 2. Check for dynamic gesture (movement direction)
        dynamic_gesture, speed = self.trajectory.detect_swipe()
        
        # 1. Classify static pose ONCE per frame
        static_gesture, confidence = self._classify_static(x_coords, y_coords, handedness_label)
        
        # Only update last_valid_static if NOT moving, to avoid motion blur garbage (e.g. blurred hand looks like FIST)
        if static_gesture != "UNKNOWN" and not dynamic_gesture:
            self.last_valid_static = static_gesture
            
        # Bug #3 & #4 fix: detect transition to IDLE from any non-IDLE state.
        # On IDLE transition: clear stale trajectory history (prevents phantom swipes)
        # and reset last_valid_static (prevents wrong movement gesture type on next attempt).
        current_sm_state = self.state_machine.state
        if current_sm_state == "IDLE" and self._prev_sm_state != "IDLE":
            self.trajectory.clear()
            self.last_valid_static = "UNKNOWN"
        self._prev_sm_state = current_sm_state
        
        if dynamic_gesture:
            if dynamic_gesture in ["PUSH", "PULL"]:
                direction = dynamic_gesture
            else:
                direction = dynamic_gesture.split('_')[1]  # UP, DOWN, LEFT, RIGHT
                
            # Base the dynamic action on what the user was holding before they started moving
            base_static = self.last_valid_static
            if self.state_machine.state in ["CONFIRMED", "CANDIDATE"] and self.state_machine.current_gesture:
                # Clean any previous move suffixes if they were re-evaluating
                base = self.state_machine.current_gesture
                for d in ["_MOVE_UP", "_MOVE_DOWN", "_MOVE_LEFT", "_MOVE_RIGHT", "_UP", "_DOWN", "_LEFT", "_RIGHT"]:
                    base = base.replace(d, "")
                # Clean SWIPE suffix
                if "SWIPE" in base:
                    base = "OPEN_PALM"
                if "PALM" in base:
                    base = "OPEN_PALM"
                base_static = base
            
            if base_static == "PINCH":
                final_gesture = f"PINCH_MOVE_{direction}" if direction not in ["PUSH", "PULL"] else f"PINCH_{direction}"
            elif base_static == "FIST":
                final_gesture = f"FIST_MOVE_{direction}" if direction not in ["PUSH", "PULL"] else f"FIST_{direction}"
            elif base_static == "POINT":
                final_gesture = f"POINT_MOVE_{direction}" if direction not in ["PUSH", "PULL"] else f"POINT_{direction}"
            elif base_static in ["TWO_FINGERS", "PEACE"]:
                final_gesture = f"TWO_FINGERS_MOVE_{direction}" if direction not in ["PUSH", "PULL"] else f"TWO_FINGERS_{direction}"
            elif base_static == "OPEN_PALM":
                if direction in ["UP", "DOWN", "PUSH", "PULL"]:
                    final_gesture = f"PALM_{direction}" if direction in ["PUSH", "PULL"] else f"PALM_MOVE_{direction}"
                else:
                    final_gesture = f"SWIPE_{direction}"
            else:
                final_gesture = f"SWIPE_{direction}" if direction not in ["PUSH", "PULL"] else f"PALM_{direction}"
                
            metadata = {"confidence": 0.95, "holding_item": holding_item}
            
            # [DEBUG TRACE]
            print(f"Dyn: {dynamic_gesture} | Base: {base_static} | Final: {final_gesture} | SM State: {self.state_machine.state} -> ", end="")
            
            state, gest, newly_confirmed, meta_out = self.state_machine.process_frame(final_gesture, metadata)
            
            print(f"{state} (New: {newly_confirmed})")
            
            if newly_confirmed:
                self.trajectory.clear()
                self.last_valid_static = "UNKNOWN"  # Bug #3 fix: reset after confirmed dynamic gesture
            out_conf = meta_out.get("confidence", 0.95) if meta_out else 0.95
            return gest, state, out_conf, newly_confirmed
        
        # 3. No movement: pass static gesture to state machine for debouncing
        metadata = {"confidence": confidence, "holding_item": holding_item}
        state, gest, newly_confirmed, meta_out = self.state_machine.process_frame(static_gesture, metadata)
        out_conf = meta_out.get("confidence", confidence) if meta_out else confidence
        return gest, state, out_conf, newly_confirmed
        
    def _classify_static(self, x: list, y: list, label: str) -> tuple[str, float]:
        """
        Heuristic classification based on finger joint states.
        Landmarks: 0: Wrist, 4: Thumb tip, 8: Index tip, 12: Middle tip, 16: Ring tip, 20: Pinky tip.
        MCP landmarks: 5=Index, 9=Middle, 13=Ring, 17=Pinky
        """
        # Intrinsic scale (Wrist to Middle Finger MCP)
        hand_scale = math.hypot(x[9] - x[0], y[9] - y[0])
        if hand_scale < 0.01:
            return "UNKNOWN", 0.0
            
        # Determine which fingers are extended using distance from wrist.
        # Cause 2 fix: all four fingers now use 1.5x threshold uniformly.
        # The previous 1.7x threshold for middle and ring was too strict — when the
        # hand is angled away from the camera (common pose), those fingers are
        # foreshortened in 2D projection and fall just below 1.7x, causing UNKNOWN.
        # 1.5x is validated as the correct threshold for all four fingers.
        index_ext  = math.hypot(x[8]  - x[0], y[8]  - y[0]) > (hand_scale * 1.5)
        middle_ext = math.hypot(x[12] - x[0], y[12] - y[0]) > (hand_scale * 1.5)
        ring_ext   = math.hypot(x[16] - x[0], y[16] - y[0]) > (hand_scale * 1.5)
        pinky_ext  = math.hypot(x[20] - x[0], y[20] - y[0]) > (hand_scale * 1.5)
        
        # Thumb extension invariant to mirroring/handedness:
        # Check if the tip (4) is further horizontally from the center (9) than the MCP (2)
        thumb_dir_x = x[2] - x[9]
        thumb_tip_x = x[4] - x[9]
        thumb_ext_x = (thumb_dir_x * thumb_tip_x > 0) and (abs(thumb_tip_x) > abs(thumb_dir_x))
        
        # Check if thumb is extended vertically (for thumbs up / thumbs down)
        thumb_vec_y = y[4] - y[2]
        thumb_ext_y = abs(thumb_vec_y) > (hand_scale * 0.3)
        
        thumb_ext = thumb_ext_x or thumb_ext_y
            
        extended_count = sum([index_ext, middle_ext, ring_ext, pinky_ext])
        
        # OPEN_PALM: 4 fingers clearly extended. Thumb is not mandatory — real palms often
        # have a slightly adducted thumb that does not pass the lateral-direction test.
        if extended_count == 4:
            return "OPEN_PALM", 0.85
            
        # Pinch geometry — check PINCH before OK_SIGN so pinch wins even when other fingers move.
        # Relax index_wrist_dist threshold: during pinch movement the index compresses slightly.
        pinch_dist = math.hypot(x[4] - x[8], y[4] - y[8])
        index_wrist_dist = math.hypot(x[8] - x[0], y[8] - y[0])
        is_pinching = (pinch_dist < hand_scale * 0.40) and (index_wrist_dist > hand_scale * 0.9)
        
        if is_pinching and not middle_ext and not ring_ext and not pinky_ext:
            return "PINCH", 0.90
            
        if is_pinching and middle_ext and ring_ext and pinky_ext:
            return "OK_SIGN", 0.90

        # Thumbs up/down: allow index to be slightly relaxed (which might trigger index_ext)
        # but middle, ring, pinky must be curled.
        if thumb_ext and not middle_ext and not ring_ext and not pinky_ext:
            if thumb_vec_y < -(hand_scale * 0.3):
                return "THUMBS_UP", 0.95
            if thumb_vec_y > (hand_scale * 0.3):
                return "THUMBS_DOWN", 0.95
                
        # If all fingers are curled, it's a fist
        if extended_count == 0:
            return "FIST", 0.85
            
        if index_ext and not middle_ext and not ring_ext and not pinky_ext:
            return "POINT", 0.90
            
        if index_ext and middle_ext and not ring_ext and not pinky_ext:
            if thumb_ext:
                return "TWO_FINGERS", 0.85
            return "PEACE", 0.85
            
        if not index_ext and not middle_ext and not ring_ext and pinky_ext and thumb_ext:
            return "SHAKA", 0.90

        return "UNKNOWN", 0.0
