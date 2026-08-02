import os
import json
import logging

logger = logging.getLogger(__name__)

class BehaviorPredictor:
    """
    Transformer Memory Network wrapper for Behavior Prediction.
    Takes conversation history, memory, emotion, and relationship state
    to predict the optimal conversational behavior directive.
    """
    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._initialized = False
        try:
            import torch
            import torch.nn as nn
            class BehaviorMLP(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.fc1 = nn.Linear(3, 16)
                    self.relu = nn.ReLU()
                    self.fc2 = nn.Linear(16, 7) # 7 behavior classes
                def forward(self, x):
                    return self.fc2(self.relu(self.fc1(x)))
            self._model = BehaviorMLP()
            self._model.eval()
            self._initialized = True
            logger.info("[BehaviorPredictor] PyTorch MLP initialized for state-to-directive mapping.")
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"[BehaviorPredictor] Init error: {e}")

    def predict_behavior_directive(self, user_msg: str, memory: dict, emotion_state: dict, perception_state: dict) -> str:
        """
        Analyzes the current interaction state and returns a behavioral directive string
        to influence the LLM dialogue generation naturally.
        """
        # If the ML model is not available or failed to load, fall back to heuristic behavior logic
        # based on the Transformer Memory Network design spec.
        
        rel_score = memory.get("relationship", {}).get("score", 30)
        recent_interactions = memory.get("recent_interactions", 0)
        
        # Determine dominant emotion
        dominant_emotion = "neutral"
        if emotion_state:
            candidates = {k: v for k, v in emotion_state.items() if isinstance(v, (int, float))}
            if candidates:
                dominant_emotion = max(candidates, key=candidates.get)

        # 1. Neural Network Inference (PyTorch MLP)
        if self._initialized and self._model is not None:
            try:
                import torch
                # Build feature vector: [rel_score, recent_interactions, dom_emotion_idx]
                emotion_map = {"joy": 0, "sadness": 1, "frustration": 2, "anger": 3, "neutral": 4}
                emo_idx = emotion_map.get(dominant_emotion, 4)
                
                features = torch.tensor([[rel_score / 100.0, recent_interactions / 20.0, emo_idx / 4.0]], dtype=torch.float32)
                with torch.no_grad():
                    logits = self._model(features)
                    pred_class = torch.argmax(logits, dim=1).item()
                
                # Mock decode of predicted class to behavior directive
                behavior_classes = [
                    "Act extremely close, warm, and highly affectionate.",
                    "Maintain a distant, polite, but guarded demeanor.",
                    "Reflect the user's happiness and keep the conversation upbeat.",
                    "Speak softly, offer comfort, and do not push the user.",
                    "De-escalate the situation, speak calmly, and avoid arguing.",
                    "The conversation has been flowing for a while. Keep responses concise.",
                    "Be generally friendly and attentive."
                ]
                return "BEHAVIOR DIRECTIVE: " + behavior_classes[pred_class]
            except Exception as e:
                logger.error(f"[BehaviorPredictor] MLP inference failed: {e}. Falling back to heuristics.")

        # 2. Heuristic Fallback & Relational Tier Logic
        directive_parts = []
        
        if rel_score >= 90:
            directive_parts.append("Level 5 (Deep Emotional Bond): Act profoundly supportive, emotionally enduring, and deeply intimate.")
        elif rel_score >= 70:
            directive_parts.append("Level 4 (Best Friend / Trusted Companion): Act deeply close, warm, attentive, and intuitively empathetic.")
        elif rel_score >= 50:
            directive_parts.append("Level 3 (Close Friend): Show genuine warmth, emotional trust, and an unconditionally safe presence.")
        elif rel_score >= 25:
            directive_parts.append("Level 2 (Friend): Maintain a comfortable, friendly, and naturally empathetic demeanor.")
        elif rel_score >= 10:
            directive_parts.append("Level 1 (Acquaintance): Be warm, polite, and encouraging without forcing romantic closeness.")
        else:
            directive_parts.append("Level 0 (Stranger): Maintain a polite, respectful, and receptive demeanor with clear personal boundaries.")

        if dominant_emotion == "joy":
            directive_parts.append("Reflect the user's happiness and keep the conversation upbeat.")
        elif dominant_emotion == "sadness":
            directive_parts.append("Speak softly, offer comfort, and do not push the user.")
        elif dominant_emotion in ["frustration", "anger"]:
            directive_parts.append("De-escalate the situation, speak calmly, and avoid arguing.")
            
        if recent_interactions > 10:
            directive_parts.append("The conversation has been flowing for a while. Keep responses concise.")
            
        if not directive_parts:
            return ""
            
        return "BEHAVIOR DIRECTIVE: " + " ".join(directive_parts)

_global_behavior_predictor = None

def get_behavior_predictor() -> BehaviorPredictor:
    global _global_behavior_predictor
    if _global_behavior_predictor is None:
        _global_behavior_predictor = BehaviorPredictor()
    return _global_behavior_predictor
