import sys
import os
import json
import time
import numpy as np
import cv2
import matplotlib.pyplot as plt
import math
import mediapipe as mp

def calculate_angle(v1, v2):
    v1_u = v1 / (np.linalg.norm(v1) + 1e-6)
    v2_u = v2 / (np.linalg.norm(v2) + 1e-6)
    dot = np.clip(np.dot(v1_u, v2_u), -1.0, 1.0)
    return math.degrees(math.acos(dot))

def main():
    anim_id = sys.argv[1] if len(sys.argv) > 1 else "AutoAnim_9112d6d3"
    video_path = sys.argv[2] if len(sys.argv) > 2 else r"D:\Vivy\vivy_recordings\authoring\0ab21904-930c-4478-bdcd-25beb9f0965c_SaveInta.com_AQPOvWXVJHrQrTYDLZVp09dQ7VhV61h0MSiFX73glcp_eo_BmDR152vYMzgVM5S_Nka8m3DHC8aBS7xLS4aaZOeQvD87pmisxdfbFj0.mp4"
    
    interchange_dir = r"d:\Vivy\shared\interchange"
    frames_dir = os.path.join(interchange_dir, "diagnostic_frames")
    trigger_file = os.path.join(interchange_dir, "diagnostic_trigger.json")
    dump_file = os.path.join(interchange_dir, "diagnostic_unity_dump.json")
    
    # Trigger Unity
    print(f"Triggering Unity Diagnostic Mode for {anim_id}...")
    if os.path.exists(dump_file): os.remove(dump_file)
    with open(trigger_file, "w") as f: json.dump({"anim_id": anim_id}, f)
        
    print(f"Waiting for Unity to render frames...")
    attempts = 0
    while not os.path.exists(dump_file) and attempts < 60:
        time.sleep(1)
        attempts += 1
        
    if not os.path.exists(dump_file):
        print("Timeout waiting for Unity diagnostic dump.")
        return
        
    with open(dump_file, "r") as f:
        unity_data = json.load(f)
    frames = unity_data.get("frames", [])
    
    # Process original video
    cap = cv2.VideoCapture(video_path)
    mp_pose = mp.solutions.pose.Pose(static_image_mode=False, min_detection_confidence=0.5)
    
    ref_frames = []
    pose_landmarks = []
    pose_world = []
    
    print("Extracting Reference Video and Skeletons...")
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        frame = cv2.resize(frame, (512, 512))
        ref_frames.append(frame)
        results = mp_pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        pose_landmarks.append(results.pose_landmarks)
        pose_world.append(results.pose_world_landmarks)
        if len(ref_frames) >= len(frames): break
    cap.release()
    
    # Artifact Generation
    print("Generating Video Artifacts...")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out_sbs = cv2.VideoWriter(os.path.join(interchange_dir, 'side_by_side.mp4'), fourcc, 30.0, (1024, 512))
    out_ovl = cv2.VideoWriter(os.path.join(interchange_dir, 'overlay.mp4'), fourcc, 30.0, (512, 512))
    
    for i in range(len(frames)):
        unity_frame_path = os.path.join(frames_dir, f"frame_{i:03d}.png")
        if not os.path.exists(unity_frame_path): continue
        u_frame = cv2.imread(unity_frame_path)
        if u_frame is None: continue
        
        r_frame = ref_frames[i] if i < len(ref_frames) else np.zeros((512,512,3), dtype=np.uint8)
        
        # Side by side
        sbs = np.hstack((r_frame, u_frame))
        out_sbs.write(sbs)
        
        # Overlay
        ovl = u_frame.copy()
        if i < len(pose_landmarks) and pose_landmarks[i]:
            mp.solutions.drawing_utils.draw_landmarks(ovl, pose_landmarks[i], mp.solutions.pose.POSE_CONNECTIONS)
        out_ovl.write(ovl)
        
        # Captures
        if i in [0, 30, 60, 90, 120, 150]:
            cv2.imwrite(os.path.join(interchange_dir, f'capture_{i:03d}.png'), sbs)

    out_sbs.release()
    out_ovl.release()
    
    # Analytics - ERROR ATTRIBUTION SYSTEM
    print("Generating Analytics & Error Attribution...")
    
    def get_mp_vec(lm, p1, p2):
        if not lm: return np.zeros(3)
        # MediaPipe to Unity Coordinate alignment
        return np.array([
            lm.landmark[p2].x - lm.landmark[p1].x,
            -(lm.landmark[p2].y - lm.landmark[p1].y),
            lm.landmark[p2].z - lm.landmark[p1].z
        ])

    def get_unity_vec(u_frame, parent, child):
        p_node = u_frame.get(parent)
        c_node = u_frame.get(child)
        if not p_node or not c_node: return np.zeros(3)
        return np.array([
            c_node["position"]["x"] - p_node["position"]["x"],
            c_node["position"]["y"] - p_node["position"]["y"],
            c_node["position"]["z"] - p_node["position"]["z"]
        ])

    bones = [
        ("Left Upper Arm", lambda w: get_mp_vec(w, 11, 13), lambda u: get_unity_vec(u, "LeftUpperArm", "LeftLowerArm")),
        ("Right Upper Arm", lambda w: get_mp_vec(w, 12, 14), lambda u: get_unity_vec(u, "RightUpperArm", "RightLowerArm")),
        ("Left Forearm", lambda w: get_mp_vec(w, 13, 15), lambda u: get_unity_vec(u, "LeftLowerArm", "LeftHand")),
        ("Right Forearm", lambda w: get_mp_vec(w, 14, 16), lambda u: get_unity_vec(u, "RightLowerArm", "RightHand")),
        ("Left Thigh", lambda w: get_mp_vec(w, 23, 25), lambda u: get_unity_vec(u, "LeftUpperLeg", "LeftLowerLeg")),
        ("Right Thigh", lambda w: get_mp_vec(w, 24, 26), lambda u: get_unity_vec(u, "RightUpperLeg", "RightLowerLeg")),
        ("Left Shin", lambda w: get_mp_vec(w, 25, 27), lambda u: get_unity_vec(u, "LeftLowerLeg", "LeftFoot")),
        ("Right Shin", lambda w: get_mp_vec(w, 26, 28), lambda u: get_unity_vec(u, "RightLowerLeg", "RightFoot")),
        ("Spine", lambda w: get_mp_vec(w, 23, 11) + get_mp_vec(w, 24, 12), lambda u: get_unity_vec(u, "Hips", "Chest"))
    ]
    
    error_log = {b[0]: [] for b in bones}
    for i in range(min(len(frames), len(pose_world))):
        u_frame = frames[i]
        w_frame = pose_world[i]
        for name, mp_fn, u_fn in bones:
            v_mp = mp_fn(w_frame)
            v_u = u_fn(u_frame)
            if np.linalg.norm(v_mp) > 0 and np.linalg.norm(v_u) > 0:
                err = calculate_angle(v_mp, v_u)
                error_log[name].append(err)
            else:
                error_log[name].append(0)

    # Compute rankings
    ranked_errors = []
    total_error = 0
    for name, errs in error_log.items():
        avg_err = np.mean(errs) if errs else 0
        ranked_errors.append((name, avg_err))
        total_error += avg_err

    ranked_errors.sort(key=lambda x: x[1], reverse=True)
    
    heatmap_data = np.zeros((len(bones), len(frames)))
    for b_idx, (name, _, _) in enumerate(bones):
        for i, err in enumerate(error_log[name]):
            heatmap_data[b_idx, i] = err
                
    plt.figure(figsize=(10, 4))
    plt.imshow(heatmap_data, aspect='auto', cmap='hot', interpolation='nearest')
    plt.colorbar(label='Angular Error (Degrees)')
    plt.yticks(ticks=np.arange(len(bones)), labels=[b[0] for b in bones])
    plt.xlabel('Frame Number')
    plt.title('Subsystem Angular Error Heatmap')
    plt.tight_layout()
    plt.savefig(os.path.join(interchange_dir, 'angular_error_heatmap.png'))
    plt.close()

    # Report Output
    report = [
        "# VIVY AI - ERROR ATTRIBUTION SYSTEM REPORT (ROOT-CAUSE MODE)",
        "## PHASE 3: HIGHEST CONTRIBUTORS RANKING\n",
        f"**Animation ID:** `{anim_id}` | **Frames Analyzed:** `{len(frames)}`\n",
        "| Rank | Subsystem | Average Angular Error | Contribution % |",
        "|------|-----------|-----------------------|----------------|"
    ]
    
    for i, (name, avg_err) in enumerate(ranked_errors):
        contribution = (avg_err / total_error * 100) if total_error > 0 else 0
        report.append(f"| {i+1} | {name} | {avg_err:.2f}° | {contribution:.1f}% |")

    report.extend([
        "\n## 1. HEATMAPS & KINEMATICS",
        "![Heatmap](/d:/Vivy/shared/interchange/angular_error_heatmap.png)\n",
        "## 2. SYNCHRONIZED FRAME CAPTURES",
        "*(Left: Raw Reference Video | Right: Headless Unity Engine Render)*\n",
        "![Frame 0](/d:/Vivy/shared/interchange/capture_000.png)",
        "![Frame 30](/d:/Vivy/shared/interchange/capture_030.png)",
        "![Frame 60](/d:/Vivy/shared/interchange/capture_060.png)",
        "![Frame 90](/d:/Vivy/shared/interchange/capture_090.png)\n",
        "## 3. ROOT-CAUSE ATTRIBUTION STATUS",
        "The diagnostic framework successfully isolated the subsystem errors. Review the rankings above to select the highest contributor for Phase 5 optimization.",
        "**PIPELINE: ERROR ATTRIBUTION COMPLETE**"
    ])
    with open("D:/Vivy/output.md", "a", encoding="utf-8") as f:
        f.write("\n" + "\n".join(report))
    print("V6.0 Report Complete!")

if __name__ == '__main__':
    main()
