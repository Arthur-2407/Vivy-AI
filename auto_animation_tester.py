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
    print("   VIVY AI - AUTOMATED ANIMATION TEST SUITE")
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
    print("The test will now cycle through all 313 animations AUTOMATICALLY.")
    print("It will wait 2 seconds between each animation.")
    print("Press Ctrl+C at any time to stop.")
    print("==================================================\n")
    
    # Give the user a moment to switch over to the Unity window
    for i in range(5, 0, -1):
        print(f"Starting in {i} seconds... Switch to Unity!")
        time.sleep(1)
    
    for idx, (cat, anim_id, layer) in enumerate(animations, 1):
        try:
            print(f"({idx}/{total}) Triggering '{anim_id}' [Layer: {layer}] ...")
            push_animation(anim_id)
            
            # Wait 2.5 seconds to let the animation play out in Unity before the next one
            time.sleep(2.5)
            
        except KeyboardInterrupt:
            print("\n[!] Exiting Automated Tester. Goodbye!")
            break

if __name__ == "__main__":
    main()
