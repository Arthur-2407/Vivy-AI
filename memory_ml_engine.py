import os
import json
import logging
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    import torch
    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    _SENTENCE_TRANSFORMERS_AVAILABLE = False

try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False

logger = logging.getLogger(__name__)

class MemoryMLEngine:
    """
    Semantic Retrieval Engine for Vivy AI Memories.
    Uses SentenceTransformers to encode memories and FAISS/Numpy for fast similarity search.
    """
    def __init__(self, db_path="memory_embeddings.json"):
        self.db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", db_path)
        self.model = None
        self.index = None
        self.texts = []
        self.is_ready = False

        if _SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                # Load from config instead of hardcoding
                config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vivy_config.json")
                model_name = "BAAI/bge-small-en-v1.5" # Default
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        model_name = cfg.get("models", {}).get("embedding", model_name)
                except Exception as e:
                    logger.warning(f"Failed to read vivy_config.json, using default embedding model. {e}")
                
                # Use a lightweight fast embedding model
                self.model = SentenceTransformer(model_name, device=device)
                self.is_ready = True
                self.load_db()
            except Exception as e:
                logger.error(f"Failed to init SentenceTransformer: {e}")
        else:
            logger.warning("sentence_transformers not installed. Memory ML engine disabled.")

    def load_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        if os.path.exists(self.db_path):
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.texts = data.get("texts", [])
                embeddings = data.get("embeddings", [])
                
                if embeddings and self.is_ready:
                    dim = len(embeddings[0])
                    if _FAISS_AVAILABLE:
                        self.index = faiss.IndexFlatL2(dim)
                        self.index.add(np.array(embeddings).astype('float32'))
                    else:
                        # Fallback to numpy dot product if FAISS not available
                        self.index = np.array(embeddings).astype('float32')

    def save_db(self):
        if not self.is_ready or self.index is None:
            return
        
        if _FAISS_AVAILABLE:
            embeddings = [self.index.reconstruct(i).tolist() for i in range(self.index.ntotal)]
        else:
            embeddings = self.index.tolist()
            
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump({"texts": self.texts, "embeddings": embeddings}, f)

    def add_memory(self, text):
        """Encodes and stores a new memory into the vector index."""
        if not self.is_ready or not text:
            return False
            
        # Avoid exact duplicates
        if text in self.texts:
            return True
            
        emb = self.model.encode([text])
        if self.index is None:
            dim = emb.shape[1]
            if _FAISS_AVAILABLE:
                self.index = faiss.IndexFlatL2(dim)
            else:
                self.index = np.empty((0, dim), dtype='float32')
                
        if _FAISS_AVAILABLE:
            self.index.add(emb.astype('float32'))
        else:
            self.index = np.vstack((self.index, emb.astype('float32')))
            
        self.texts.append(text)
        self.save_db()
        return True

    def semantic_search(self, query, top_k=3):
        """Retrieves top_k most similar memories to the query."""
        if not self.is_ready or self.index is None or len(self.texts) == 0:
            return []
            
        query_emb = self.model.encode([query]).astype('float32')
        
        if _FAISS_AVAILABLE:
            distances, indices = self.index.search(query_emb, min(top_k, self.index.ntotal))
            results = []
            for d, i in zip(distances[0], indices[0]):
                if i < len(self.texts) and i >= 0:
                    # Convert L2 distance to a 0-1 similarity score
                    results.append({"text": self.texts[i], "score": float(1.0 / (1.0 + d))})
            # Sort by score descending
            results = sorted(results, key=lambda x: x["score"], reverse=True)
            return results
        else:
            # Numpy cosine similarity fallback
            norms = np.linalg.norm(self.index, axis=1)
            q_norm = np.linalg.norm(query_emb[0])
            if q_norm == 0: return []
            sims = np.dot(self.index, query_emb[0]) / (norms * q_norm + 1e-9)
            
            top_indices = np.argsort(sims)[::-1][:min(top_k, len(self.texts))]
            results = []
            for i in top_indices:
                if sims[i] > 0.3: # Threshold for cosine similarity
                    results.append({"text": self.texts[i], "score": float(sims[i])})
            return results

_engine = None
def get_memory_ml_engine():
    global _engine
    if _engine is None:
        _engine = MemoryMLEngine()
    return _engine
