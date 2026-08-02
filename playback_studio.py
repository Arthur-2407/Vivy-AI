import cv2
import json
import os
import glob
import sys
import time
import numpy as np

# We share similar drawing logic with frame inspector, but with advanced overlays
POSE_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8), (9, 10),
    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
    (11, 23), (12, 24), (23, 24), (23, 25), (24, 26), (25, 27), (26, 28),
    (27, 29), (28, 30), (29, 31), (30, 32), (27, 31), (28, 32)
]

def draw_bone_heatmap(img, points1, points2):
    if not points1 or not points2:
        return
    h, w = img.shape[:2]
    # Draw connections colored by error
    for p1, p2 in POSE_CONNECTIONS:
        if p1 < len(points1) and p2 < len(points1) and p1 < len(points2) and p2 < len(points2):
            pt1_ref, pt2_ref = points1[p1], points1[p2]
            pt1_un, pt2_un = points2[p1], points2[p2]
            
            if pt1_ref.get("visibility", 1.0) > 0.3 and pt2_ref.get("visibility", 1.0) > 0.3:
                # Compute vector in ref and unity
                v_ref = np.array([pt2_ref["x"] - pt1_ref["x"], pt2_ref["y"] - pt1_ref["y"], pt2_ref.get("z", 0) - pt1_ref.get("z", 0)])
                v_un = np.array([pt2_un["x"] - pt1_un["x"], pt2_un["y"] - pt1_un["y"], pt2_un.get("z", 0) - pt1_un.get("z", 0)])
                n_ref = np.linalg.norm(v_ref)
                n_un = np.linalg.norm(v_un)
                
                sim = 1.0
                if n_ref > 0 and n_un > 0:
                    sim = max(0, np.dot(v_ref / n_ref, v_un / n_un))
                    
                # Red = high error (low sim), Green = low error (high sim)
                color = (0, int(255 * sim), int(255 * (1 - sim)))
                
                cv2.line(img, (int(pt1_un["x"] * w), int(pt1_un["y"] * h)), (int(pt2_un["x"] * w), int(pt2_un["y"] * h)), color, 3)

def render_timeline(w, h, max_frame, current_frame, telemetry_dict):
    timeline = np.zeros((h, w, 3), dtype=np.uint8)
    if max_frame <= 0: return timeline
    
    col_width = max(1.0, w / float(max_frame + 1))
    
    for fid in range(max_frame + 1):
        item = telemetry_dict.get(fid, None)
        x_start = int(fid * col_width)
        x_end = int((fid + 1) * col_width)
        if x_end <= x_start: x_end = x_start + 1
        
        if item:
            sim = item.get("similarity", 0.0) / 100.0
            status = item.get("status", "Unknown")
            
            bar_h = int(sim * (h - 10))
            if status != "Success":
                color = (0, 0, 255) # Red for error
                bar_h = h - 10
            else:
                color = (0, int(255 * sim), 0) # Green scaled by sim
                
            cv2.rectangle(timeline, (x_start, h - bar_h), (x_end, h), color, -1)
            
            # Confidence mini-bar on top
            conf = 1.0
            if item.get("ref_points"):
                vis_list = [p.get("visibility", 1.0) for p in item["ref_points"]]
                conf = sum(vis_list) / len(vis_list) if vis_list else 0.0
            conf_h = int(conf * 5)
            cv2.rectangle(timeline, (x_start, h - bar_h - conf_h - 2), (x_end, h - bar_h - 2), (255, 255, 0), -1)
            
        else:
            cv2.rectangle(timeline, (x_start, h - 10), (x_end, h), (50, 50, 50), -1)
            
    # Draw current frame marker
    cx = int((current_frame + 0.5) * col_width)
    cv2.line(timeline, (cx, 0), (cx, h), (255, 255, 255), 2)
    return timeline


def main():
    report_dir = r"d:\Vivy\Reports\Validation"
    json_path = os.path.join(report_dir, "live_runtime_capture.json")
    frames_dir = os.path.join(report_dir, "frames")
    
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        sys.exit(1)
        
    with open(json_path, 'r', encoding='utf-8') as f:
        telemetry = json.load(f)
        
    if not telemetry:
        print("No telemetry found.")
        sys.exit(1)
        
    authoring_dir = r"d:\Vivy\vivy_recordings\authoring"
    video_path = None
    if os.path.exists(authoring_dir):
        vids = glob.glob(os.path.join(authoring_dir, "*.mp4"))
        if vids:
            video_path = max(vids, key=os.path.getmtime)
            
    cap = cv2.VideoCapture(video_path) if video_path else None
    
    telemetry_dict = {item["frame_id"]: item for item in telemetry}
    max_frame = max(telemetry_dict.keys()) if telemetry_dict else 0
    
    state = {"fid": 0, "playing": False, "export": False}
    
    cv2.namedWindow("Playback Analysis Studio", cv2.WINDOW_NORMAL)
    
    def on_trackbar(val):
        state["fid"] = val
        
    cv2.createTrackbar("Frame", "Playback Analysis Studio", 0, max_frame, on_trackbar)
    
    last_time = time.time()
    
    while True:
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
        if unity_img is None:
            unity_img = np.zeros((480, 640, 3), dtype=np.uint8)
            
        h, w = ref_img.shape[:2]
        uh, uw = unity_img.shape[:2]
        if uh > 0 and uw > 0 and uh != h:
            scale = h / uh
            unity_img = cv2.resize(unity_img, (int(uw * scale), h))
            
        # Draw heatmaps if data is available
        if item and item.get("ref_points") and item.get("unity_points"):
            draw_bone_heatmap(unity_img, item["ref_points"], item["unity_points"])
            
        combined = np.hstack((ref_img, unity_img))
        
        # Info Panel
        info_panel = np.zeros((120, combined.shape[1], 3), dtype=np.uint8)
        if item:
            sim = item["similarity"]
            cv2.putText(info_panel, f"Frame: {fid}/{max_frame} | Playback: {'PLAYING' if state['playing'] else 'PAUSED'}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(info_panel, f"Similarity: {sim:.2f}% | Status: {item['status']}", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if sim > 80 else (0, 0, 255), 2)
            lat = item.get("latency", {})
            tot = sum(lat.values())
            cv2.putText(info_panel, f"Latency: {tot*1000:.1f}ms | Limitation: {item.get('limitation_class', 'None')}", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 200, 0), 2)
            cv2.putText(info_panel, f"Exec ID: {item.get('execution_id', 'UNKNOWN')}", (500, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
        
        # Timeline panel
        timeline = render_timeline(combined.shape[1], 100, max_frame, fid, telemetry_dict)
        
        final_img = np.vstack((combined, info_panel, timeline))
        
        if state["export"]:
            snap_path = os.path.join(report_dir, f"snapshot_f{fid}.png")
            cv2.imwrite(snap_path, final_img)
            print(f"Exported diagnostic snapshot to {snap_path}")
            state["export"] = False
            
        cv2.imshow("Playback Analysis Studio", final_img)
        
        key = cv2.waitKey(30) & 0xFF
        if key == 27 or key == ord('q'):
            break
        elif key == ord(' '):
            state["playing"] = not state["playing"]
        elif key == ord('e'):
            state["export"] = True
        elif key == 81 or key == ord('a'): # Left arrow
            state["fid"] = max(0, state["fid"] - 1)
            cv2.setTrackbarPos("Frame", "Playback Analysis Studio", state["fid"])
        elif key == 83 or key == ord('d'): # Right arrow
            state["fid"] = min(max_frame, state["fid"] + 1)
            cv2.setTrackbarPos("Frame", "Playback Analysis Studio", state["fid"])
            
        if state["playing"]:
            now = time.time()
            if now - last_time > 0.033: # ~30fps
                state["fid"] = (state["fid"] + 1) % (max_frame + 1)
                cv2.setTrackbarPos("Frame", "Playback Analysis Studio", state["fid"])
                last_time = now

    cv2.destroyAllWindows()
    if cap: cap.release()

if __name__ == '__main__':
    main()
