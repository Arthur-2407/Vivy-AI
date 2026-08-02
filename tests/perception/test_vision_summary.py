"""
tests/perception/test_vision_summary.py
======================================
Unit tests for perception/vision_summary.py
"""

import pytest
import numpy as np
from perception.vision_summary import VisionSummarizer, get_vision_summarizer

def test_vision_summarizer_none_frame():
    summarizer = get_vision_summarizer()
    summary = summarizer.summarize_scene(None)
    assert isinstance(summary, dict)
    assert "scene" in summary
    assert "ocr" in summary
    assert "motion" in summary
    assert summary["frame_size"] == [0, 0]

def test_vision_summarizer_synthetic_frame():
    summarizer = VisionSummarizer()
    frame = np.full((480, 640, 3), 180, dtype=np.uint8)
    summary = summarizer.summarize(frame)
    assert isinstance(summary, dict)
    assert summary["frame_size"] == [640, 480]
    assert isinstance(summary["motion"], bool)
