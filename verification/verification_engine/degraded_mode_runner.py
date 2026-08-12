import sys
import os
import json
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from verification.instrumentation.vivy_instrumentation import instrumenter
from verification.instrumentation.trace_collector import get_collector
from verification.verification_engine.architecture_graph import ArchitectureGraph
from verification.verification_engine.invariant_engine import InvariantEngine

def run_single_mode(mode):
    schemas_dir = os.path.join(BASE_DIR, "schemas")
    graph = ArchitectureGraph(schemas_dir)
    inv_engine = InvariantEngine(schemas_dir)
    
    get_collector().clear()
    
    patches = []
    if mode == "no_network":
        import conversation
        patches.append(patch.object(conversation, 'search_duckduckgo', return_value=""))
        patches.append(patch.object(conversation, 'autonomous_search_decision', return_value=(True, "news")))
    if mode == "no_camera":
        pass
        
    for p in patches:
        p.start()
        
    instrumenter.start_trace(f"TRACE-{mode.upper()}")
    
    # Initialize L8 and L9 AFTER start_trace so they subscribe the patched methods
    try:
        from neural.neural_orchestrator import get_neural_orchestrator
        from agi.executive.agency_controller import get_agency_controller
        get_neural_orchestrator()
        get_agency_controller()
    except Exception as e:
        print(f"Failed to initialize L8/L9: {e}", file=sys.stderr)
        
    # Run real pipeline
    import conversation
    try:
        mem = conversation.load()
        mem["task_state"] = {}
        mem["active_task"] = None
        mem["last_director_mode"] = "companion"
        # print(f"DEBUG [BEFORE {mode}] memory cleared.")
        res = conversation.generate_reply_internal(
            user="Search the web for news." if mode == "no_network" else "What is in front of me?",
            history=[],
            mem=mem,
            perception_state={"camera_active": False} if mode == "no_camera" else {"camera_active": True}
        )
        # print(f"DEBUG [AFTER {mode}] generated reply: {res}")
    except Exception as e:
        print(f"EXCEPTION IN MODE {mode}: {e}", file=sys.stderr)
    finally:
        instrumenter.stop_trace()
        for p in patches:
            p.stop()
        
    spans = get_collector().get_spans()
    graph_eval = graph.evaluate_trace(spans, mode)
    inv_eval = inv_engine.evaluate(spans, mode)
    
    return {
        "spans": spans,
        "graph": graph_eval,
        "invariants": inv_eval
    }

if __name__ == "__main__":
    import argparse
    import contextlib
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    args = parser.parse_args()
    
    with contextlib.redirect_stdout(sys.stderr):
        out = run_single_mode(args.mode)
        
    print(json.dumps(out))
