"""
tests/perception/test_facial_emotion.py
========================================
Unit tests for perception/face_emotion.py
"""

import pytest
import numpy as np
from perception.face_emotion import FaceEmotionClassifier, FacialEmotion, get_face_emotion_classifier
from perception.perception_state import FaceData, EyeData, HeadPose

def test_facial_emotion_classifier_default():
    classifier = get_face_emotion_classifier()
    emo = classifier.predict_emotion(None)
    assert isinstance(emo, FacialEmotion)
    assert emo.label == "neutral"
    assert emo.confidence >= 0.5
    assert -1.0 <= emo.valence <= 1.0
    assert 0.0 <= emo.arousal <= 1.0

def test_facial_emotion_from_synthetic_image():
    classifier = FaceEmotionClassifier()
    # Create a 64x64 synthetic BGR image
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    img[20:30, 20:40] = 255 # synthetic feature
    emo = classifier.predict_emotion(img)
    assert isinstance(emo, FacialEmotion)
    assert emo.label in ["neutral", "happy", "surprised", "sad", "angry", "fearful", "disgusted"]

def test_facial_emotion_from_landmarks():
    classifier = FaceEmotionClassifier()
    face = FaceData(
        left_eye=EyeData(ear=0.4, eye_openness=0.9),
        right_eye=EyeData(ear=0.4, eye_openness=0.9),
        head_pose=HeadPose(pitch=5.0)
    )
    emo = classifier.predict_emotion(None, face_landmarks=face)
    assert emo.label == "surprised"
