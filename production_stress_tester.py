import json
import time
import sys
import os
from avatar_bridge import start_server_thread, push_animation, is_connected

REGISTRY_PATH = "d:/Vivy/vivy_animation_registry.json"
REPORT_DIR = "d:/Vivy/Reports"

def main():
    print("==================================================")
    print(" VIVY RC-1 PRODUCTION STRESS TESTER (AUTOMATED)")
    print("==================================================")
    
    os.makedirs(REPORT_DIR, exist_ok=True)
    
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        registry = json.load(f)
        
    animations = []
    for category, items in registry.get("categories", {}).items():
        for item in items:
            animations.append(item["id"])
            
    print(f"Loaded {len(animations)} animations from Registry.")
    
    start_server_thread()
    
    retries = 10
    while not is_connected() and retries > 0:
        print("Waiting for Unity connection...")
        time.sleep(1)
        retries -= 1
        
    if not is_connected():
        print("[FATAL] Unity is not connected. The RC-1 tests cannot proceed.")
        print("Ensure Unity is in Play Mode.")
        sys.exit(1)
        
    print("[SUCCESS] Unity Connected. Commencing Physical Pipeline E2E Stress Test.")
    
    import random
    random.seed(42)
    
    # Check if a sample mode or full mode was specified via command line arguments
    if "--sample" in sys.argv:
        test_set = animations[:10] + random.sample(animations[10:], 10)
        delay = 1.0
        print(f"[MODE] Sample mode selected: testing {len(test_set)} animations with {delay}s delay.")
    else:
        test_set = animations
        delay = 0.05
        print(f"[MODE] Full registry mode selected: testing ALL {len(test_set)} animations with {delay}s delay.")
    
    success_count = 0
    for anim_id in test_set:
        print(f"[TEST] Injecting Trigger -> {anim_id}")
        push_animation(anim_id)
        time.sleep(delay)
        success_count += 1
        
    print("\n[STRESS TEST] Rapid switching test (20 rapid switches)...")
    for i in range(20):
        push_animation(random.choice(animations))
        time.sleep(0.05)
        
    print("\n[SUCCESS] E2E Automated Transmission Complete.")
    print(f"Broadcasted {success_count} normal triggers and 20 stress triggers.")
    
    target_path = os.path.join(REPORT_DIR, "production_tester_result.txt")
    tmp_path = target_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(f"TEST_COMPLETED\nSENT_NORMAL={success_count}\nSENT_STRESS=20\nTOTAL_REGISTRY={len(animations)}\n")
    os.replace(tmp_path, target_path)
        
    sys.exit(0)

if __name__ == "__main__":
    main()
