"""
Vivy AI - ML Vision Service Facade
Exposes isolated Vision capabilities running explicitly on GPU (YOLO/Moondream).
"""
import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from perception.fusion_engine import get_global_engine
except ImportError:
    get_global_engine = None

def process_frame(frame, trigger_analysis: bool = False) -> dict:
    """
    Processes a single image frame using the Vision Engine.
    Returns detected objects, text, and contextual description.
    """
    if get_global_engine is None:
        return {"error": "Vision engine unavailable."}
        
    engine = get_global_engine()
    
    # We push the frame to the underlying fusion engine buffer.
    # If trigger_analysis is true, it forces a deep Moondream/YOLO pass.
    engine.push_screen_frame(frame)
    if trigger_analysis:
        return engine.get_fused_state()
    return {}
