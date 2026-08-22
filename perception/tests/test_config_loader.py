"""
perception/tests/test_config_loader.py
Unit tests for the config loader module.
"""

import os
import json
import sys
import tempfile
import pytest

# Ensure project root is on sys.path
_THIS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_THIS))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _reset_loader():
    """Force the config loader to re-read on next call."""
    import perception.config_loader as cl
    cl._config = None


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestGetConfigDefaults:
    """Config loader returns complete defaults when no file is present."""

    def test_returns_dict(self):
        _reset_loader()
        import perception.config_loader as cl
        cl._CONFIG_PATH = "/nonexistent/vivy_config.json"
        cfg = cl.get_config()
        assert isinstance(cfg, dict)
        _reset_loader()

    def test_default_screen_fps(self):
        _reset_loader()
        import perception.config_loader as cl
        cl._CONFIG_PATH = "/nonexistent/vivy_config.json"
        assert cl.get("screen_perception", "fps") == 30
        _reset_loader()

    def test_default_staleness(self):
        _reset_loader()
        import perception.config_loader as cl
        cl._CONFIG_PATH = "/nonexistent/vivy_config.json"
        assert cl.get("screen_perception", "staleness_seconds") == 60
        _reset_loader()

    def test_audio_disabled_by_default(self):
        _reset_loader()
        import perception.config_loader as cl
        cl._CONFIG_PATH = "/nonexistent/vivy_config.json"
        cl._DISABLE_SHARED_OVERRIDES = True
        try:
            assert cl.get("audio_perception", "enabled") is False
        finally:
            cl._DISABLE_SHARED_OVERRIDES = False
            _reset_loader()

    def test_proactivity_disabled_by_default(self):
        _reset_loader()
        import perception.config_loader as cl
        cl._CONFIG_PATH = "/nonexistent/vivy_config.json"
        cl._DISABLE_SHARED_OVERRIDES = True
        try:
            assert cl.get("proactivity", "enabled") is False
        finally:
            cl._DISABLE_SHARED_OVERRIDES = False
            _reset_loader()

    def test_missing_key_returns_default_arg(self):
        _reset_loader()
        import perception.config_loader as cl
        cl._CONFIG_PATH = "/nonexistent/vivy_config.json"
        val = cl.get("screen_perception", "nonexistent_key_xyz", default="sentinel")
        assert val == "sentinel"
        _reset_loader()


class TestGetConfigFromFile:
    """Config loader correctly overrides defaults from a JSON file."""

    def _make_config_file(self, overrides: dict) -> str:
        """Write a temporary vivy_config.json and return its path."""
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(overrides, tmp)
        tmp.close()
        return tmp.name

    def test_override_fps(self):
        path = self._make_config_file({"screen_perception": {"fps": 10}})
        try:
            import perception.config_loader as cl
            _reset_loader()
            cl._CONFIG_PATH = path
            assert cl.get("screen_perception", "fps") == 10
        finally:
            os.unlink(path)
            _reset_loader()

    def test_partial_override_preserves_other_defaults(self):
        path = self._make_config_file({"screen_perception": {"fps": 5}})
        try:
            import perception.config_loader as cl
            _reset_loader()
            cl._CONFIG_PATH = path
            # fps overridden
            assert cl.get("screen_perception", "fps") == 5
            # staleness_seconds still has its default
            assert cl.get("screen_perception", "staleness_seconds") == 60
        finally:
            os.unlink(path)
            _reset_loader()

    def test_bad_json_uses_defaults(self):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        tmp.write("{ not valid json }")
        tmp.close()
        try:
            import perception.config_loader as cl
            _reset_loader()
            cl._CONFIG_PATH = tmp.name
            assert cl.get("screen_perception", "fps") == 30  # default
        finally:
            os.unlink(tmp.name)
            _reset_loader()


class TestGetAbsolutePath:
    def test_absolute_path_unchanged(self):
        import perception.config_loader as cl
        p = cl.get_absolute_path("C:\\Windows\\System32\\test.exe")
        assert p == "C:\\Windows\\System32\\test.exe"

    def test_relative_joined_to_root(self):
        import perception.config_loader as cl
        p = cl.get_absolute_path("models/test.gguf")
        # Normalise separators so the test is OS-agnostic
        p_norm = os.path.normpath(p)
        expected = os.path.join("models", "test.gguf")
        assert p_norm.endswith(expected)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
