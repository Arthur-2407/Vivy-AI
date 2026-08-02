import json
import os

def analyze():
    json_path = r"d:\Vivy\Reports\Validation\live_runtime_capture.json"
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    total = len(data)
    statuses = {}
    limits = {}
    
    for d in data:
        st = d.get("status", "Unknown")
        statuses[st] = statuses.get(st, 0) + 1
        
        lim = d.get("limitation_class", "None")
        if lim != "None":
            limits[lim] = limits.get(lim, 0) + 1
            
    print(f"Total Frames: {total}")
    print("\n--- Statuses ---")
    for k, v in statuses.items():
        print(f"{k}: {v} ({v/total*100:.1f}%)")
        
    print("\n--- Limitations (Non-Success) ---")
    for k, v in limits.items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    analyze()
