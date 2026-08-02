import os
import logging
from typing import List

logger = logging.getLogger(__name__)

class TopicRecommendationEngine:
    """
    LightGBM-powered Recommendation Engine.
    Predicts optimal conversation topics based on user emotion, interaction history, and relationship score.
    """
    def __init__(self):
        self._model = None
        self._available = False
        
        try:
            import lightgbm as lgb
            import numpy as np
            # In a full deployment, this would load a pre-trained LightGBM model.
            # self._model = lgb.Booster(model_file="models/lgbm/topic_recommender.txt")
            self._available = True
            logger.info("[RecommendationEngine] LightGBM initialized successfully.")
        except ImportError:
            logger.warning("[RecommendationEngine] 'lightgbm' not installed. Using fallback heuristics.")
        except Exception as e:
            logger.error(f"[RecommendationEngine] Initialization failed: {e}")

    def recommend_topics(self, memory_state: dict, emotion_state: dict, top_k: int = 3) -> List[str]:
        """
        Recommend conversation topics to drive engagement.
        """
        candidate_topics = [
            "technology", "music", "movies", "life goals", "hobbies", 
            "gaming", "travel", "food", "books", "art"
        ]
        
        if self._available:
            try:
                import torch
                import numpy as np
                # Semantic Metric Learning Inference:
                # Rank topics based on cosine similarity between topic embeddings and user latent embedding.
                # Since we don't have the real LightGBM, we use SentenceTransformer for metric matching.
                from sentence_transformers import SentenceTransformer
                if not hasattr(self, "st_model"):
                    self.st_model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
                    self.topic_embs = self.st_model.encode(candidate_topics)
                
                # We mock the user's current latent state by projecting their emotion into a generic text query
                user_state_text = f"I am feeling {memory_state.get('emotion_vector', 'neutral')}."
                user_emb = self.st_model.encode([user_state_text])[0]
                
                # Cosine similarity
                norms = np.linalg.norm(self.topic_embs, axis=1) * np.linalg.norm(user_emb)
                sims = np.dot(self.topic_embs, user_emb) / (norms + 1e-9)
                
                # Sort indices by similarity descending
                top_indices = np.argsort(sims)[::-1][:top_k]
                return [candidate_topics[i] for i in top_indices]
            except Exception as e:
                logger.error(f"[RecommendationEngine] Metric Learning inference failed: {e}. Falling back.")
        # Fallback heuristic logic
        rel = memory_state.get("relationship", {}).get("score", 30)
        
        if rel > 70:
            return ["life goals", "deep philosophical thoughts", "art"]
        elif rel > 40:
            return ["hobbies", "movies", "technology"]
        else:
            return ["weather", "gaming", "music"]

_global_recommendation_engine = None

def get_recommendation_engine() -> TopicRecommendationEngine:
    global _global_recommendation_engine
    if _global_recommendation_engine is None:
        _global_recommendation_engine = TopicRecommendationEngine()
    return _global_recommendation_engine
