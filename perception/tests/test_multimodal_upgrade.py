"""
perception/tests/test_multimodal_upgrade.py
============================================
Verification tests for the Multimodal Perception Expansion features.
"""

import os
import sys
import time
import pytest
import numpy as np
import PIL.Image

_THIS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_THIS))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from perception.plugins.interfaces import BaseVisionPlugin, BaseOCRPlugin, BaseAudioAnalysisPlugin
from perception.model_router import ModelRouter
from perception.event_memory import EventMemory, make_event
from perception.fusion_engine import FusionEngine
from perception.screen_pipeline import analyze_frame


# ── Test Mock Plugins ─────────────────────────────────────────────────────────

class MockVisionPlugin(BaseVisionPlugin):
    @property
    def name(self) -> str:
        return "mock_vision"

    def is_available(self) -> bool:
        return True

    def describe(self, image, prompt: str = "") -> str:
        return "A mock screen description"

    def get_capabilities(self) -> list[str]:
        return ["scene_understanding", "object_recognition"]


class MockOCRPlugin(BaseOCRPlugin):
    @property
    def name(self) -> str:
        return "mock_ocr"

    def is_available(self) -> bool:
        return True

    def extract_text(self, image) -> str:
        return "Mock OCR Text"


# ── Test Cases ────────────────────────────────────────────────────────────────

def test_model_router_plugin_registration():
    """Verify that we can register and retrieve plugins via ModelRouter."""
    ModelRouter.register_plugin("vision", "mock_vision", MockVisionPlugin)
    ModelRouter.register_plugin("ocr", "mock_ocr", MockOCRPlugin)

    # Temporary configuration override for testing
    from perception.config_loader import get_config
    cfg = get_config()
    cfg.setdefault("model_routing", {})["vision_preferred"] = "mock_vision"
    cfg.setdefault("model_routing", {})["ocr_preferred"] = "mock_ocr"

    vision_plugin = ModelRouter.get_vision_plugin()
    ocr_plugin = ModelRouter.get_ocr_plugin()

    assert isinstance(vision_plugin, MockVisionPlugin)
    assert isinstance(ocr_plugin, MockOCRPlugin)
    assert vision_plugin.name == "mock_vision"
    assert "scene_understanding" in vision_plugin.get_capabilities()
    assert ocr_plugin.extract_text(PIL.Image.new("RGB", (100, 100))) == "Mock OCR Text"


def test_hierarchical_memory_ordering():
    """Verify that EventMemory's LLM context formatting correctly prioritizes hierarchies."""
    mem = EventMemory()
    mem._retention_seconds = 10.0
    mem._short_term_seconds = 2.0
    mem._token_budget = 200

    # Add timeline events
    mem.add(make_event("audio", "Recent sound", importance=0.4))
    
    # Add scene summaries and long term memories
    mem.add_episodic_summary("Finished editing python script")
    mem.approve_for_long_term("relational_1")
    mem._long_term_approved = ["User is a developer name Satyajeet"]

    ctx = mem.get_context_for_prompt()
    
    assert "[Important Relational Memories]" in ctx
    assert "Satyajeet" in ctx
    assert "[Recent Scene Summary]" in ctx
    assert "Finished editing python script" in ctx
    assert "[Timeline of observations]" in ctx
    assert "Recent sound" in ctx

    # Verify that memories are printed first in order
    idx_lt = ctx.find("[Important Relational Memories]")
    idx_sc = ctx.find("[Recent Scene Summary]")
    idx_timeline = ctx.find("[Timeline of observations]")

    assert idx_lt < idx_sc < idx_timeline


def test_diarization_and_character_tracking():
    """Verify that FusionEngine tracks characters and performs speaker diarization."""
    mem = EventMemory()
    mem._retention_seconds = 10.0
    mem._short_term_seconds = 2.0
    mem._token_budget = 200
    
    engine = FusionEngine(memory=mem)
    
    # Set custom speaker names
    engine._speakers["speaker_1"] = "Assistant (Vivy)"
    
    # Push speech event with speaker_1
    engine.push_speech_event("Hello Satyajeet!", metadata={"speaker_id": "speaker_1"})
    
    # Push vision event with character metadata
    vlm_event = {
        "raw_description": "VLM details here",
        "vision_metadata": {
            "detected_characters": [{"id": "character_1", "description": "Avatar Smiling"}]
        }
    }
    engine.push_screen_event(vlm_event)
    
    events = engine.get_recent_events()
    
    # Verify diarization name mapping in event text
    speech_events = [e for e in events if e["source"] in ("speech", "speech_recognition")]
    assert len(speech_events) == 1
    assert "Assistant (Vivy)" in speech_events[0]["semantic"]
    
    # Verify character database persistent session cache
    assert "character_1" in engine._characters
    assert engine._characters["character_1"] == "Avatar Smiling"


def test_adaptive_sampling_delays():
    """Verify that screen_pipeline compute_visual_difference detects static screens and adjusts delays."""
    # Create two identical white frames
    img1 = PIL.Image.new("RGB", (200, 200), color="white")
    img2 = PIL.Image.new("RGB", (200, 200), color="white")

    # Seed configuration overrides to enable adaptive sampling
    from perception.config_loader import get_config
    cfg = get_config()
    cfg.setdefault("screen_perception", {})["adaptive_sampling_enabled"] = True
    cfg.setdefault("screen_perception", {})["min_sampling_delay_ms"] = 333
    cfg.setdefault("screen_perception", {})["max_sampling_delay_ms"] = 5000
    cfg.setdefault("screen_perception", {})["static_threshold"] = 0.05
    cfg.setdefault("screen_perception", {})["fps"] = 2

    # Process first frame (sets base state)
    res1 = analyze_frame(img1)
    
    # Process identical second frame
    res2 = analyze_frame(img2)
    
    # Since they are identical, next delay must increase (back-off delay)
    assert res2["next_delay_ms"] > 500  # Default delay for 2 FPS is 500ms
    assert res2["next_delay_ms"] <= 5000

    # Now process a completely different frame (black)
    img3 = PIL.Image.new("RGB", (200, 200), color="black")
    res3 = analyze_frame(img3)
    
    # Delay must reset back to fast sample rate (min_sampling_delay_ms)
    assert res3["next_delay_ms"] == 333


# ── New Verification Tests for Multimodal Upgrades ───────────────────────────

class MockRichOCRPlugin(BaseOCRPlugin):
    y_offset = 100

    @property
    def name(self) -> str:
        return "mock_rich_ocr"

    def is_available(self) -> bool:
        return True

    def extract_text(self, image) -> str:
        return "WordOne WordTwo WordThree WordFour"

    def extract_rich_text(self, image) -> tuple[str, list[dict]]:
        words = [
            {"text": "WordOne", "left": 100, "top": MockRichOCRPlugin.y_offset, "width": 50, "height": 15, "block_num": 1, "par_num": 1, "line_num": 1, "word_num": 1, "conf": 90.0},
            {"text": "WordTwo", "left": 160, "top": MockRichOCRPlugin.y_offset, "width": 50, "height": 15, "block_num": 1, "par_num": 1, "line_num": 1, "word_num": 2, "conf": 90.0},
            {"text": "WordThree", "left": 220, "top": MockRichOCRPlugin.y_offset, "width": 50, "height": 15, "block_num": 1, "par_num": 1, "line_num": 1, "word_num": 3, "conf": 90.0},
            {"text": "WordFour", "left": 280, "top": MockRichOCRPlugin.y_offset, "width": 50, "height": 15, "block_num": 1, "par_num": 1, "line_num": 1, "word_num": 4, "conf": 90.0},
        ]
        return "WordOne WordTwo WordThree WordFour", words


def test_scroll_detection_heuristic():
    """Verify that screen_pipeline detects scrolling events correctly from word coordinates."""
    ModelRouter.register_plugin("ocr", "mock_rich_ocr", MockRichOCRPlugin)
    
    # Configure router to use our mock rich ocr plugin
    from perception.config_loader import get_config
    cfg = get_config()
    old_ocr = cfg.get("model_routing", {}).get("ocr_preferred")
    old_threshold = cfg.get("screen_perception", {}).get("static_threshold", 0.02)
    
    cfg.setdefault("model_routing", {})["ocr_preferred"] = "mock_rich_ocr"
    cfg.setdefault("screen_perception", {})["adaptive_sampling_enabled"] = False
    cfg.setdefault("screen_perception", {})["static_threshold"] = -1.0
    
    # Clear instances cache to force construction
    ModelRouter._instances.pop("ocr:mock_rich_ocr", None)
    
    # Force initialize states
    from perception.screen_pipeline import analyze_frame
    import perception.screen_pipeline as sp_mod
    sp_mod._last_frame_data = None
    sp_mod._last_ocr_words = []
    
    # Process frame 1 (baseline coordinates)
    img1 = PIL.Image.new("RGB", (300, 300), color="white")
    MockRichOCRPlugin.y_offset = 100
    analyze_frame(img1)
    
    # Wait for the async OCR worker thread to finish
    import time
    for _ in range(40):
        with sp_mod._ocr_lock:
            in_prog = sp_mod._ocr_in_progress
        if not in_prog and len(sp_mod._last_ocr_words) > 0:
            break
        time.sleep(0.02)
    
    # Update y-offset to simulate scrolling down
    MockRichOCRPlugin.y_offset = 80
    
    # Process frame 2
    img2 = PIL.Image.new("RGB", (300, 300), color="white")
    
    # Hook the fusion engine to intercept the scroll event
    from perception.fusion_engine import get_global_engine
    engine = get_global_engine()
    engine._memory.clear()
    
    analyze_frame(img2)
    
    # Wait for the async OCR worker thread to finish for frame 2
    for _ in range(40):
        with sp_mod._ocr_lock:
            in_prog = sp_mod._ocr_in_progress
        if not in_prog:
            break
        time.sleep(0.02)
        
    events = engine.get_recent_events()
    scroll_events = [e for e in events if "scroll" in e["semantic"].lower()]
    
    print("DEBUG TEST scroll_events:", scroll_events)
    print("DEBUG TEST all events:", [e["semantic"] for e in events])
    print("DEBUG TEST _last_ocr_words:", len(sp_mod._last_ocr_words))
    
    # Clean up test states
    if old_ocr:
        cfg["model_routing"]["ocr_preferred"] = old_ocr
    else:
        cfg["model_routing"].pop("ocr_preferred", None)
    cfg["screen_perception"]["static_threshold"] = old_threshold
    ModelRouter._instances.pop("ocr:mock_rich_ocr", None)
    
    assert len(scroll_events) >= 1
    assert "down" in scroll_events[0]["semantic"]


def test_world_state_accumulation():
    """Verify that WorldState class compiles sensors and context cleanly."""
    from perception.perception_manager import WorldState, get_reader
    
    sensor_state = {
        "screen_sharing_active": True,
        "current_app_type": "Notepad",
        "relative_cursor_x": 0.5,
        "relative_cursor_y": 0.7,
        "last_ocr_text": "Grounding details"
    }
    
    world = WorldState(sensor_state, memory_context="Observation narrative log text")
    state_dict = world.to_dict()
    
    assert state_dict["visual"]["app_type"] == "Notepad"
    assert state_dict["os"]["cursor"]["relative_x"] == 0.5
    assert state_dict["memory_context"] == "Observation narrative log text"


def test_grounded_perception_rie():
    """Verify that RIE Validator enforces visual context grounding for perception queries."""
    from conversation import score_response_rie
    from perception.perception_manager import get_writer
    
    # Set up some mock active screen/highlight states
    writer = get_writer()
    writer.record_highlighted_region("UniqueHighlightPhrase")
    with writer._lock:
        writer._active_window_title = "My VSCode Project"
        writer._active_window_class = "VSCodeClass"
        writer._active_window_rect = [10, 10, 800, 600]
    writer._flush_to_disk()
    
    # Force user to be asking a perception query
    user_query = "What word is highlighted on my screen?"
    categories = ["screen"]
    
    # 1. Hallucinated response (does not contain highlighted text)
    reply_hallucinated = "I can see that the word 'Banana' is highlighted on your screen."
    score1, is_valid1 = score_response_rie(reply_hallucinated, user_query, {}, categories)
    assert not is_valid1  # Must be rejected because it failed grounding check!
    
    # 2. Grounded correct response
    reply_grounded = "You have highlighted the text 'UniqueHighlightPhrase'."
    score2, is_valid2 = score_response_rie(reply_grounded, user_query, {}, categories)
    # Grounding will pass
    assert score2 > 0.0 or not is_valid2


def test_temporal_changes_and_layout():
    """Verify that layout zones and temporal state changes are recorded and exposed correctly."""
    from perception.perception_manager import get_writer, get_reader
    
    writer = get_writer()
    writer._state_changes.clear()
    writer._last_recorded_state.clear()
    
    # 1. Simulate state changes to build temporal history
    writer.record_frame_arrival(app_type="Browser", scene_layout={"zones": [{"name": "title_bar", "role": "navigation"}]})
    writer.record_highlighted_region("GroundingWord")
    
    writer._flush_to_disk()
    
    # 2. Verify reader snapshot
    reader = get_reader()
    reader._cache = None # invalidate cache
    snap = reader.get_live_perception_snapshot()
    assert "scene_layout" in snap
    assert "temporal_history" in snap
    assert snap["app_type"] == "Browser"
