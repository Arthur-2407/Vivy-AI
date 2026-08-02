import time
import sys
from animator.animator import VivyAnimationPlanner

def main():
    planner = VivyAnimationPlanner(bridge=None)
    
    emotions = ["joy", "sadness", "anger", "surprise", "fear", "disgust", "neutral"]
    
    for emotion in emotions:
        print(f"Testing emotion: {emotion}")
        # The planner chooses randomly, let's call it a few times to get full coverage
        for _ in range(5):
            # force cooldown bypass
            planner._last_sent_at = {}
            req = planner.on_emotion(emotion)
            if req:
                print(f"  Generated requests...")
            
    print("[DONE] Planner test successful.")
    sys.exit(0)

if __name__ == "__main__":
    main()
