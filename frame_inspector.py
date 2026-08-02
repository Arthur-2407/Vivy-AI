import cv2
import json
import os
import glob
import sys
import numpy as np

POSE_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8), (9, 10),
    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
    (11, 23), (12, 24), (23, 24), (23, 25), (24, 26), (25, 27), (26, 28),
    (27, 29), (28, 30), (29, 31), (30, 32), (27, 31), (28, 32)
]

def draw_pose(img, points, color=(0, 255, 0)):
    if not points:
        return
    
    h, w = img.shape[:2]
    # Draw connections
    for p1, p2 in POSE_CONNECTIONS:
        if p1 < len(points) and p2 < len(points):
            pt1 = points[p1]
            pt2 = points[p2]
            if pt1.get("visibility", 1.0) > 0.3 and pt2.get("visibility", 1.0) > 0.3:
                cv2.line(img, (int(pt1["x"] * w), int(pt1["y"] * h)), (int(pt2["x"] * w), int(pt2["y"] * h)), color, 2)
                
    # Draw joints
    for pt in points:
        if pt.get("visibility", 1.0) > 0.3:
            cv2.circle(img, (int(pt["x"] * w), int(pt["y"] * h)), 4, (0, 0, 255), -1)

def main():
    report_dir = r"d:\Vivy\Reports\Validation"
    json_path = os.path.join(report_dir, "live_runtime_capture.json")
    frames_dir = os.path.join(report_dir, "frames")
    
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found. Please run a pipeline validation first.")
        sys.exit(1)
        
    with open(json_path, 'r', encoding='utf-8') as f:
        telemetry = json.load(f)
        
    if not telemetry:
        print("No telemetry found in the capture file.")
        sys.exit(1)
        
    video_path = None
    if len(sys.argv) > 1:
        video_path = sys.argv[1]
    else:
        authoring_dir = r"d:\Vivy\vivy_recordings\authoring"
        if os.path.exists(authoring_dir):
            vids = glob.glob(os.path.join(authoring_dir, "*.mp4"))
            if vids:
                video_path = max(vids, key=os.path.getmtime)
                
    if not video_path or not os.path.exists(video_path):
        print(f"Warning: Source video not found (looked for {video_path}). Showing only Unity frames.")
        cap = None
    else:
        print(f"Loaded reference video: {video_path}")
        cap = cv2.VideoCapture(video_path)
        
    telemetry_dict = {item["frame_id"]: item for item in telemetry}
    max_frame = max(telemetry_dict.keys()) if telemetry_dict else 0
    # Prefer actual execution_id from telemetry if available
    default_exec = "EXEC-UNKNOWN"
    if telemetry and "execution_id" in telemetry[0]:
        default_exec = telemetry[0]["execution_id"]
    elif telemetry:
        default_exec = f"EXEC-{int(telemetry[0]['timestamp'])}"
    exec_id = default_exec
    
    cv2.namedWindow("Vivy Frame Inspector - [Q or ESC to quit]", cv2.WINDOW_NORMAL)
    
    state = {"fid": 0}
    
    def update_display(val=None):
        if val is not None:
            state["fid"] = val
        fid = state["fid"]
        item = telemetry_dict.get(fid, None)
        
        ref_img = None
        if cap:
            cap.set(cv2.CAP_PROP_POS_FRAMES, fid)
            ret, frame = cap.read()
            if ret:
                ref_img = frame
                
        unity_img_path = os.path.join(frames_dir, f"unity_frame_{fid}.jpg")
        unity_img = None
        if os.path.exists(unity_img_path):
            unity_img = cv2.imread(unity_img_path)
            
        if ref_img is None:
            ref_img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(ref_img, "NO REF VIDEO", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (128, 128, 128), 2)
        if unity_img is None:
            unity_img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(unity_img, "NO UNITY FRAME", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (128, 128, 128), 2)
            
        # Match heights for side-by-side display
        h, w = ref_img.shape[:2]
        uh, uw = unity_img.shape[:2]
        if uh > 0 and uw > 0 and uh != h:
            scale = h / uh
            unity_img = cv2.resize(unity_img, (int(uw * scale), h))
            
        if item:
            draw_pose(ref_img, item.get("ref_points", []), color=(0, 255, 0))
            draw_pose(unity_img, item.get("unity_points", []), color=(255, 0, 0))
            
        sim = item["similarity"] if item else 0.0
        pos_err = item["position_error"] if item else 0.0
        bone_err = item["bone_error"] if item else 0.0
        status = item["status"] if item else "Missing Frame"
        timestamp = item["timestamp"] if item else 0.0
        
        # Calculate avg confidence from MediaPipe visibility if available
        conf = 0.0
        if item and item.get("ref_points"):
            vis_list = [p.get("visibility", 1.0) for p in item["ref_points"]]
            conf = sum(vis_list) / len(vis_list) if vis_list else 0.0
        
        # Read new metrics
        lim_class = item.get("limitation_class", "None") if item else "None"
        latency_dict = item.get("latency", {}) if item else {}
        total_latency = sum(latency_dict.values()) if latency_dict else 0.0
        
        combined = np.hstack((ref_img, unity_img))
        
        hud = np.zeros((190, combined.shape[1], 3), dtype=np.uint8)
        
        # Display true Exec ID
        disp_exec = item.get("execution_id", exec_id) if item else exec_id
        cv2.putText(hud, f"Exec ID: {disp_exec} | TS: {timestamp:.3f}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        
        cv2.putText(hud, f"Frame: {fid} / {max_frame}", (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        status_color = (0, 255, 0) if status == "Success" else (0, 0, 255)
        cv2.putText(hud, f"Status: {status}", (300, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
        if lim_class != "None":
            cv2.putText(hud, f"Limitation: {lim_class}", (750, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
        
        sim_color = (0, 255, 0) if sim > 80 else ((0, 165, 255) if sim > 60 else (0, 0, 255))
        cv2.putText(hud, f"Similarity Score: {sim:.2f}%", (10, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.8, sim_color, 2)
        cv2.putText(hud, f"Confidence: {conf*100:.1f}%", (300, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 255), 2)
        
        cv2.putText(hud, f"Position Error: {pos_err:.4f}", (10, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        cv2.putText(hud, f"Bone Error: {bone_err:.4f}", (300, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        
        if latency_dict:
            latency_str = f"Tot Latency: {total_latency*1000:.1f}ms (YOLO: {latency_dict.get('YOLO', 0.0)*1000:.1f}ms, MP: {latency_dict.get('MediaPipe', 0.0)*1000:.1f}ms, Unity: {latency_dict.get('Unity Render', 0.0)*1000:.1f}ms)"
            cv2.putText(hud, latency_str, (10, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        
        final_img = np.vstack((combined, hud))
        cv2.imshow("Vivy Frame Inspector - [Q or ESC to quit]", final_img)

    cv2.createTrackbar("Frame", "Vivy Frame Inspector - [Q or ESC to quit]", 0, max_frame, update_display)
    
    update_display(0)
    
    print("--------------------------------------------------")
    print("Vivy Frame-by-Frame Playback Inspector active.")
    print("Drag the trackbar to scrub through frames.")
    print("Press 'Q' or 'ESC' on the image window to exit.")
    print("--------------------------------------------------")
    
    while True:
        key = cv2.waitKey(100) & 0xFF
        if key == 27 or key == ord('q'):
            break
            
    cv2.destroyAllWindows()
    if cap:
        cap.release()

if __name__ == '__main__':
    main()
