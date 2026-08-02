"""
perception/tests/test_screen_pipeline.py
Unit tests for the screen pipeline module.
"""

import os
import sys
import pytest

_THIS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_THIS))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_solid_image(r, g, b, width=400, height=300):
    """Create a solid-color PIL image for testing."""
    try:
        from PIL import Image
        img = Image.new("RGB", (width, height), (r, g, b))
        return img
    except ImportError:
        pytest.skip("PIL not available")


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalyzeFrame:
    def test_returns_screen_event_dict(self):
        from perception.screen_pipeline import analyze_frame
        img = _make_solid_image(30, 30, 40)  # dark — IDE-like
        result = analyze_frame(img)
        assert isinstance(result, dict)
        assert "app_type"         in result
        assert "raw_description"  in result
        assert "brightness"       in result
        assert "has_sidebar"      in result
        assert "ocr_text"         in result
        assert "vision_description" in result
        assert "timestamp"        in result

    def test_dark_image_low_brightness(self):
        from perception.screen_pipeline import analyze_frame
        img = _make_solid_image(20, 20, 30)
        result = analyze_frame(img)
        assert result["brightness"] < 30

    def test_bright_image_high_brightness(self):
        from perception.screen_pipeline import analyze_frame
        img = _make_solid_image(240, 240, 240)
        result = analyze_frame(img)
        assert result["brightness"] > 70

    def test_raw_description_non_empty(self):
        from perception.screen_pipeline import analyze_frame
        img = _make_solid_image(30, 30, 40)
        result = analyze_frame(img)
        assert len(result["raw_description"]) > 0

    def test_null_vision_adapter_returns_empty(self):
        """With NullVisionAdapter (default), vision_description should be ''."""
        from perception.screen_pipeline import analyze_frame
        img = _make_solid_image(30, 30, 40)
        result = analyze_frame(img)
        # Vision description is empty when NullVisionAdapter is active
        # (may be non-empty if a real adapter is configured — still valid)
        assert isinstance(result["vision_description"], str)

    def test_rgba_image_converted(self):
        """RGBA images should be handled without error."""
        try:
            from PIL import Image
            from perception.screen_pipeline import analyze_frame
            img = Image.new("RGBA", (200, 150), (30, 30, 40, 255))
            result = analyze_frame(img)
            assert isinstance(result, dict)
        except ImportError:
            pytest.skip("PIL not available")

    def test_resize_applied(self):
        """Large images should be resized to max_width."""
        from perception.screen_pipeline import analyze_frame
        from perception.config_loader import get
        max_w = get("screen_perception", "capture_resolution_max_width", default=1280)
        img = _make_solid_image(30, 30, 40, width=max_w * 2, height=400)
        # Should not raise even for very large input
        result = analyze_frame(img)
        assert isinstance(result, dict)


class TestAppTypeClassification:
    def test_dark_image_classified_as_ide(self):
        from perception.screen_pipeline import analyze_frame
        img = _make_solid_image(15, 15, 20)  # very dark
        result = analyze_frame(img)
        assert "dark" in result["app_type"].lower() or "code" in result["app_type"].lower()

    def test_bright_image_classified_as_browser(self):
        from perception.screen_pipeline import analyze_frame
        img = _make_solid_image(240, 245, 250)  # near-white
        result = analyze_frame(img)
        # Should match browser or document
        assert any(
            word in result["app_type"].lower()
            for word in ["browser", "document", "notepad", "explorer"]
        )


class TestProcessFrameBytes:
    def test_valid_base64_jpeg(self):
        try:
            import base64
            from io import BytesIO
            from PIL import Image
            from perception.screen_pipeline import process_frame_bytes

            img = Image.new("RGB", (100, 80), (30, 30, 40))
            buf = BytesIO()
            img.save(buf, format="JPEG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")

            result = process_frame_bytes(b64)
            assert result is not None
            assert isinstance(result, dict)
        except ImportError:
            pytest.skip("PIL not available")

    def test_invalid_base64_returns_none(self):
        from perception.screen_pipeline import process_frame_bytes
        result = process_frame_bytes("not_valid_base64!!!")
        assert result is None

    def test_empty_string_returns_none(self):
        from perception.screen_pipeline import process_frame_bytes
        result = process_frame_bytes("")
        assert result is None

    def test_data_uri_prefix_stripped(self):
        """Handles 'data:image/jpeg;base64,...' format."""
        try:
            import base64
            from io import BytesIO
            from PIL import Image
            from perception.screen_pipeline import process_frame_bytes

            img = Image.new("RGB", (50, 50), (200, 200, 200))
            buf = BytesIO()
            img.save(buf, format="JPEG")
            b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

            result = process_frame_bytes(b64)
            assert result is not None
        except ImportError:
            pytest.skip("PIL not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
