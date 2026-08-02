import json
import time
import os
import sys

# Import the bridge functions to start the server directly
from avatar_bridge import start_server_thread, push_animation, is_connected, get_client_count

REGISTRY_PATH = "d:/Vivy/vivy_animation_registry.json"

def load_animations():
    if not os.path.exists(REGISTRY_PATH):
        print(f"[ERROR] Registry not found at {REGISTRY_PATH}")
        sys.exit(1)
        
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        registry = json.load(f)
        
    animations = []
    for category, items in registry.get("categories", {}).items():
        for item in items:
            animations.append((category, item["id"], item["layer"]))
            
    return animations

def main():
    print("==================================================")
    print("   VIVY AI - COMPLETE ANIMATION TEST SUITE")
    print("==================================================")
    print("Starting Avatar WebSocket Bridge...")
    
    # Start the bridge server in a background thread
    start_server_thread()
    
    print("Waiting for Unity to connect...")
    print("Please ensure Unity is playing and the VivyWebSocketClient is active.")
    
    # Wait up to 10 seconds for Unity to connect
    retries = 10
    while not is_connected() and retries > 0:
        time.sleep(1)
        retries -= 1
        
    if is_connected():
        print(f"\n[SUCCESS] Connected to {get_client_count()} Unity client(s)!")
    else:
        print("\n[WARNING] Unity has not connected yet. Triggers will be sent but might be missed.")
        print("Please start Unity's Play Mode.")
    
    animations = load_animations()
    total = len(animations)
    
    print("\n==================================================")
    print(f"Loaded {total} animations from registry.")
    print("Type 'next' (or just press Enter) to send the next animation.")
    print("Type 'stop' or 'quit' to exit.")
    print("==================================================\n")
    
    for idx, (cat, anim_id, layer) in enumerate(animations, 1):
        try:
            user_input = input(f"({idx}/{total}) Ready for '{anim_id}' [Layer: {layer}]. Press Enter... ").strip().lower()
            
            if user_input in ["stop", "quit", "exit"]:
                print("\n[!] Exiting Interactive Tester. Goodbye!")
                break
                
            # Direct websocket push (bypasses file writing for speed/reliability)
            push_animation(anim_id)
            print(f"[>>>] SENT TRIGGER: '{anim_id}' to Unity!")
            time.sleep(0.1)
            
        except KeyboardInterrupt:
            print("\n[!] Exiting Interactive Tester. Goodbye!")
            break

if __name__ == "__main__":
    main()
