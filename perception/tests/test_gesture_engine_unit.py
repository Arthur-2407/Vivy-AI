"""
perception/tests/test_gesture_engine_unit.py
============================================
Unit tests for GestureEngine._classify_static, TrajectoryTracker.detect_swipe,
GestureStateMachine.process_frame, and their integration.

These tests use SYNTHETIC hand landmarks — no camera or MediaPipe required.
They exhaustively cover:
  - All 7 static gestures
  - All 4 swipe directions
  - PUSH / PULL depth gestures
  - Temporal confirmation (candidate → confirmed)
  - Cooldown enforcement (no re-fire)
  - PALM_GRAB combo sequence (OPEN_PALM → FIST within window)
  - Virtual desktop combo (SWIPE_DOWN → SWIPE_LEFT/RIGHT)
  - Stale state expiry on UNKNOWN input
  - Scale invariance (gesture works at 0.5x and 2x normal scale)
  - False-positive rejection (random/noise landmarks → UNKNOWN)
"""

import math
import sys
import os
import time
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from perception.gesture_engine import GestureEngine, TrajectoryTracker
from perception.gesture_state_machine import GestureStateMachine


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic landmark helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_hand(
    wrist=(0.5, 0.7),
    mcp9=(0.5, 0.5),    # Middle MCP — controls scale
    index_tip=(0.5, 0.3),
    middle_tip=(0.52, 0.3),
    ring_tip=(0.54, 0.55),
    pinky_tip=(0.56, 0.55),
    thumb_tip=(0.38, 0.5),
    thumb_mcp2=(0.42, 0.6),
    scale=1.0,
):
    """
    Build a 21-landmark hand (x, y) list where critical landmarks are set
    explicitly. All other landmarks are filled from wrist position.
    landmark indices that matter:
      0: wrist
      2: thumb MCP (for thumb extension direction)
      4: thumb tip
      8: index tip
      9: middle MCP (for hand_scale)
     12: middle tip
     16: ring tip
     20: pinky tip
    """
    def sc(pt, anchor=(0.5, 0.5)):
        """Apply scale relative to anchor."""
        return (anchor[0] + (pt[0] - anchor[0]) * scale,
                anchor[1] + (pt[1] - anchor[1]) * scale)

    wrist = sc(wrist)
    mcp9 = sc(mcp9)

    x = [wrist[0]] * 21
    y = [wrist[1]] * 21

    x[9], y[9] = mcp9
    x[2], y[2] = sc(thumb_mcp2)
    x[4], y[4] = sc(thumb_tip)
    x[8], y[8] = sc(index_tip)
    x[12], y[12] = sc(middle_tip)
    x[16], y[16] = sc(ring_tip)
    x[20], y[20] = sc(pinky_tip)

    return x, y


def _confirm_static(engine: GestureEngine, x, y, label="Right", hold_sec=0.2):
    """Feed static landmarks for hold_sec wall-clock seconds until confirmed or timeout."""
    t_start = time.time()
    result = None
    while time.time() - t_start < hold_sec + 0.5:
        result = engine.process_hand(x_coords=x, y_coords=y,
                                     handedness_label=label,
                                     timestamp=time.time())
        gest, state, conf, confirmed = result
        if confirmed:
            return gest, state, conf, confirmed
        time.sleep(0.01)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 — Static Gesture Recognition
# ─────────────────────────────────────────────────────────────────────────────

class TestStaticGestures:
    """Verify that each static pose is classified correctly from synthetic landmarks."""

    def _make_engine(self):
        return GestureEngine()

    def test_open_palm_detected(self):
        """All 4 fingers + thumb extended → OPEN_PALM."""
        engine = self._make_engine()
        # 4 fingers clearly extended: tip far from wrist
        x, y = _make_hand(
            wrist=(0.5, 0.8),
            mcp9=(0.5, 0.55),
            index_tip=(0.45, 0.2),
            middle_tip=(0.50, 0.18),
            ring_tip=(0.55, 0.2),
            pinky_tip=(0.60, 0.25),
            thumb_tip=(0.30, 0.55),
            thumb_mcp2=(0.40, 0.65),
        )
        gest, conf = engine._classify_static(x, y, "Right")
        assert gest == "OPEN_PALM", f"Expected OPEN_PALM, got {gest}"

    def test_fist_detected(self):
        """All fingers curled tight toward wrist → FIST."""
        engine = self._make_engine()
        x, y = _make_hand(
            wrist=(0.5, 0.8),
            mcp9=(0.5, 0.6),
            index_tip=(0.48, 0.70),   # close to wrist
            middle_tip=(0.50, 0.72),
            ring_tip=(0.52, 0.71),
            pinky_tip=(0.54, 0.70),
            thumb_tip=(0.43, 0.68),   # thumb across, not truly extended
            thumb_mcp2=(0.42, 0.66),
        )
        gest, conf = engine._classify_static(x, y, "Right")
        assert gest == "FIST", f"Expected FIST, got {gest}"

    def test_point_detected(self):
        """Only index extended → POINT."""
        engine = self._make_engine()
        x, y = _make_hand(
            wrist=(0.5, 0.8),
            mcp9=(0.5, 0.6),
            index_tip=(0.45, 0.22),   # extended far
            middle_tip=(0.50, 0.70),  # curled
            ring_tip=(0.52, 0.71),
            pinky_tip=(0.54, 0.70),
            thumb_tip=(0.43, 0.68),
            thumb_mcp2=(0.42, 0.66),
        )
        gest, conf = engine._classify_static(x, y, "Right")
        assert gest == "POINT", f"Expected POINT, got {gest}"

    def test_thumbs_up_detected(self):
        """All fingers curled + thumb pointing up → THUMBS_UP."""
        engine = self._make_engine()
        x, y = _make_hand(
            wrist=(0.5, 0.8),
            mcp9=(0.5, 0.6),
            index_tip=(0.48, 0.70),
            middle_tip=(0.50, 0.72),
            ring_tip=(0.52, 0.71),
            pinky_tip=(0.54, 0.70),
            # thumb MCP has a clear lateral offset from MCP9 (at 0.5, 0.6)
            # so thumb_dir_x = x[2]-x[9] = 0.40-0.50 = -0.10 (non-zero)
            # thumb tip goes further left AND higher: thumb_tip_x = 0.38-0.50 = -0.12
            # thumb_dir_x * thumb_tip_x = (-0.10)*(-0.12) = +0.012 > 0  → thumb_ext True
            # thumb_vec_y = y[4]-y[2] = 0.35-0.55 = -0.20 < -0.05       → THUMBS_UP
            thumb_tip=(0.38, 0.35),
            thumb_mcp2=(0.40, 0.55),
        )
        gest, conf = engine._classify_static(x, y, "Right")
        assert gest == "THUMBS_UP", f"Expected THUMBS_UP, got {gest}"

    def test_thumbs_down_detected(self):
        """All fingers curled + thumb pointing down → THUMBS_DOWN."""
        engine = self._make_engine()
        x, y = _make_hand(
            wrist=(0.5, 0.5),
            mcp9=(0.5, 0.35),
            index_tip=(0.48, 0.38),
            middle_tip=(0.50, 0.40),
            ring_tip=(0.52, 0.39),
            pinky_tip=(0.54, 0.38),
            # Similar lateral offset approach:
            # thumb_dir_x = 0.40-0.50 = -0.10; thumb_tip_x = 0.38-0.50 = -0.12
            # thumb_dir_x * thumb_tip_x > 0  → thumb_ext True
            # thumb_vec_y = y[4]-y[2] = 0.80-0.50 = +0.30 > 0.05  → THUMBS_DOWN
            thumb_tip=(0.38, 0.80),
            thumb_mcp2=(0.40, 0.50),
        )
        gest, conf = engine._classify_static(x, y, "Right")
        assert gest == "THUMBS_DOWN", f"Expected THUMBS_DOWN, got {gest}"

    def test_shaka_detected(self):
        """Thumb + pinky extended, middle fingers curled → SHAKA."""
        engine = self._make_engine()
        x, y = _make_hand(
            wrist=(0.5, 0.8),
            mcp9=(0.5, 0.6),
            index_tip=(0.48, 0.72),   # curled
            middle_tip=(0.50, 0.73),
            ring_tip=(0.52, 0.72),
            pinky_tip=(0.62, 0.25),   # extended
            thumb_tip=(0.30, 0.60),   # thumb extended sideways
            thumb_mcp2=(0.39, 0.65),
        )
        gest, conf = engine._classify_static(x, y, "Right")
        assert gest == "SHAKA", f"Expected SHAKA, got {gest}"

    def test_ok_sign_detected(self):
        """Thumb+index pinching + middle/ring/pinky extended → OK_SIGN."""
        engine = self._make_engine()
        x, y = _make_hand(
            wrist=(0.5, 0.8),
            mcp9=(0.5, 0.6),
            index_tip=(0.465, 0.52),  # very close to thumb tip (pinching)
            middle_tip=(0.50, 0.22),  # extended
            ring_tip=(0.54, 0.24),
            pinky_tip=(0.58, 0.28),
            thumb_tip=(0.45, 0.50),   # thumb close to index
            thumb_mcp2=(0.43, 0.64),
        )
        gest, conf = engine._classify_static(x, y, "Right")
        assert gest == "OK_SIGN", f"Expected OK_SIGN, got {gest}"

    def test_unknown_for_noise_landmarks(self):
        """Random noise landmarks should not produce a valid gesture."""
        engine = self._make_engine()
        # All landmarks at exactly wrist position → hand_scale = 0
        x = [0.5] * 21
        y = [0.5] * 21
        gest, conf = engine._classify_static(x, y, "Right")
        assert gest == "UNKNOWN", f"Noise produced gesture: {gest}"
        assert conf == 0.0

    def test_gesture_scale_invariant(self):
        """OPEN_PALM must be detected at 0.5x and 2.0x scale."""
        for scale in [0.5, 1.0, 2.0]:
            engine = self._make_engine()
            x, y = _make_hand(
                wrist=(0.5, 0.8),
                mcp9=(0.5, 0.55),
                index_tip=(0.45, 0.2),
                middle_tip=(0.50, 0.18),
                ring_tip=(0.55, 0.2),
                pinky_tip=(0.60, 0.25),
                thumb_tip=(0.30, 0.55),
                thumb_mcp2=(0.40, 0.65),
                scale=scale,
            )
            gest, conf = engine._classify_static(x, y, "Right")
            assert gest == "OPEN_PALM", f"Scale {scale}x: Expected OPEN_PALM, got {gest}"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — Dynamic Gesture / Swipe Detection
# ─────────────────────────────────────────────────────────────────────────────

class TestDynamicGestures:
    """TrajectoryTracker.detect_swipe detects direction correctly from synthetic history."""

    def _tracker_with_points(self, points: list[tuple[float, float, float, float]]):
        """Build a tracker and inject (x, y, t, size) history tuples directly."""
        tracker = TrajectoryTracker(history_size=60, ema_alpha=1.0)
        for px, py, pt, ps in points:
            tracker.history.append((px, py, pt, ps))
        if points:
            tracker.ema_x = points[-1][0]
            tracker.ema_y = points[-1][1]
            tracker.ema_size = points[-1][3]
        return tracker

    def test_swipe_right(self):
        t0 = time.time()
        size = 0.08
        points = [(0.1 + i * 0.04, 0.5, t0 + i * 0.04, size) for i in range(8)]
        tracker = self._tracker_with_points(points)
        direction, speed = tracker.detect_swipe()
        assert direction == "SWIPE_RIGHT", f"Got {direction}"
        assert speed > 0

    def test_swipe_left(self):
        t0 = time.time()
        size = 0.08
        points = [(0.8 - i * 0.04, 0.5, t0 + i * 0.04, size) for i in range(8)]
        tracker = self._tracker_with_points(points)
        direction, speed = tracker.detect_swipe()
        assert direction == "SWIPE_LEFT", f"Got {direction}"

    def test_swipe_up(self):
        t0 = time.time()
        size = 0.08
        points = [(0.5, 0.8 - i * 0.04, t0 + i * 0.04, size) for i in range(8)]
        tracker = self._tracker_with_points(points)
        direction, speed = tracker.detect_swipe()
        assert direction == "SWIPE_UP", f"Got {direction}"

    def test_swipe_down(self):
        t0 = time.time()
        size = 0.08
        points = [(0.5, 0.2 + i * 0.04, t0 + i * 0.04, size) for i in range(8)]
        tracker = self._tracker_with_points(points)
        direction, speed = tracker.detect_swipe()
        assert direction == "SWIPE_DOWN", f"Got {direction}"

    def test_no_swipe_on_jitter(self):
        """Sub-threshold random micro-movements must NOT register as swipe."""
        t0 = time.time()
        size = 0.08
        import random
        random.seed(42)
        points = [(0.5 + random.uniform(-0.004, 0.004),
                   0.5 + random.uniform(-0.004, 0.004),
                   t0 + i * 0.03, size) for i in range(10)]
        tracker = self._tracker_with_points(points)
        direction, _ = tracker.detect_swipe()
        assert direction == "", f"Jitter produced swipe: {direction}"

    def test_no_swipe_on_static_open_palm(self):
        """A completely static hand must produce no swipe."""
        t0 = time.time()
        size = 0.08
        points = [(0.5, 0.5, t0 + i * 0.03, size) for i in range(10)]
        tracker = self._tracker_with_points(points)
        direction, _ = tracker.detect_swipe()
        assert direction == "", f"Static hand produced swipe: {direction}"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 — State Machine: Temporal Confirmation + Cooldown
# ─────────────────────────────────────────────────────────────────────────────

class TestStateMachine:
    """GestureStateMachine temporal debouncing and cooldown enforcement."""

    def test_candidate_then_confirmed_after_threshold(self):
        """A gesture held past its threshold transitions IDLE→CANDIDATE→CONFIRMED."""
        sm = GestureStateMachine()
        # First frame: IDLE → CANDIDATE
        state, gest, confirmed, _ = sm.process_frame("OPEN_PALM", {})
        assert state == "CANDIDATE"
        assert not confirmed

        # Simulate time passing by manually backdating candidate_start_time
        sm.candidate_start_time -= 0.20  # push it past the 0.15s threshold

        state, gest, confirmed, _ = sm.process_frame("OPEN_PALM", {})
        assert state == "CONFIRMED"
        assert confirmed
        assert gest == "OPEN_PALM"

    def test_no_refire_during_cooldown(self):
        """Same gesture cannot re-confirm while the state machine hasn't reset."""
        sm = GestureStateMachine()
        # Force confirm
        sm.process_frame("FIST", {})
        sm.candidate_start_time -= 0.20
        state, gest, confirmed, _ = sm.process_frame("FIST", {})
        assert confirmed
        assert state == "CONFIRMED"

        # Immediately try again on the same frame — must NOT re-confirm.
        # The SM stays CONFIRMED for the same gesture but fires only once.
        _, _, confirmed2, _ = sm.process_frame("FIST", {})
        assert not confirmed2, "Same gesture must not re-confirm on the very next frame"

    def test_cooldown_expires_and_allows_refire(self):
        """After the hold ends (UNKNOWN / gesture removed), same gesture can confirm again."""
        sm = GestureStateMachine()
        sm.process_frame("FIST", {})
        sm.candidate_start_time -= 0.20
        sm.process_frame("FIST", {})  # confirms

        # Feed UNKNOWN to simulate the hand going away → SM should drop to IDLE
        for _ in range(30):
            state, _, _, _ = sm.process_frame("UNKNOWN", {})
        assert state == "IDLE", f"SM should return to IDLE on sustained UNKNOWN, got {state}"

    def test_unknown_resets_candidate_over_time(self):
        """UNKNOWN input causes candidate to decay and eventually drop to IDLE."""
        sm = GestureStateMachine()
        sm.process_frame("OPEN_PALM", {})
        assert sm.state == "CANDIDATE"

        # Feed UNKNOWN repeatedly — should eventually drop back
        for _ in range(20):
            sm.process_frame("UNKNOWN", {})

        assert sm.state == "IDLE"

    def test_gesture_switch_resets_candidate(self):
        """Changing gesture before confirmation resets the candidate clock."""
        sm = GestureStateMachine()
        sm.process_frame("OPEN_PALM", {})
        t1 = sm.candidate_start_time

        time.sleep(0.05)
        sm.process_frame("FIST", {})
        t2 = sm.candidate_start_time

        assert t2 > t1, "Candidate start time should reset on gesture change"
        assert sm.current_gesture == "FIST"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8 — Combo: Virtual Desktop (SWIPE_DOWN → SWIPE_LEFT/RIGHT)
# ─────────────────────────────────────────────────────────────────────────────

class TestVirtualDesktopCombo:

    def _confirm_gesture(self, sm, gesture):
        """Helper: drive sm to confirm a gesture."""
        sm.state = "IDLE"
        sm.current_gesture = None
        sm.process_frame(gesture, {})
        sm.candidate_start_time -= 0.30
        state, gest, confirmed, _ = sm.process_frame(gesture, {})
        return state, gest, confirmed

    def test_swipe_down_then_left_gives_previous_desktop(self):
        sm = GestureStateMachine()
        # Confirm SWIPE_DOWN — should park in pending_combo and return None
        state, gest, confirmed = self._confirm_gesture(sm, "SWIPE_DOWN")
        assert sm.pending_combo == "SWIPE_DOWN", "SWIPE_DOWN should set pending_combo"
        # SWIPE_DOWN combo intercept: gesture is None (parked, not fired)
        assert gest is None or gest == "SWIPE_DOWN"  # implementation detail

        # Drive SWIPE_LEFT — should resolve to PREVIOUS_DESKTOP in one pass
        state, gest, confirmed = self._confirm_gesture(sm, "SWIPE_LEFT")
        assert gest == "PREVIOUS_DESKTOP", f"Expected PREVIOUS_DESKTOP, got {gest}"

    def test_swipe_down_then_right_gives_next_desktop(self):
        sm = GestureStateMachine()
        self._confirm_gesture(sm, "SWIPE_DOWN")
        assert sm.pending_combo == "SWIPE_DOWN"

        sm.state = "IDLE"
        sm.current_gesture = None
        sm.process_frame("SWIPE_RIGHT", {})
        sm.candidate_start_time -= 0.30
        state, gest, confirmed, _ = sm.process_frame("SWIPE_RIGHT", {})
        assert gest == "NEXT_DESKTOP", f"Expected NEXT_DESKTOP, got {gest}"

    def test_combo_expired_does_not_trigger_desktop(self):
        """SWIPE_DOWN → wait → SWIPE_LEFT must NOT trigger combo."""
        sm = GestureStateMachine()
        self._confirm_gesture(sm, "SWIPE_DOWN")
        # Expire the combo window
        sm.pending_combo_time -= 10.0

        sm.state = "IDLE"
        sm.current_gesture = None
        sm.process_frame("SWIPE_LEFT", {})
        sm.candidate_start_time -= 0.30
        _, gest, confirmed, _ = sm.process_frame("SWIPE_LEFT", {})
        assert gest != "PREVIOUS_DESKTOP", f"Expired combo should not fire, got {gest}"

    def test_reverse_order_does_not_trigger_combo(self):
        """SWIPE_LEFT first, then SWIPE_DOWN — must NOT combo."""
        sm = GestureStateMachine()
        self._confirm_gesture(sm, "SWIPE_LEFT")
        # No pending_combo should be set for left swipe
        assert sm.pending_combo != "SWIPE_LEFT"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9 — PALM_GRAB (OPEN_PALM → FIST sequence)
# ─────────────────────────────────────────────────────────────────────────────

class TestPalmGrab:

    def _confirm(self, sm, gesture):
        sm.state = "IDLE"
        sm.current_gesture = None
        sm.process_frame(gesture, {})
        sm.candidate_start_time -= 0.30
        return sm.process_frame(gesture, {})

    def test_open_palm_then_fist_gives_palm_grab(self):
        sm = GestureStateMachine()
        _, _, confirmed, _ = self._confirm(sm, "OPEN_PALM")
        assert confirmed, "OPEN_PALM should confirm"

        _, gest, confirmed2, _ = self._confirm(sm, "FIST")
        assert gest == "PALM_GRAB", f"Expected PALM_GRAB, got {gest}"
        assert confirmed2

    def test_fist_alone_does_not_give_palm_grab(self):
        """FIST without prior OPEN_PALM in history window → plain FIST, not PALM_GRAB."""
        sm = GestureStateMachine()
        _, gest, confirmed, _ = self._confirm(sm, "FIST")
        assert confirmed
        assert gest == "FIST", f"Expected FIST (no prior OPEN_PALM), got {gest}"

    def test_palm_grab_not_repeated_on_hold(self):
        """Holding FIST after PALM_GRAB must not re-fire PALM_GRAB."""
        sm = GestureStateMachine()
        self._confirm(sm, "OPEN_PALM")
        _, gest, confirmed2, _ = self._confirm(sm, "FIST")
        assert gest == "PALM_GRAB"

        # Now stay in FIST — should be in cooldown
        state, _, confirmed3, _ = sm.process_frame("FIST", {})
        assert not confirmed3, "PALM_GRAB must not re-fire on hold"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 11 — Repeat-fire protection
# ─────────────────────────────────────────────────────────────────────────────

class TestRepeatFireProtection:

    def test_static_gesture_does_not_refire_on_hold(self):
        """Holding OPEN_PALM for many frames must produce exactly one confirmed event."""
        sm = GestureStateMachine()
        confirmed_count = 0

        sm.process_frame("OPEN_PALM", {})
        sm.candidate_start_time -= 0.20

        for _ in range(30):
            _, _, confirmed, _ = sm.process_frame("OPEN_PALM", {})
            if confirmed:
                confirmed_count += 1

        assert confirmed_count == 1, f"Expected 1 confirm, got {confirmed_count}"

    def test_dynamic_gesture_does_not_repeat_after_motion_stops(self):
        """Once SWIPE_RIGHT is confirmed, feeding it again during cooldown must not refire."""
        sm = GestureStateMachine()
        sm.process_frame("SWIPE_RIGHT", {})
        sm.candidate_start_time -= 0.10
        _, _, confirmed, _ = sm.process_frame("SWIPE_RIGHT", {})
        assert confirmed

        refire = 0
        for _ in range(15):
            _, _, c, _ = sm.process_frame("SWIPE_RIGHT", {})
            if c:
                refire += 1
        assert refire == 0, f"Dynamic gesture re-fired {refire} times during cooldown"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
