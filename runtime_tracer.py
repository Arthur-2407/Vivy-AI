import sys
import os
import json
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Globals to collect trace data
execution_trace = []
modules_hit = set()
hardware_paths = set()

def trace_calls(frame, event, arg):
    if event == "call":
        func_name = frame.f_code.co_name
        filename = frame.f_code.co_filename
        
        # Only trace our own code, ignore standard library and site-packages
        if BASE_DIR in filename and "venv" not in filename:
            rel_path = os.path.relpath(filename, BASE_DIR).replace("\\", "/")
            modules_hit.add(rel_path)
            
            # Record execution path order
            execution_trace.append({
                "module": rel_path,
                "function": func_name
            })
            
            # Simple heuristic for hardware path usage
            if "torch" in filename or "cuda" in func_name.lower() or "onnx" in filename:
                hardware_paths.add("GPU/Tensor-Acceleration triggered via " + rel_path)
                
    return trace_calls

def simulate_conversation_turn():
    # We will simulate a call to conversation.score_response_rie and conversation.clean
    # to trace the cognition pipeline.
    try:
        from conversation import score_response_rie, clean
        mem = {"active_task": "none", "strategy_plan": {"strategy": "medium"}}
        raw_text = "I am Vivy AI. I can see you."
        user_input = "Who are you?"
        
        # Start tracing
        sys.settrace(trace_calls)
        
        # Execute the pipeline segment
        cleaned = clean(raw_text, user_input, mem)
        score, valid = score_response_rie(cleaned, user_input, mem, ["general"])
        
        # Stop tracing
        sys.settrace(None)
        
        return True
    except Exception as e:
        sys.settrace(None)
        print(f"Error during simulation: {e}")
        return False

def main():
    print("Starting dynamic runtime tracing of the cognitive loop...")
    success = simulate_conversation_turn()
    
    # We also check for GPU availability using torch directly to confirm paths
    try:
        import torch
        if torch.cuda.is_available():
            hardware_paths.add(f"CUDA Available: {torch.cuda.get_device_name(0)}")
        else:
            hardware_paths.add("CUDA Not Available, falling back to CPU")
    except ImportError:
        hardware_paths.add("Torch not installed")

    report = {
        "success": success,
        "modules_hit": list(modules_hit),
        "execution_path": execution_trace,
        "hardware_paths": list(hardware_paths)
    }
    
    out_path = os.path.join(BASE_DIR, "Reports", "runtime_execution_trace.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    print(f"Dynamic execution trace written to {out_path}")
    print(f"Modules hit during turn: {len(modules_hit)}")

if __name__ == "__main__":
    main()
