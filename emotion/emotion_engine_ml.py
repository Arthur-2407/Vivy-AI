import os
import logging
import numpy as np

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    import torch
    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    _SENTENCE_TRANSFORMERS_AVAILABLE = False


class EmotionEngineML:

    def get_canonical_emotion_state(self, user_text: str = None, face_dict: dict = None, audio_dict: dict = None):
        try:
            from contracts.emotion_state import EmotionState
            return EmotionState(
                observed_emotion=face_dict.get("emotion", "neutral") if face_dict else "neutral",
                inferred_emotion=self.predict_emotion(user_text) if user_text else "neutral",
                prosodic_emotion=audio_dict.get("emotion", "neutral") if audio_dict else "neutral",
                fused_emotion_vector={"inferred": 0.5, "observed": 0.5},
                dominance=0.5,
                arousal=0.5,
                valence=0.5
            )
        except ImportError:
            return None

    """
    Neural Emotion Prediction Engine.
    Uses zero-shot embedding distances to predict the most likely emotional state
    from text, replacing or augmenting simple keyword heuristics.
    """
    def __init__(self):
        self.is_ready = False
        self.model = None

        # Emotional clusters for distance mapping
        self.emotion_clusters = {
            "happy": ["joyful", "excited", "happy", "delighted", "thrilled", "laughing"],
            "sad": ["crying", "depressed", "sad", "miserable", "heartbroken", "gloomy"],
            "angry": ["furious", "angry", "mad", "enraged", "annoyed", "frustrated"],
            "fear": ["terrified", "scared", "fearful", "anxious", "nervous"],
            "surprise": ["shocked", "amazed", "surprised", "astonished", "wow"],
            "neutral": ["okay", "fine", "neutral", "normal", "calm", "bored"],
            "affection": ["love", "caring", "affectionate", "sweet", "romantic", "warm"]
        }
        
        self.cluster_embeddings = {}

        if _SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                self.model = SentenceTransformer("all-MiniLM-L6-v2", device=device)
                self._compute_clusters()
                self.is_ready = True
            except Exception as e:
                logger.error(f"Failed to load Emotion Engine ML: {e}")

    def _compute_clusters(self):
        if not self.model: return
        for emotion, keywords in self.emotion_clusters.items():
            # Average the embeddings of keywords to create a centroid for the emotion
            embs = self.model.encode(keywords).astype('float32')
            centroid = np.mean(embs, axis=0)
            self.cluster_embeddings[emotion] = centroid

    def predict_emotion(self, text: str) -> str:
        """
        Returns the closest emotion label based on cosine similarity to cluster centroids.
        """
        if not self.is_ready or not text:
            return "neutral"
            
        emb = self.model.encode([text]).astype('float32')[0]
        
        best_emotion = "neutral"
        best_score = -1.0
        
        q_norm = np.linalg.norm(emb)
        if q_norm == 0: return "neutral"

        for emotion, centroid in self.cluster_embeddings.items():
            c_norm = np.linalg.norm(centroid)
            sim = np.dot(emb, centroid) / (q_norm * c_norm + 1e-9)
            if sim > best_score:
                best_score = sim
                best_emotion = emotion
                
        # Only override neutral if the confidence is reasonably high
        if best_score > 0.35:
            return best_emotion
        return "neutral"

_emotion_ml = None
def get_emotion_engine_ml():
    global _emotion_ml
    if _emotion_ml is None:
        _emotion_ml = EmotionEngineML()
    return _emotion_ml
