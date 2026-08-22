import pytest
import time
import threading
from pipeline.manager import PipelineManager, pipeline_manager
from pipeline.queues import token_queue, tts_queue
from contracts.tts_request import TTSRequest
from pipeline.chunker import run_chunker

@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup
    pipeline_manager.stop() # Ensure no global background threads are draining the queue
    pipeline_manager.workers = []
    pipeline_manager._cancelled_responses.clear()
    pipeline_manager.shutdown_event.clear()
    pipeline_manager.shutdown_state = 0 # RUNNING
    
    # Drain queues just in case
    while not token_queue.empty(): 
        try: token_queue.get_nowait()
        except: pass
    while not tts_queue.empty(): 
        try: tts_queue.get_nowait()
        except: pass
    
    yield
    
    # Teardown
    pipeline_manager.shutdown_event.set()

def test_cancellation():
    resp_id = "test-123"
    assert not pipeline_manager.is_cancelled(resp_id)
    pipeline_manager.cancel_response(resp_id)
    assert pipeline_manager.is_cancelled(resp_id)

def test_chunker_heuristics():
    # Start chunker in background
    t = threading.Thread(target=run_chunker, daemon=True)
    t.start()
    
    resp_id = "test-456"
    
    # Send tokens: "Hello. I am Vivy."
    token_queue.put({"type": "token", "text": "Hello. ", "response_id": resp_id})
    token_queue.put({"type": "token", "text": "I am ", "response_id": resp_id})
    token_queue.put({"type": "token", "text": "Vivy.", "response_id": resp_id})
    token_queue.put({"type": "final_state", "response_id": resp_id})
    
    time.sleep(0.5)
    
    # We expect 1 chunk because "Hello. " is less than MIN_CHUNK_SIZE (15)
    # So it should be aggregated into "Hello. I am Vivy."
    chunks = []
    while not tts_queue.empty():
        chunks.append(tts_queue.get())
        
    assert len(chunks) > 0
    assert chunks[-1].text == "Hello. I am Vivy."
    assert isinstance(chunks[-1], TTSRequest)
    assert chunks[-1].response_id == resp_id
    
    # Shutdown chunker
    pipeline_manager.shutdown_event.set()
    token_queue.put(None)
    t.join(timeout=1.0)
