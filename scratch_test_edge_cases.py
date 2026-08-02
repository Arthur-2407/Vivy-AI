import time
import sys
from avatar_bridge import start_server_thread, push_animation, is_connected

def main():
    print("Starting server thread...")
    start_server_thread()
    
    print("Waiting for Unity to connect...")
    retries = 10
    while not is_connected() and retries > 0:
        time.sleep(1)
        retries -= 1
        
    if not is_connected():
        print("[FAIL] Unity did not connect.")
        sys.exit(1)
        
    animations = [
        "Wave",
        "Point",
        "Walk",
        "Run",
        "Sit",
        "Stand",
        "Smile",
        "Nod",
        "Shake head",
        "Idle",
        "Unknown animation",
        "Invalid animation ID"
    ]
    
    for anim in animations:
        print(f"Sending '{anim}'...")
        push_animation(anim)
        time.sleep(0.5)
        
    print("[DONE] Transmission successful.")
    time.sleep(1) # wait a moment for unity to process
    sys.exit(0)

if __name__ == "__main__":
    main()
