import sys
import traceback
import os

print("[TRACE] Starting import step-by-step trace...")
sys.stdout.flush()

steps = [
    ("telemetry_manager", lambda: __import__("telemetry_manager").get_telemetry_manager()),
    ("perception.config_loader", lambda: __import__("perception.config_loader")),
    ("perception.context_injector", lambda: __import__("perception.context_injector")),
    ("perception.fusion_engine", lambda: __import__("perception.fusion_engine")),
    ("perception.audio_pipeline", lambda: __import__("perception.audio_pipeline")),
    ("perception.proactivity_engine", lambda: __import__("perception.proactivity_engine")),
    ("perception.perception_manager", lambda: __import__("perception.perception_manager")),
    ("perception.plugins.speech", lambda: __import__("perception.plugins.speech")),
    ("circadian.circadian_engine", lambda: __import__("circadian.circadian_engine")),
    ("evolution", lambda: __import__("evolution")),
    ("mic_input", lambda: __import__("mic_input")),
    ("conversation", lambda: __import__("conversation")),
    ("voice", lambda: __import__("voice")),
    ("emotion.emotion", lambda: __import__("emotion.emotion")),
    ("internet", lambda: __import__("internet")),
    ("animator.animator", lambda: __import__("animator.animator")),
    ("session_manager", lambda: __import__("session_manager")),
]

for name, action in steps:
    print(f"[TRACE] Importing {name}...")
    sys.stdout.flush()
    try:
        action()
        print(f"[TRACE] Import {name} SUCCESS")
        sys.stdout.flush()
    except Exception as e:
        print(f"[TRACE] Import {name} ERROR: {e}")
        traceback.print_exc()
        sys.stdout.flush()

print("[TRACE] Step-by-step trace complete.")
