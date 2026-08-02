import os
import json
import time
import logging

logger = logging.getLogger(__name__)

class ExperienceReplay:
    """
    Self-Learning Module: Experience Replay Buffer
    Logs state-action-reward tuples for continuous offline fine-tuning of embedding models
    and conversational reinforcement learning, without destroying existing memory.
    """
    def __init__(self, log_dir="logs/replay"):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.log_dir = os.path.join(self.base_dir, log_dir)
        self.replay_file = os.path.join(self.log_dir, "experience_buffer.jsonl")
        
        os.makedirs(self.log_dir, exist_ok=True)
        
        # In-memory buffer before flushing to disk
        self.buffer = []
        self.buffer_size_limit = 50

    def log_interaction(self, user_input: str, ai_response: str, 
                        context_state: dict, emotion_state: str, 
                        reward_proxy: float = 0.0):
        """
        Logs a single turn of interaction.
        reward_proxy can be derived from subsequent user sentiment (e.g. if the user says "thank you", reward is high).
        """
        if not user_input or not ai_response:
            return

        experience = {
            "timestamp": time.time(),
            "user_input": user_input,
            "ai_response": ai_response,
            "context_state": context_state,
            "emotion": emotion_state,
            "reward": reward_proxy
        }
        
        self.buffer.append(experience)
        
        if len(self.buffer) >= self.buffer_size_limit:
            self.flush()

    def flush(self):
        """Writes buffer to JSONL and clears it."""
        if not self.buffer:
            return
            
        try:
            with open(self.replay_file, "a", encoding="utf-8") as f:
                for exp in self.buffer:
                    f.write(json.dumps(exp) + "\n")
            self.buffer = []
        except Exception as e:
            logger.error(f"Failed to flush experience replay: {e}")

    def consolidate_learning(self):
        """
        Offline process hook. Could be triggered during idle periods to scan the replay buffer
        and update embedding models or adjust generation temperatures.
        """
        pass # To be implemented by the resource scheduler when idle

_replay_instance = None
def get_experience_replay():
    global _replay_instance
    if _replay_instance is None:
        _replay_instance = ExperienceReplay()
    return _replay_instance
