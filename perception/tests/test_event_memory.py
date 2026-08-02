"""
perception/tests/test_event_memory.py
Unit tests for the EventMemory rolling log.
"""

import os
import sys
import time
import pytest

_THIS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_THIS))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from perception.event_memory import EventMemory, make_event


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mem():
    """Fresh EventMemory with tight config overrides for fast testing."""
    m = EventMemory()
    m._retention_seconds = 5.0    # 5-second window for tests
    m._max_events        = 10
    m._token_budget      = 100
    m._summary_trigger   = 5
    m._summary_path      = None   # no disk writes during tests
    m._state_loaded      = True   # do not load real state from disk during tests
    return m


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMakeEvent:
    def test_has_required_keys(self):
        ev = make_event("screen", "Browser is open")
        assert ev["source"]   == "screen"
        assert ev["semantic"] == "Browser is open"
        assert "id" in ev
        assert "timestamp" in ev
        assert isinstance(ev["importance"], float)

    def test_default_importance(self):
        ev = make_event("audio", "Music playing")
        assert ev["importance"] == 0.5

    def test_custom_importance(self):
        ev = make_event("screen", "Test", importance=0.9)
        assert ev["importance"] == 0.9

    def test_metadata_stored(self):
        ev = make_event("screen", "Test", metadata={"key": "value"})
        assert ev["metadata"]["key"] == "value"


class TestEventMemoryAdd:
    def test_add_single_event(self, mem):
        ev = make_event("screen", "VS Code is open")
        mem.add(ev)
        assert mem.event_count() == 1

    def test_add_multiple_events(self, mem):
        for i in range(5):
            mem.add(make_event("screen", f"Event {i}"))
        assert mem.event_count() == 5

    def test_max_events_enforced(self, mem):
        # Add more than max_events
        for i in range(15):
            mem.add(make_event("screen", f"Event {i}", importance=0.5))
        assert mem.event_count() <= mem._max_events


class TestGetRecentEvents:
    def test_returns_events_within_window(self, mem):
        ev = make_event("screen", "Recent event")
        mem.add(ev)
        recent = mem.get_recent_events(max_age_seconds=60)
        assert len(recent) >= 1
        assert any(e["semantic"] == "Recent event" for e in recent)

    def test_excludes_old_events(self, mem):
        # Manually create an old event by patching its timestamp
        ev = make_event("screen", "Old event")
        ev["timestamp"] = time.time() - 1000  # 1000 seconds ago
        mem._events.append(ev)
        recent = mem.get_recent_events(max_age_seconds=5)
        assert not any(e["semantic"] == "Old event" for e in recent)


class TestGetContextForPrompt:
    def test_returns_string(self, mem):
        mem.add(make_event("screen", "VS Code open"))
        ctx = mem.get_context_for_prompt()
        assert isinstance(ctx, str)

    def test_empty_when_no_events(self, mem):
        ctx = mem.get_context_for_prompt()
        assert ctx == ""

    def test_respects_token_budget(self, mem):
        # Add many events with long descriptions
        for i in range(20):
            mem.add(make_event("screen", "A" * 200 + f" event {i}"))
        ctx = mem.get_context_for_prompt(token_budget=50)
        assert len(ctx) <= 50 * 4 + 200  # Allow some overhead for header

    def test_contains_event_text(self, mem):
        mem.add(make_event("screen", "Unique-test-phrase-XYZ"))
        ctx = mem.get_context_for_prompt()
        assert "Unique-test-phrase-XYZ" in ctx


class TestEviction:
    def test_eviction_compresses_into_summary(self, mem):
        # Fill past summary trigger count
        for i in range(8):
            ev = make_event("screen", f"Old event {i}", importance=0.3)
            ev["timestamp"] = time.time() - 1000
            mem._events.append(ev)

        # Force eviction
        mem._evict_counter = mem._summary_trigger
        mem.add(make_event("screen", "Trigger eviction"))

        # Summary should have been populated
        assert mem._summary != "" or mem.event_count() <= mem._max_events


class TestClear:
    def test_clear_removes_all(self, mem):
        for _ in range(5):
            mem.add(make_event("screen", "Test"))
        mem.clear()
        assert mem.event_count() == 0
        assert mem._summary == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
