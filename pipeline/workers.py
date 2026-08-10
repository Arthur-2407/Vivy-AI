import os
import time
import shutil
import xmlrpc.client
import soundfile as sf
import sounddevice as sd
from pipeline.queues import tts_queue, rvc_queue, playback_queue
from contracts.tts_request import TTSRequest
from contracts.rvc_request import RVCRequest
from contracts.playback_request import PlaybackRequest
from pipeline.manager import pipeline_manager

SHARED_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "shared")

def run_tts_worker():
    import voice
    while True:
        try:
            chunk: TTSRequest = tts_queue.get()
        except Exception:
            continue
            
        if chunk is None:
            break
            
        if chunk.is_cancelled(pipeline_manager):
            tts_queue.task_done()
            continue
            
        out_wav = os.path.join(SHARED_DIR, f"tts_chunk_{chunk.chunk_id}_{chunk.response_id}.wav")
        try:
            voice.generate_tts_only(chunk.text, out_wav)
            chunk.wav_path = out_wav
            pipeline_manager.update_telemetry('TTSWorker', status='processing')
            if not chunk.is_cancelled(pipeline_manager):
                rvc_req = RVCRequest(response_id=chunk.response_id, chunk_id=chunk.chunk_id, sequence_number=chunk.sequence_number, text=chunk.text, wav_path_in=out_wav, is_final_chunk=chunk.is_final_chunk)
                rvc_queue.put(rvc_req)
        except Exception as e:
            print(f"[TTS Worker] Error generating TTS for chunk {chunk.chunk_id}: {e}")
            
        tts_queue.task_done()


def run_rvc_worker():
    while True:
        try:
            chunk: RVCRequest = rvc_queue.get()
        except Exception:
            continue
            
        if chunk is None:
            break
            
        if chunk.is_cancelled(pipeline_manager):
            rvc_queue.task_done()
            continue
            
        out_wav = os.path.join(SHARED_DIR, f"rvc_chunk_{chunk.chunk_id}_{chunk.response_id}.wav")
        in_wav = chunk.wav_path_in
        rvc_disabled = os.path.exists(os.path.join(SHARED_DIR, "rvc_disable.txt"))
        
        if not rvc_disabled and os.path.exists(in_wav) and os.path.getsize(in_wav) > 100:
            try:
                from voice.voice_manager import get_voice_manager
                mgr = get_voice_manager()
                active = mgr.get_active_voice()
                model_filename = active.get("model_filename", "")
                
                # Serialized XML-RPC request keeps the model resident and safe for VRAM
                proxy = xmlrpc.client.ServerProxy("http://127.0.0.1:8766", allow_none=True)
                res = proxy.convert_voice(in_wav, out_wav, 0, "rmvpe", model_filename)
                if res.get("status") == "error":
                    shutil.copy2(in_wav, out_wav)
            except Exception as e:
                print(f"[RVC Worker] RPC failed: {e}. Falling back to TTS.")
                shutil.copy2(in_wav, out_wav)
        else:
            if os.path.exists(in_wav):
                shutil.copy2(in_wav, out_wav)
                
        if os.path.exists(out_wav):
            chunk.wav_path = out_wav
            pipeline_manager.update_telemetry('TTSWorker', status='processing')
            if not chunk.is_cancelled(pipeline_manager):
                playback_queue.put(chunk)
                
        rvc_queue.task_done()


def run_playback_worker():
    import json
    
    # Track the next expected chunk_id for the current active response
    active_response_id = None
    next_expected_chunk = 0
    buffer = {} # Dict of chunk_id -> ChunkInfo for out-of-order alignment
    
    def dispatch_lip_sync(text: str, duration: float):
        # Fire-and-forget event to Avatar Bridge
        try:
            payload = {"action": "speak", "text": text, "duration": duration}
            event_path = os.path.join(SHARED_DIR, "avatar_lip_sync_event.json")
            with open(event_path + ".tmp", "w") as f:
                json.dump(payload, f)
            os.replace(event_path + ".tmp", event_path)
        except Exception: pass
        
        # Fallback mechanism for legacy Unity scripts
        try:
            with open(os.path.join(SHARED_DIR, "lip_sync_trigger.txt"), "w", encoding="utf-8") as f:
                f.write(text)
        except: pass

    while True:
        try:
            chunk: PlaybackRequest = playback_queue.get()
        except Exception:
            continue
            
        if chunk is None:
            break
            
        if chunk.is_cancelled(pipeline_manager):
            playback_queue.task_done()
            continue
            
        # Context switching handling
        if chunk.response_id != active_response_id:
            # We received a chunk for a new response!
            # Since the user might have initiated a new turn, we accept it.
            active_response_id = chunk.response_id
            next_expected_chunk = 0
            buffer.clear()
            
        buffer[chunk.chunk_id] = chunk
        
        # Play strictly in sequence
        while next_expected_chunk in buffer:
            curr = buffer.pop(next_expected_chunk)
            
            # Check cancellation right before playing
            if curr.is_cancelled(pipeline_manager):
                # If cancelled, invalidate the entire response stream
                buffer.clear()
                active_response_id = None
                break
                
            play_muted = os.path.exists(os.path.join(SHARED_DIR, "voice_output_mute.txt"))
            if not play_muted and os.path.exists(curr.wav_path):
                try:
                    data, samplerate = sf.read(curr.wav_path, dtype="float32")
                    duration = len(data) / float(samplerate)
                    
                    dispatch_lip_sync(curr.text, duration)
                    
                    # Blocking play to guarantee sequential playback
                    sd.play(data, samplerate)
                    
                    # Custom wait loop to allow instantaneous interruption
                    while sd.get_stream().active:
                        if curr.is_cancelled(pipeline_manager):
                            sd.stop()
                            buffer.clear()
                            active_response_id = None
                            break
                        time.sleep(0.01)
                        
                except Exception as e:
                    print(f"[Playback Worker] Playback error: {e}")
                    
            next_expected_chunk += 1
            
        playback_queue.task_done()
