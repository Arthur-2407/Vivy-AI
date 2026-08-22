"""
perception/gesture_suppression_gate.py
======================================
Vivy AI - Air Gesture Suppression Gate

Evaluates multimodal evidence (hand + object presence) and manages a state machine
to suppress air gestures when an object is held in the hand.
"""

import time
import logging

logger = logging.getLogger(__name__)

class GestureSuppressionGate:
    def __init__(self, block_debounce_frames: int = 2, recover_cooldown_seconds: float = 1.0):
        self.state = "GESTURE_ACTIVE"
        self.frames_suspected = 0
        self.block_debounce_frames = block_debounce_frames
        self.recover_cooldown_seconds = recover_cooldown_seconds
        self.last_suppressed_time = 0.0

    def process_frame(self, object_in_hand: bool) -> str:
        """
        Processes a single frame's object_in_hand signal.
        Returns the current gate state: GESTURE_ACTIVE, GESTURE_SUPPRESSED, or GESTURE_RECOVERING
        """
        now = time.time()

        if self.state == "GESTURE_ACTIVE":
            if object_in_hand:
                self.state = "GESTURE_SUSPECTED_BLOCK"
                self.frames_suspected = 1
        elif self.state == "GESTURE_SUSPECTED_BLOCK":
            if object_in_hand:
                self.frames_suspected += 1
                if self.frames_suspected >= self.block_debounce_frames:
                    self.state = "GESTURE_SUPPRESSED"
                    self.last_suppressed_time = now
                    logger.info("[GestureSuppressionGate] Air Gesture suppressed due to object in hand.")
            else:
                self.state = "GESTURE_ACTIVE"
                self.frames_suspected = 0
        elif self.state == "GESTURE_SUPPRESSED":
            if object_in_hand:
                self.last_suppressed_time = now
            else:
                self.state = "GESTURE_RECOVERING"
        elif self.state == "GESTURE_RECOVERING":
            if object_in_hand:
                self.state = "GESTURE_SUPPRESSED"
                self.last_suppressed_time = now
            else:
                if now - self.last_suppressed_time >= self.recover_cooldown_seconds:
                    self.state = "GESTURE_ACTIVE"
                    logger.info("[GestureSuppressionGate] Air Gesture active again.")

        return self.state

    def is_suppressed(self) -> bool:
        return self.state in ("GESTURE_SUPPRESSED", "GESTURE_RECOVERING", "GESTURE_SUSPECTED_BLOCK")
