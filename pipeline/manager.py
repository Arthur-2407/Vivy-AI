import threading
import time
from typing import Set, Dict
from enum import Enum

class ShutdownState(Enum):
    RUNNING = 0
    NORMAL_STOP = 1
    EMERGENCY_SHUTDOWN = 2

class PipelineManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PipelineManager, cls).__new__(cls)
            cls._instance._init_state()
        return cls._instance
        
    def _init_state(self):
        self._cancelled_responses: Set[str] = set()
        self._cancellation_lock = threading.Lock()
        
        self.shutdown_state = ShutdownState.RUNNING
        self.shutdown_event = threading.Event()
        
        self.telemetry: Dict[str, Dict] = {
            "STTWorker": {"running": False, "queue_depth": 0, "last_activity": 0},
            "LLMWorker": {"running": False, "queue_depth": 0, "last_activity": 0},
            "TTSWorker": {"running": False, "queue_depth": 0, "last_activity": 0},
            "RVCWorker": {"running": False, "queue_depth": 0, "last_activity": 0},
            "PlaybackWorker": {"running": False, "queue_depth": 0, "last_activity": 0},
        }
        self.workers = []
        
    def cancel_response(self, response_id: str):
        """Thread-safe cancellation registry."""
        if response_id:
            with self._cancellation_lock:
                self._cancelled_responses.add(response_id)
            
    def is_cancelled(self, response_id: str) -> bool:
        """Thread-safe cancellation check."""
        with self._cancellation_lock:
            return response_id in self._cancelled_responses
        
    def update_telemetry(self, worker_name: str, **kwargs):
        if worker_name in self.telemetry:
            self.telemetry[worker_name].update(kwargs)
            self.telemetry[worker_name]["last_activity"] = time.time()
            
    def start(self):
        print("[PipelineManager] Starting workers...")
        self.shutdown_state = ShutdownState.RUNNING
        self.shutdown_event.clear()
        
        from pipeline.chunker import run_chunker
        from pipeline.workers import run_tts_worker, run_rvc_worker, run_playback_worker
        
        self.workers = [
            threading.Thread(target=run_chunker, daemon=True, name="SentenceChunker"),
            threading.Thread(target=run_tts_worker, daemon=True, name="TTSWorker"),
            threading.Thread(target=run_rvc_worker, daemon=True, name="RVCWorker"),
            threading.Thread(target=run_playback_worker, daemon=True, name="PlaybackWorker")
        ]
        
        for w in self.workers:
            w.start()
            
    def stop(self):
        """Normal Stop: Stop accepting new work, let queues drain naturally."""
        print("[PipelineManager] Normal Stop requested. Draining queues...")
        self.shutdown_state = ShutdownState.NORMAL_STOP
        self.shutdown_event.set()
        
        from pipeline.queues import token_queue, tts_queue, rvc_queue, playback_queue, text_queue
        try:
            token_queue.put_nowait(None)
            tts_queue.put_nowait(None)
            rvc_queue.put_nowait(None)
            playback_queue.put_nowait(None)
            text_queue.put_nowait(None)
        except Exception:
            pass
            
        for w in self.workers:
            w.join(timeout=3.0)
        print("[PipelineManager] Normal Shutdown complete.")
        
    def emergency_shutdown(self):
        """Emergency Shutdown: Discard pending work, cancel active responses immediately."""
        print("[PipelineManager] Emergency Shutdown requested! Cancelling all work...")
        self.shutdown_state = ShutdownState.EMERGENCY_SHUTDOWN
        self.shutdown_event.set()
        
        # Stop sounddevice playback immediately if playing
        try:
            import sounddevice as sd
            if sd.get_stream().active:
                sd.stop()
        except Exception:
            pass
            
        # Put None in queues to abort workers
        from pipeline.queues import token_queue, tts_queue, rvc_queue, playback_queue, text_queue
        try:
            token_queue.put_nowait(None)
            tts_queue.put_nowait(None)
            rvc_queue.put_nowait(None)
            playback_queue.put_nowait(None)
            text_queue.put_nowait(None)
        except Exception:
            pass
            
        for w in self.workers:
            w.join(timeout=1.0)
        print("[PipelineManager] Emergency Shutdown complete.")

pipeline_manager = PipelineManager()
