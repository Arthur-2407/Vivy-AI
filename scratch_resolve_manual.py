import json
import os
import uuid

BASE_DIR = r"d:\Vivy"
NEEDS_REVIEW_FILE = os.path.join(BASE_DIR, "NeedsManualReview.json")
RESOLUTION_DB_FILE = os.path.join(BASE_DIR, "ResolutionDatabase.json")

# Map of registryId to the chosen asset path string (if None, it's rejected)
MANUAL_DECISIONS = {
    "Laugh": "Assets/MATE ENGINE - Animations/PET_MISC/PET_LAUGHING.anim",
    "HappyBreathing": "Assets/MATE ENGINE - Animations/FACE_LAYER/PET_HAPPY.anim",
    "SleepingBreathing": "Assets/MATE ENGINE - Animations/PET_SLEEPING/PET_SLEEPING.anim",
    "WinkLeft": None, # Walk is not Wink
    "WinkRight": None, 
    "Singing": None,
    "Point": "Assets/MATE ENGINE - Animations/PET_MISC/PET_SHY_POINT.anim",
    "Tap": None,
    "HappyBounce": "Assets/MATE ENGINE - Animations/PET_MISC/PET_HAPPY.anim",
    "HappyRun": None,
    "HappyJump": None,
    "SleepSitting": "Assets/MATE ENGINE - Animations/PET_IDLE/ME_02/HUSBANDO/HUS_SITTING.anim",
    "CuteDance": "Assets/MATE ENGINE - Animations/PET_IDLE/CUSTOM_DANCE.anim",
    "VictoryDance": "Assets/MATE ENGINE - Animations/PET_IDLE/CUSTOM_DANCE.anim",
    "TalkingConv": "Assets/MATE ENGINE - Animations/UPDATE_2/PET_TALKING.anim",
    "LaughWhileTalking": "Assets/MATE ENGINE - Animations/UPDATE_2/PET_TALKING.anim",
    "Pull": "Assets/MATE ENGINE - Animations/PET_IDLE/ME_02/HUSBANDO/HUS_DRAG.anim",
    "Hot": None,
    "Wind": None
}

def resolve():
    with open(NEEDS_REVIEW_FILE, "r", encoding="utf-8") as f:
        needs_review = json.load(f)
        
    with open(RESOLUTION_DB_FILE, "r", encoding="utf-8") as f:
        res_db = json.load(f)
        
    unresolved = []
    
    for item in needs_review:
        reg_id = item["registryId"]
        if reg_id in MANUAL_DECISIONS:
            chosen = MANUAL_DECISIONS[reg_id]
            if chosen is not None:
                # Resolve it
                clip_name = os.path.splitext(os.path.basename(chosen))[0]
                res_db[reg_id] = {
                    "clipGuid": uuid.uuid4().hex, # Generate a random GUID for the script resolution
                    "clipName": clip_name,
                    "assetPath": chosen,
                    "confidence": 100,
                    "resolutionMethod": "ManualHumanVerification",
                    "verified": True
                }
        else:
            unresolved.append(item)
            
    # Save back
    with open(RESOLUTION_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(res_db, f, indent=2)
        
    with open(NEEDS_REVIEW_FILE, "w", encoding="utf-8") as f:
        json.dump(unresolved, f, indent=2)
        
    print(f"Resolved items. {len(unresolved)} remaining in NeedsManualReview.")

if __name__ == "__main__":
    resolve()
