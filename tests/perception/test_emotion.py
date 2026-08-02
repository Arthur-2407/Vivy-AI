"""
tests/perception/test_emotion.py
==================================
Unit tests for FaceEmotionClassifier module.
"""

import unittest
import numpy as np
from perception.face_emotion import FaceEmotionClassifier, FacialEmotion, get_face_emotion_classifier
from perception.emotion import predict_emotion, EmotionClassifier


class TestEmotionClassifier(unittest.TestCase):

    def setUp(self):
        self.classifier = get_face_emotion_classifier()

    def test_singleton_instance(self):
        inst1 = get_face_emotion_classifier()
        inst2 = get_face_emotion_classifier()
        self.assertIs(inst1, inst2)
        self.assertIsInstance(self.classifier, FaceEmotionClassifier)

    def test_predict_emotion_none(self):
        emo = self.classifier.predict_emotion(None)
        self.assertIsInstance(emo, FacialEmotion)
        self.assertEqual(emo.label, "neutral")
        self.assertGreaterEqual(emo.confidence, 0.5)

    def test_facial_emotion_to_dict(self):
        emo = FacialEmotion(label="happy", confidence=0.85, valence=0.7, arousal=0.4)
        d = emo.to_dict()
        self.assertEqual(d["label"], "happy")
        self.assertEqual(d["confidence"], 0.85)
        self.assertEqual(d["valence"], 0.7)
        self.assertEqual(d["arousal"], 0.4)

    def test_predict_emotion_synthetic_image(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        emo = predict_emotion(img)
        self.assertIsInstance(emo, FacialEmotion)
        self.assertIn(emo.label, ["neutral", "happy", "sad", "angry", "surprised", "fearful", "disgusted"])

    def test_blueprint_alias(self):
        self.assertIs(EmotionClassifier, FaceEmotionClassifier)


if __name__ == "__main__":
    unittest.main()
