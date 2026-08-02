"""
perception/emotion.py
======================
Facial Emotion Classifier interface for the perception package.
Provides modular API: predict_emotion(face_image) -> Emotion
"""

from perception.face_emotion import (
    FaceEmotionClassifier,
    FacialEmotion,
    get_face_emotion_classifier
)

# Export EmotionClassifier alias for blueprint compatibility
EmotionClassifier = FaceEmotionClassifier

def predict_emotion(face_image) -> FacialEmotion:
    """Predict emotion from face image."""
    classifier = get_face_emotion_classifier()
    return classifier.predict_emotion(face_image)
