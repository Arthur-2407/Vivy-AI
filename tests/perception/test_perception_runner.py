"""
tests/perception/test_perception_runner.py
============================================
Unit & Integration tests for PerceptionRunner and PerceptionConnector
"""

import pytest
import numpy as np
import time
from perception.runner import PerceptionRunner, get_perception_runner
from perception.connectors.perception_connector import PerceptionConnector

def test_perception_connector_instantiation():
    connector = PerceptionConnector(uri="ws://127.0.0.1:8765/perception")
    assert connector.uri == "ws://127.0.0.1:8765/perception"

def test_perception_runner_single_step():
    runner = PerceptionRunner(fps=5, enabled=True)
    runner._process_single_frame_sync()
    assert runner.frame_id == 1

def test_perception_runner_reaction_rules():
    runner = PerceptionRunner(fps=5, enabled=True)
    from perception.perception_state import FaceData, GazeData
    faces = [FaceData(tracking_id=1, confidence=0.9)]
    gaze = GazeData(eye_contact_score=0.85)

    # Frame 1: eye contact score >= 0.7 -> count 1
    runner._apply_reaction_rules(faces, gaze, "happy", 0.8, {"scene": "test"})
    assert runner._consecutive_eye_contact_count == 1

    # Frame 2: eye contact score >= 0.7 -> count 2 -> sustained eye contact trigger
    runner._apply_reaction_rules(faces, gaze, "happy", 0.8, {"scene": "test"})
    assert runner._consecutive_eye_contact_count == 2
