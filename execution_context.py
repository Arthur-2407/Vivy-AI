import uuid
import os
import time

_EXECUTION_ID = None

def get_execution_id():
    global _EXECUTION_ID
    if _EXECUTION_ID is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        shared_file = os.path.join(base_dir, "shared", "execution_id.txt")
        try:
            if os.path.exists(shared_file):
                with open(shared_file, "r") as f:
                    _EXECUTION_ID = f.read().strip()
        except Exception as _err:
            print(f"[execution_context.py] Silenced exception: {_err}")
            
        if not _EXECUTION_ID:
            _EXECUTION_ID = f"EXEC-{uuid.uuid4().hex[:8].upper()}-{int(time.time())}"
            try:
                os.makedirs(os.path.dirname(shared_file), exist_ok=True)
                with open(shared_file, "w") as f:
                    f.write(_EXECUTION_ID)
            except Exception as _err:
                print(f"[execution_context.py] Silenced exception: {_err}")
                
    return _EXECUTION_ID

def reset_execution_id():
    global _EXECUTION_ID
    base_dir = os.path.dirname(os.path.abspath(__file__))
    shared_file = os.path.join(base_dir, "shared", "execution_id.txt")
    try:
        if os.path.exists(shared_file):
            os.remove(shared_file)
    except Exception as _err:
        print(f"[execution_context.py] Silenced exception: {_err}")
    _EXECUTION_ID = None
    return get_execution_id()
