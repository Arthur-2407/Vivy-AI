import json
import time
import os
import sys

REGISTRY_PATH = "d:/Vivy/vivy_animation_registry.json"
TRIGGER_FILE = "d:/Vivy/shared/animation_trigger.txt"

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

def send_trigger(anim_id):
    """Sends the trigger to the Vivy animation bridge via the shared IPC file."""
    os.makedirs(os.path.dirname(TRIGGER_FILE), exist_ok=True)
    with open(TRIGGER_FILE, "w", encoding="utf-8") as f:
        f.write(anim_id)
    print(f"\n[>>>] SENT TRIGGER: '{anim_id}' to Unity!")

def main():
    print("==================================================")
    print("   VIVY AI - INTERACTIVE ANIMATION TESTER")
    print("==================================================")
    print("This tool will step through all 313 mapped animations.")
    print("Make sure Unity is running and the Animator is open.")
    print("==================================================\n")
    
    animations = load_animations()
    total = len(animations)
    
    print(f"Loaded {total} animations from registry.")
    print("Type 'next' (or just press Enter) to send the next animation.")
    print("Type 'stop' or 'quit' to exit.\n")
    
    for idx, (cat, anim_id, layer) in enumerate(animations, 1):
        try:
            user_input = input(f"({idx}/{total}) Ready for '{anim_id}' [Layer: {layer}]. Press Enter... ").strip().lower()
            
            if user_input in ["stop", "quit", "exit"]:
                print("\n[!] Exiting Interactive Tester. Goodbye!")
                break
                
            send_trigger(anim_id)
            time.sleep(0.1) # Small buffer
            
        except KeyboardInterrupt:
            print("\n[!] Exiting Interactive Tester. Goodbye!")
            break

if __name__ == "__main__":
    main()
