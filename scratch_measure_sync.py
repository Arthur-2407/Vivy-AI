import os
import json
import statistics

def main():
    json_path = r"d:\Vivy\Reports\Validation\live_runtime_capture.json"
    if not os.path.exists(json_path):
        print("Telemetry not found.")
        return
        
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    if not data:
        print("Empty telemetry.")
        return
        
    # Synchronization metrics
    timestamps = []
    latencies = []
    timeouts = 0
    low_conf = 0
    success = 0
    sync_mismatch = 0
    invalid_data = 0
    
    for item in data:
        timestamps.append(item["timestamp"])
        st = item["status"]
        if st == "Success":
            success += 1
        elif st == "Shared Memory Timeout":
            timeouts += 1
        elif st == "Low MediaPipe Confidence":
            low_conf += 1
        elif st == "WebSocket Sync Mismatch":
            sync_mismatch += 1
        else:
            invalid_data += 1
            
    for i in range(1, len(timestamps)):
        latencies.append(timestamps[i] - timestamps[i-1])
        
    total_frames = len(data)
    
    if latencies:
        avg_lat = statistics.mean(latencies) * 1000
        med_lat = statistics.median(latencies) * 1000
        min_lat = min(latencies) * 1000
        max_lat = max(latencies) * 1000
        p95_lat = sorted(latencies)[int(len(latencies) * 0.95)] * 1000
    else:
        avg_lat = med_lat = min_lat = max_lat = p95_lat = 0.0

    print("=== SYNCHRONIZATION METRICS ===")
    print(f"Total Frames: {total_frames}")
    print(f"Success: {success} ({success/total_frames*100:.1f}%)")
    print(f"Timeouts: {timeouts} ({timeouts/total_frames*100:.1f}%)")
    print(f"Low Confidence: {low_conf} ({low_conf/total_frames*100:.1f}%)")
    print(f"Sync Mismatch: {sync_mismatch} ({sync_mismatch/total_frames*100:.1f}%)")
    print(f"Invalid Data: {invalid_data} ({invalid_data/total_frames*100:.1f}%)")
    print("\n--- Latency (ms) ---")
    print(f"Average: {avg_lat:.2f} ms")
    print(f"Median : {med_lat:.2f} ms")
    print(f"Min    : {min_lat:.2f} ms")
    print(f"Max    : {max_lat:.2f} ms")
    print(f"95th P : {p95_lat:.2f} ms")

if __name__ == "__main__":
    main()
