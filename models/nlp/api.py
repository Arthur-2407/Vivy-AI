"""
Vivy AI - ML NLP Service Facade
Exposes isolated NLP capability APIs running explicitly on GPU (if available).
"""
import sys
import os

# Ensure the root path is accessible to import cognition_classifiers
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from cognition_classifiers import get_cognition_classifier

def predict_intent(text: str) -> str:
    """Predicts high-level intent from user text using Neural Classification."""
    classifier = get_cognition_classifier()
    if classifier.predict_search_intent(text):
        return "search"
    return "general"

def predict_health_priority(text: str) -> str:
    """Predicts health/safety priority from user text (HIGH/MEDIUM/NORMAL)."""
    classifier = get_cognition_classifier()
    return classifier.predict_health_priority(text)
