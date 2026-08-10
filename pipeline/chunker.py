import re
import queue
from pipeline.queues import token_queue, tts_queue
from contracts.tts_request import TTSRequest
from contracts.token_event import TokenEvent
from pipeline.manager import pipeline_manager

MIN_CHUNK_SIZE = 15
MAX_CHUNK_SIZE = 150

sentence_end_pattern = re.compile(r'(?<=[.!?])\s+')

def run_chunker():
    """
    Background worker that aggregates tokens from the LLM and 
    chunks them into complete sentences before dispatching to TTS.
    """
    buffer = ""
    chunk_idx = 0
    active_response_id: str = None
    
    while True:
        try:
            item = token_queue.get()
        except Exception:
            continue
            
        if item is None:
            break
            
        if item.get("type") == "token":
            resp_id = item.get("response_id")
            
            # If context switches (new response), reset buffer
            if active_response_id != resp_id:
                active_response_id = resp_id
                buffer = ""
                chunk_idx = 0
                
            if pipeline_manager.is_cancelled(resp_id):
                token_queue.task_done()
                continue
                
            tok = item.get("text", "")
            buffer += tok
            
            if any(p in buffer for p in ['. ', '! ', '? ', '\n']):
                parts = sentence_end_pattern.split(buffer)
                if len(parts) > 1:
                    complete_text = "".join(parts[:-1]).strip()
                    if len(complete_text) >= MIN_CHUNK_SIZE:
                        if complete_text:
                            info = TTSRequest(
                                response_id=resp_id,
                                chunk_id=chunk_idx,
                                text=complete_text,
                                is_final_chunk=False
                            )
                            tts_queue.put(info)
                            chunk_idx += 1
                        buffer = parts[-1]
                    
            # Force chunk if buffer exceeds max size
            elif len(buffer) >= MAX_CHUNK_SIZE:
                # Find last space
                space_idx = buffer.rfind(" ")
                if space_idx > MIN_CHUNK_SIZE:
                    complete_text = buffer[:space_idx].strip()
                    buffer = buffer[space_idx:].lstrip()
                else:
                    complete_text = buffer.strip()
                    buffer = ""
                    
                if complete_text:
                    info = TTSRequest(
                        response_id=resp_id,
                        chunk_id=chunk_idx,
                        text=complete_text,
                        is_final_chunk=False
                    )
                    tts_queue.put(info)
                    chunk_idx += 1
                    
        elif item.get("type") == "final_state":
            resp_id = item.get("response_id")
            if resp_id and not pipeline_manager.is_cancelled(resp_id) and buffer.strip():
                info = TTSRequest(
                    response_id=resp_id,
                    chunk_id=chunk_idx,
                    text=buffer.strip(),
                    is_final_chunk=True
                )
                tts_queue.put(info)
            buffer = ""
            chunk_idx = 0
            
        token_queue.task_done()
