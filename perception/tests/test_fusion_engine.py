"""
perception/tests/test_fusion_engine.py
Unit tests for the FusionEngine.
"""

import os
import sys
import time
import pytest

_THIS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_THIS))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from perception.fusion_engine import FusionEngine
from perception.event_memory import EventMemory


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def engine():
    """Fresh FusionEngine with in-memory EventMemory (no disk writes)."""
    mem = EventMemory()
    mem._retention_seconds = 60.0
    mem._max_events        = 100
    mem._token_budget      = 300
    mem._summary_path      = None
    mem._state_loaded      = True   # do not load real state from disk during tests
    eng = FusionEngine(memory=mem)
    eng._events_path = None   # Disable disk flushing in tests
    return eng


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPushScreenEvent:
    def test_basic_push(self, engine):
        ev = {
            "raw_description": "VS Code is open with Python code.",
            "app_type": "Visual Studio Code (dark theme)",
            "brightness": 20.0,
            "has_sidebar": True,
            "content_density": "dense with content",
            "ocr_text": "",
            "vision_description": "",
        }
        engine.push_screen_event(ev)
        assert engine.event_count() == 1

    def test_dedup_skips_identical(self, engine):
        desc = "Same description every time"
        ev = {
            "raw_description": desc,
            "app_type": "browser",
            "brightness": 80.0,
            "has_sidebar": False,
            "content_density": "sparse",
            "ocr_text": "",
            "vision_description": "",
        }
        engine.push_screen_event(ev)
        engine.push_screen_event(ev)
        assert engine.event_count() == 1  # second push skipped

    def test_different_descriptions_both_stored(self, engine):
        for i in range(3):
            ev = {
                "raw_description": f"Description variant {i}",
                "app_type": "browser",
                "brightness": 80.0,
                "has_sidebar": False,
                "content_density": "sparse",
                "ocr_text": "",
                "vision_description": "",
            }
            engine.push_screen_event(ev)
        assert engine.event_count() == 3

    def test_empty_description_skipped(self, engine):
        engine.push_screen_event({"raw_description": ""})
        assert engine.event_count() == 0

    def test_ocr_raises_importance(self, engine):
        """Events with OCR text should have higher importance."""
        ev = {
            "raw_description": "OCR-rich event",
            "app_type": "VS Code",
            "brightness": 20.0,
            "has_sidebar": False,
            "content_density": "dense",
            "ocr_text": "some extracted text",
            "vision_description": "",
        }
        engine.push_screen_event(ev)
        events = engine.get_recent_events()
        assert events[0]["importance"] == 0.8


class TestPushAudioEvent:
    def test_basic_audio_push(self, engine):
        ev = {
            "event_type": "music",
            "description": "Upbeat electronic music playing",
            "confidence": 0.7,
            "duration_seconds": 2.0,
        }
        engine.push_audio_event(ev)
        assert engine.event_count() == 1

    def test_empty_audio_skipped(self, engine):
        engine.push_audio_event({"event_type": "silence", "description": ""})
        assert engine.event_count() == 0

    def test_alarm_has_high_importance(self, engine):
        ev = {
            "event_type": "alarm",
            "description": "High-pitched alarm detected",
            "confidence": 0.8,
            "duration_seconds": 1.0,
        }
        engine.push_audio_event(ev)
        events = engine.get_recent_events()
        assert events[0]["importance"] == 0.9


class TestPushUserAction:
    def test_action_stored(self, engine):
        engine.push_user_action("emotion:joy")
        events = engine.get_recent_events()
        assert any("emotion:joy" in e["semantic"] for e in events)

    def test_empty_action_skipped(self, engine):
        engine.push_user_action("")
        assert engine.event_count() == 0


class TestGetContextForPrompt:
    def test_returns_string(self, engine):
        engine.push_user_action("Vivy startup")
        ctx = engine.get_context_for_prompt()
        assert isinstance(ctx, str)

    def test_empty_when_nothing(self, engine):
        ctx = engine.get_context_for_prompt()
        assert ctx == ""


class TestThreadSafety:
    def test_concurrent_pushes(self, engine):
        """Multiple threads pushing events should not corrupt state."""
        import threading

        def push_many(n):
            for i in range(n):
                engine.push_user_action(f"Thread event {i}")

        threads = [threading.Thread(target=push_many, args=(20,)) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have exactly 100 events (5 threads × 20 each)
        assert engine.event_count() == 100


class TestDedupRelaxation:
    def test_dedup_allows_rich_ocr(self, engine):
        ev1 = {
            "raw_description": "Same description",
            "app_type": "browser",
            "brightness": 80.0,
            "has_sidebar": False,
            "content_density": "sparse",
            "ocr_text": "",
            "vision_description": "",
        }
        ev2 = {
            "raw_description": "Same description",
            "app_type": "browser",
            "brightness": 80.0,
            "has_sidebar": False,
            "content_density": "sparse",
            "ocr_text": "some new ocr text",
            "vision_description": "",
        }
        engine._process_event("screen", ev1)
        engine._process_event("screen", ev2)
        assert engine.event_count() == 2


class TestObservationNarrative:
    def test_narrative_generation(self, engine):
        engine._screen_share_start_time = time.time() - 120  # 2 minutes ago
        engine._current_activity = "VS Code"
        ev = {
            "raw_description": "Screen shows code editor",
            "app_type": "VS Code",
            "brightness": 20.0,
            "has_sidebar": True,
            "content_density": "dense",
            "ocr_text": "",
            "vision_description": "",
        }
        engine._process_event("screen", ev)
        
        # Manually force update by resetting interval timestamp
        engine._narrative_last_update = 0.0
        engine._update_observation_narrative()
        
        narr = engine.get_observation_narrative()
        assert "Screen share active for ~2 min" in narr
        assert "showing VS Code" in narr


class TestMeaningfulEventDetection:
    def test_silence_after_music_emits_event(self, engine):
        # 1. Start with music playing
        ev_music = {
            "event_type": "music",
            "description": "Music playing",
            "confidence": 0.8,
            "duration_seconds": 2.0,
        }
        engine._process_event("audio", ev_music)
        assert engine._media_state == "playing"
        
        # 2. Fake that the last audio event time was 35 seconds ago
        engine._last_audio_event_time = time.time() - 35.0
        
        # 3. Receive a silence event
        ev_silence = {
            "event_type": "silence",
            "description": "Silent ambient",
            "confidence": 0.9,
            "duration_seconds": 2.0,
        }
        engine._process_event("audio", ev_silence)
        
        # Verify media state changed to paused, and a system event was emitted
        assert engine._media_state == "paused"
        events = engine.get_recent_events()
        assert any(e["source"] == "system" and "media may have paused" in e["semantic"] for e in events)

    def test_passive_session_emits_event(self, engine):
        engine._screen_share_start_time = time.time() - 600
        engine._current_activity = "Browser"
        # Last user interaction was 6 minutes (360 seconds) ago
        engine._last_user_interaction_time = time.time() - 360.0
        
        # Add a dummy screen event so recent list is not empty
        ev = {
            "raw_description": "Screen shows browser",
            "app_type": "Browser",
            "brightness": 20.0,
            "has_sidebar": True,
            "content_density": "dense",
            "ocr_text": "",
            "vision_description": "",
        }
        engine._process_event("screen", ev)
        
        # Trigger narrative update which runs passive session detection
        engine._narrative_last_update = 0.0
        engine._update_observation_narrative()
        
        # Verify system event was emitted for passive presence
        events = engine.get_recent_events()
        assert any(e["source"] == "system" and "passively present" in e["semantic"] for e in events)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
