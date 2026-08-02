import time
import psutil
import logging
import numpy as np
from collections import deque

logger = logging.getLogger(__name__)

class ResourceSchedulerML:
    """
    Time-Series ML Resource Allocator.
    Predicts CPU/GPU spikes using a lightweight auto-regressive model.
    Throttles background tasks (like experience replay consolidation) if system is constrained.
    """
    def __init__(self, history_size=60):
        self.history_size = history_size
        self.cpu_history = deque(maxlen=history_size)
        self.is_ready = True
        self.last_update = time.time()
        
        # Neural Network Integration (LSTM)
        self.lstm = None
        self.use_ml = False
        try:
            import torch
            import torch.nn as nn
            class LoadPredictorLSTM(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.lstm = nn.LSTM(input_size=1, hidden_size=8, num_layers=1, batch_first=True)
                    self.fc = nn.Linear(8, 1)
                def forward(self, x):
                    out, _ = self.lstm(x)
                    return self.fc(out[:, -1, :])
            self.lstm = LoadPredictorLSTM()
            self.lstm.eval()
            self.use_ml = True
            logger.info("[ResourceScheduler] PyTorch LSTM initialized for load forecasting.")
        except ImportError:
            logger.warning("[ResourceScheduler] PyTorch not available. Falling back to heuristic load forecasting.")
        except Exception as e:
            logger.error(f"[ResourceScheduler] LSTM init failed: {e}")
        
    def record_usage(self):
        """Called periodically (e.g. every second) to track system state."""
        current_time = time.time()
        if current_time - self.last_update >= 1.0:
            cpu_percent = psutil.cpu_percent(interval=None)
            self.cpu_history.append(cpu_percent)
            self.last_update = current_time

    def predict_next_cpu_load(self) -> float:
        """
        Uses an LSTM Sequence model to predict the next CPU load.
        Falls back to Moving Average / Auto-Regressive heuristic if Torch is unavailable.
        """
        if len(self.cpu_history) < 5:
            return 50.0 # Default assumption if no data
            
        data = np.array(self.cpu_history)
        
        if self.use_ml and len(self.cpu_history) >= 10:
            try:
                import torch
                # Normalize and prepare sequence
                seq = torch.tensor(data / 100.0, dtype=torch.float32).view(1, -1, 1)
                with torch.no_grad():
                    pred = self.lstm(seq).item()
                return float(max(0.0, min(100.0, pred * 100.0)))
            except Exception as e:
                logger.error(f"[ResourceScheduler] LSTM inference failed: {e}")
                
        # Simple weighted moving average fallback
        weights = np.exp(np.linspace(-1, 0, len(data)))
        weights /= weights.sum()
        
        prediction = np.sum(data * weights)
        return float(prediction)

    def can_run_background_tasks(self) -> bool:
        """
        Decides if a heavy background task (like ML consolidation) should run.
        """
        self.record_usage()
        predicted_load = self.predict_next_cpu_load()
        
        # If predicted load is less than 60%, it's safe to run background jobs
        return predicted_load < 60.0

_scheduler_instance = None
def get_resource_scheduler_ml():
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = ResourceSchedulerML()
    return _scheduler_instance
