import os
import sys
import unittest
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from perception.face_detector import FaceDetector
from perception.object_detector import ObjectDetector
from perception.face_emotion import FaceEmotionClassifier, FacialEmotion
from perception.vision_summary import VisionSummarizer
from perception.hardware_scheduler import get_hardware_scheduler
from perception.config_loader import get_config, get

class TestPhase3PerceptionModels(unittest.TestCase):

    def test_config_loader_perception_models(self):
        cfg = get_config()
        self.assertIn("perception_models", cfg)
        pm_cfg = cfg["perception_models"]
        self.assertIn("face_detection", pm_cfg)
        self.assertIn("object_detection", pm_cfg)
        self.assertIn("face_emotion", pm_cfg)
        self.assertIn("vision_summary", pm_cfg)

    def test_hardware_scheduler_assignments(self):
        hs = get_hardware_scheduler()
        self.assertIn(hs.get_assignment("face_detection"), ["cpu", "gpu"])
        self.assertIn(hs.get_assignment("object_detection"), ["cpu", "gpu"])
        self.assertEqual(hs.get_assignment("hand_tracking"), "cpu")
        self.assertEqual(hs.get_assignment("gaze_estimation"), "cpu")

    def test_face_detector_fallback_chain(self):
        detector = FaceDetector()
        backend = detector.get_backend_name()
        self.assertTrue(isinstance(backend, str) and len(backend) > 0)
        # Create a dummy 640x480 frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        faces = detector.detect_faces(frame)
        self.assertTrue(isinstance(faces, list))

    def test_object_detector_fallback_chain(self):
        detector = ObjectDetector()
        backend = detector.get_backend_name()
        self.assertTrue(isinstance(backend, str) and len(backend) > 0)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        objects = detector.detect_objects(frame)
        self.assertTrue(isinstance(objects, list))

    def test_face_emotion_classifier(self):
        classifier = FaceEmotionClassifier()
        emo = classifier.predict(None)
        self.assertTrue(isinstance(emo, FacialEmotion))
        self.assertIn(emo.label, ["neutral", "happy", "surprise", "surprised", "sad", "angry", "disgust", "fear", "fearful"])

    def test_vision_summarizer(self):
        summarizer = VisionSummarizer()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        summary = summarizer.summarize_scene(frame)
        self.assertIn("scene", summary)
        self.assertIn("ocr", summary)
        self.assertIn("motion", summary)
        self.assertIn("frame_size", summary)

if __name__ == "__main__":
    unittest.main()
