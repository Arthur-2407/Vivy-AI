import os
import threading
from transformers import pipeline
from emotion.emotion_engine import get_emotion_engine, EmotionEngine

try:
    from emotion.emotion_engine_ml import get_emotion_engine_ml
    _ml_engine = get_emotion_engine_ml()
except ImportError:
    _ml_engine = None

# Thread-safe lazy loading & background preloader for DistilRoBERTa model
_classifier = None
_classifier_lock = threading.Lock()

def get_classifier():
    """Thread-safe getter for emotion classifier. Lazy loads on first use if not preloaded."""
    global _classifier
    if _classifier is None:
        with _classifier_lock:
            if _classifier is None:
                try:
                    print("[emotion] Loading DistilRoBERTa emotion classifier...")
                    _classifier = pipeline(
                        "text-classification",
                        model="j-hartmann/emotion-english-distilroberta-base",
                        top_k=1
                    )
                    print("[emotion] DistilRoBERTa emotion classifier ready.")
                except Exception as e:
                    print(f"[emotion] Error loading emotion classifier: {e}")
                    _classifier = False
    return _classifier if _classifier is not False else None

def preload_classifier():
    """Asynchronous background preloader to initialize the classifier off the main startup thread."""
    threading.Thread(target=get_classifier, daemon=True, name="EmotionPreloader").start()

def detect_emotion(text):
    if not text or not str(text).strip():
        result = "neutral"
    else:
        try:
            clf = get_classifier()
            if clf is None:
                result = "neutral"
            else:
                res = clf(text)
                if isinstance(res, list) and len(res) > 0:
                    item = res[0]
                    if isinstance(item, list) and len(item) > 0:
                        result = item[0].get("label", "neutral")
                    elif isinstance(item, dict):
                        result = item.get("label", "neutral")
                    else:
                        result = "neutral"
                elif isinstance(res, dict):
                    result = res.get("label", "neutral")
                else:
                    result = "neutral"
        except Exception as e:
            print(f"[detect_emotion] Error classifying emotion with RoBERTa: {e}")
            if _ml_engine is not None and _ml_engine.is_ready:
                print("[detect_emotion] Falling back to Neural Embedding Emotion Engine...")
                result = _ml_engine.predict_emotion(text)
            else:
                result = "neutral"

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    shared_path = os.path.join(base_dir, "shared", "emotion.txt")
    try:
        os.makedirs(os.path.dirname(shared_path), exist_ok=True)
        with open(shared_path, "w", encoding="utf-8") as f:
            f.write(result)
    except Exception as e:
        print(f"[detect_emotion] Failed to write emotion.txt: {e}")
    return result


def modulate_emotion_with_perception(base_emotion: str, perception_state: dict) -> dict:
    """
    Modulates Vivy's internal emotional vector based on real-time face, gaze, and presence signals.
    Does not remove or break text classification.
    """
    engine = get_emotion_engine()
    vector = engine.update_vector(categories=[], perception_state=perception_state)
    vector["primary_label"] = base_emotion
    return vector

