"""
perception/tests/test_gesture_interpreter_unit.py
==================================================
Unit tests for GestureInterpreter._map_gesture_to_intent()

Covers:
  - Every gesture→intent mapping in system, browser, and media contexts
  - Task View state machine gating (gestures suppressed/allowed per state)
  - Null return for unknown/unhandled gestures
  - Context rules override via blackboard
"""

import sys
import os
import time
import pytest
from unittest.mock import MagicMock, patch

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: Isolated GestureInterpreter with mocked dependencies
# ─────────────────────────────────────────────────────────────────────────────

def _make_interpreter(domain="system", context_rules=None):
    """Return a fresh GestureInterpreter with mocked event hub, smart_manager, blackboard."""
    from perception.gesture_interpreter import TaskViewState

    with patch("perception.gesture_interpreter.get_event_hub") as mock_hub, \
         patch("perception.gesture_interpreter.get_smart_manager") as mock_sm, \
         patch("perception.gesture_interpreter.get_cognitive_blackboard") as mock_bb:

        mock_hub.return_value = MagicMock()
        mock_sm.return_value = MagicMock()

        bb = MagicMock()
        bb.get_state.side_effect = lambda key: {
            "active_action": {"domain": domain, "action": "open"},
            "gesture_context_rules": context_rules or {},
        }.get(key)
        mock_bb.return_value = bb

        # Bypass singleton to get a fresh instance
        from perception.gesture_interpreter import GestureInterpreter
        GestureInterpreter._instance = None
        interp = GestureInterpreter()
        interp._task_view_state = TaskViewState.NORMAL
        return interp


# ─────────────────────────────────────────────────────────────────────────────
# Phase 6 — Intent mapping per gesture
# ─────────────────────────────────────────────────────────────────────────────

class TestStaticGestureIntents:

    def test_open_palm_maps_to_play_pause(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("OPEN_PALM")
        assert intent is not None
        assert intent.action == "play_pause"
        assert intent.domain == "media"

    def test_fist_maps_to_escape(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("FIST")
        assert intent is not None
        assert intent.action == "escape"

    def test_thumbs_up_maps_to_like(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("THUMBS_UP")
        assert intent is not None
        assert intent.action == "like"

    def test_thumbs_down_maps_to_cancel(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("THUMBS_DOWN")
        assert intent is not None
        assert intent.action == "cancel"

    def test_ok_sign_maps_to_confirm(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("OK_SIGN")
        assert intent is not None
        assert intent.action == "confirm"

    def test_point_maps_to_click_outside_task_view(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("POINT")
        assert intent is not None
        assert intent.action == "click"

    def test_shaka_maps_to_mute_toggle(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("SHAKA")
        assert intent is not None
        assert intent.action == "mute_toggle"

    def test_palm_grab_maps_to_screenshot(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("PALM_GRAB")
        assert intent is not None
        assert intent.action == "screenshot"

    def test_clap_maps_to_toggle_recording(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("CLAP")
        assert intent is not None
        assert intent.action == "toggle_recording"

    def test_unknown_gesture_returns_none(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("TOTALLY_FAKE_GESTURE")
        assert intent is None


class TestDynamicGestureIntents:

    def test_swipe_right_system_maps_to_next_app(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("SWIPE_RIGHT")
        assert intent.action == "next_app"

    def test_swipe_left_system_maps_to_previous_app(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("SWIPE_LEFT")
        assert intent.action == "previous_app"

    def test_swipe_right_browser_maps_to_next_tab(self):
        interp = _make_interpreter("browser")
        intent = interp._map_gesture_to_intent("SWIPE_RIGHT")
        assert intent.action == "next_tab"

    def test_swipe_left_browser_maps_to_previous_tab(self):
        interp = _make_interpreter("browser")
        intent = interp._map_gesture_to_intent("SWIPE_LEFT")
        assert intent.action == "previous_tab"

    def test_pinch_move_up_maps_to_volume_up(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("PINCH_MOVE_UP")
        assert intent.action == "volume_up"

    def test_pinch_move_down_maps_to_volume_down(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("PINCH_MOVE_DOWN")
        assert intent.action == "volume_down"

    def test_pinch_move_right_maps_to_seek_forward(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("PINCH_MOVE_RIGHT")
        assert intent.action == "seek_forward"

    def test_pinch_move_left_maps_to_seek_back(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("PINCH_MOVE_LEFT")
        assert intent.action == "seek_back"

    def test_fist_move_right_maps_to_next_track(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("FIST_MOVE_RIGHT")
        assert intent.action == "next_track"

    def test_fist_move_left_maps_to_previous_track(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("FIST_MOVE_LEFT")
        assert intent.action == "previous_track"

    def test_palm_move_up_maps_to_scroll_up(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("PALM_MOVE_UP")
        assert intent.action == "scroll_up"

    def test_palm_move_down_maps_to_scroll_down(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("PALM_MOVE_DOWN")
        assert intent.action == "scroll_down"

    def test_point_move_up_opens_task_view(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("POINT_MOVE_UP")
        assert intent.action == "task_view"

    def test_point_move_down_shows_desktop_in_normal_mode(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("POINT_MOVE_DOWN")
        assert intent.action == "show_desktop"

    def test_previous_desktop_intent(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("PREVIOUS_DESKTOP")
        assert intent.action == "previous_desktop"

    def test_next_desktop_intent(self):
        interp = _make_interpreter("system")
        intent = interp._map_gesture_to_intent("NEXT_DESKTOP")
        assert intent.action == "next_desktop"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7 — Task View state machine gating
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskViewGating:

    def test_point_suppressed_in_task_view(self):
        """POINT (click) must be suppressed while Task View is active."""
        from perception.gesture_interpreter import TaskViewState
        interp = _make_interpreter("system")
        interp._task_view_state = TaskViewState.ACTIVE
        intent = interp._map_gesture_to_intent("POINT")
        assert intent is None, "POINT click must be suppressed in Task View"

    def test_point_move_up_ignored_if_task_view_already_active(self):
        """POINT_MOVE_UP must not re-trigger task_view if already active."""
        from perception.gesture_interpreter import TaskViewState
        interp = _make_interpreter("system")
        interp._task_view_state = TaskViewState.ACTIVE
        intent = interp._map_gesture_to_intent("POINT_MOVE_UP")
        assert intent is None

    def test_swipe_suppressed_in_task_view(self):
        """SWIPE_LEFT/RIGHT must be suppressed in Task View mode."""
        from perception.gesture_interpreter import TaskViewState
        interp = _make_interpreter("system")
        interp._task_view_state = TaskViewState.ACTIVE
        assert interp._map_gesture_to_intent("SWIPE_LEFT") is None
        assert interp._map_gesture_to_intent("SWIPE_RIGHT") is None

    def test_two_fingers_move_active_in_task_view(self):
        """TWO_FINGERS_MOVE_LEFT/RIGHT are active ONLY in Task View."""
        from perception.gesture_interpreter import TaskViewState
        interp = _make_interpreter("system")

        # Normal mode — should return None
        assert interp._map_gesture_to_intent("TWO_FINGERS_MOVE_LEFT") is None
        assert interp._map_gesture_to_intent("TWO_FINGERS_MOVE_RIGHT") is None

        # Task View active — should return intents
        interp._task_view_state = TaskViewState.ACTIVE
        left = interp._map_gesture_to_intent("TWO_FINGERS_MOVE_LEFT")
        right = interp._map_gesture_to_intent("TWO_FINGERS_MOVE_RIGHT")
        assert left is not None and left.action == "task_view_prev"
        assert right is not None and right.action == "task_view_next"

    def test_point_move_down_closes_task_view_after_delay(self):
        """POINT_MOVE_DOWN in Task View after 1.5s closes it via escape."""
        from perception.gesture_interpreter import TaskViewState
        interp = _make_interpreter("system")
        interp._task_view_state = TaskViewState.ACTIVE
        interp._task_view_opened_at = time.time() - 2.0  # 2s ago

        intent = interp._map_gesture_to_intent("POINT_MOVE_DOWN")
        assert intent is not None
        assert intent.action == "escape"
        assert interp._task_view_state == TaskViewState.NORMAL

    def test_point_move_down_ignored_immediately_after_open(self):
        """POINT_MOVE_DOWN within 1.5s of opening Task View must be ignored."""
        from perception.gesture_interpreter import TaskViewState
        interp = _make_interpreter("system")
        interp._task_view_state = TaskViewState.ACTIVE
        interp._task_view_opened_at = time.time() - 0.3  # just opened

        intent = interp._map_gesture_to_intent("POINT_MOVE_DOWN")
        assert intent is None, "Downward return motion must be ignored immediately after opening"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
