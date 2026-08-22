from dataclasses import dataclass
from typing import List

@dataclass
class PerceptionSnapshot:
    """Canonical Perception Data for a Single Turn"""
    timestamp: float
    face_visible: bool
    gaze_target: str
    detected_objects: List[str]
    hand_gestures: List[str]
    ambient_audio_class: str
    is_avatar_active: bool
    
    def to_dict(self):
        return self.__dict__
