import os
import json
import logging
import numpy as np

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    import torch
    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    _SENTENCE_TRANSFORMERS_AVAILABLE = False


class CognitionClassifierML:
    """
    Lightweight Semantic Neural Classifier for Intent and Health priority.
    Uses zero-shot few-shot nearest neighbors over embedding vectors.
    Saves LLM tokens and latency.
    """
    def __init__(self):
        self.is_ready = False
        self.model = None
        
        # Predefined Anchor Vectors for Intent (Search vs No Search)
        self.search_anchors = [
            "what is the meaning of", "how do I cook", "recipe for", "who is the president",
            "tell me about history", "what's the weather like", "recommend a good movie",
            "current news", "how tall is", "where is located"
        ]
        self.no_search_anchors = [
            "hello there", "how are you today", "i love you", "you are amazing",
            "what do you think of me", "let's just chat", "i am feeling sad",
            "i had a good day", "good morning", "goodbye"
        ]
        
        # Anchors for Health Priority
        self.health_anchors = [
            "i feel dizzy", "i am vomiting", "i have a high fever", "my head hurts badly",
            "i haven't slept in days", "i am starving", "i feel sick to my stomach",
            "i am dehydrated", "i need a doctor", "chest pain"
        ]
        self.normal_anchors = [
            "i am feeling great", "i am tired but okay", "i just woke up", "i ate a burger",
            "i am a bit sleepy", "hello", "what are we doing", "let's play a game"
        ]

        self.anchor_embeddings = {}

        if _SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                self.model = SentenceTransformer("all-MiniLM-L6-v2", device=device)
                self._compute_anchors()
                self.is_ready = True
            except Exception as e:
                logger.error(f"Failed to load Cognition Classifier ML: {e}")

    def _compute_anchors(self):
        if not self.model: return
        self.anchor_embeddings["search"] = self.model.encode(self.search_anchors).astype('float32')
        self.anchor_embeddings["no_search"] = self.model.encode(self.no_search_anchors).astype('float32')
        self.anchor_embeddings["health"] = self.model.encode(self.health_anchors).astype('float32')
        self.anchor_embeddings["normal"] = self.model.encode(self.normal_anchors).astype('float32')

    def _get_max_similarity(self, query_emb, anchor_matrix):
        """Returns the highest cosine similarity between query and a matrix of anchors."""
        query_emb = query_emb.reshape(1, -1)
        norms = np.linalg.norm(anchor_matrix, axis=1)
        q_norm = np.linalg.norm(query_emb[0])
        if q_norm == 0: return 0.0
        sims = np.dot(anchor_matrix, query_emb[0]) / (norms * q_norm + 1e-9)
        return float(np.max(sims))

    def predict_search_intent(self, text: str) -> bool:
        """Returns True if the text strongly resembles a web search intent."""
        if not self.is_ready:
            return False # Fallback to legacy
            
        emb = self.model.encode([text]).astype('float32')
        score_search = self._get_max_similarity(emb, self.anchor_embeddings["search"])
        score_no_search = self._get_max_similarity(emb, self.anchor_embeddings["no_search"])
        
        # Threshold tuning
        if score_search > 0.65 and score_search > score_no_search:
            return True
        return False

    def predict_health_priority(self, text: str) -> str:
        """Returns 'HIGH', 'MEDIUM', or 'NORMAL'."""
        if not self.is_ready:
            return "NORMAL"
            
        emb = self.model.encode([text]).astype('float32')
        score_health = self._get_max_similarity(emb, self.anchor_embeddings["health"])
        
        if score_health > 0.75:
            return "HIGH"
        elif score_health > 0.60:
            return "MEDIUM"
        else:
            return "NORMAL"

_classifier = None
def get_cognition_classifier():
    global _classifier
    if _classifier is None:
        _classifier = CognitionClassifierML()
    return _classifier
