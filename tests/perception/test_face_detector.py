"""
tests/perception/test_face_detector.py
=======================================
Unit tests for FaceDetector module.
"""

import unittest
import numpy as np
from perception.face_detector import FaceDetector
from perception.perception_state import FaceData


class TestFaceDetector(unittest.TestCase):

    def setUp(self):
        self.detector = FaceDetector(min_detection_confidence=0.5)

    def test_init_and_backend(self):
        backend = self.detector.get_backend_name()
        self.assertIsInstance(backend, str)
        self.assertIn(backend, ["MediaPipe", "OpenCV Haar", "Fallback Heuristic", "Unknown"])

    def test_detect_faces_empty_and_invalid(self):
        self.assertEqual(self.detector.detect_faces(None), [])
        self.assertEqual(self.detector.detect_faces(""), [])
        self.assertEqual(self.detector.detect_faces(np.zeros((0, 0, 3), dtype=np.uint8)), [])

    def test_to_numpy_bgr_synthetic(self):
        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
        img_np, h, w = self.detector._to_numpy_bgr(dummy_img)
        self.assertEqual((h, w), (100, 100))
        self.assertIsNotNone(img_np)

    def test_detect_faces_synthetic_frame(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Draw a synthetic face rectangle to test Haar/MediaPipe non-crash
        frame[100:200, 100:200] = 200
        faces = self.detector.detect_faces(frame)
        self.assertIsInstance(faces, list)


if __name__ == "__main__":
    unittest.main()
