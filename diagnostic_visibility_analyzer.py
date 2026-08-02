import os
import cv2
import mediapipe as mp
import glob
import json

def main():
    folder = r"D:\Vivy\Reports\Validation\FailedFrames"
    frames = glob.glob(os.path.join(folder, "*.png"))
    if not frames:
        print("No failed frames found.")
        return
        
    mp_pose = mp.solutions.pose
    # Force output even on terrible confidence
    pose_est = mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.0, min_tracking_confidence=0.0)
    
    analysis_results = []
    
    for frame_path in frames:
        frame_name = os.path.basename(frame_path)
        img = cv2.imread(frame_path)
        if img is None:
            continue
            
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        res = pose_est.process(img_rgb)
        
        causes = []
        if not res.pose_landmarks:
            causes.append("Complete Detector Collapse")
        else:
            lm = res.pose_landmarks.landmark
            # Check critical joints for low visibility (< 0.5)
            if lm[mp_pose.PoseLandmark.LEFT_WRIST].visibility < 0.5:
                causes.append("Left Wrist Occluded")
            if lm[mp_pose.PoseLandmark.RIGHT_WRIST].visibility < 0.5:
                causes.append("Right Wrist Occluded")
            if lm[mp_pose.PoseLandmark.LEFT_SHOULDER].visibility < 0.5:
                causes.append("Left Shoulder Occluded")
            if lm[mp_pose.PoseLandmark.RIGHT_SHOULDER].visibility < 0.5:
                causes.append("Right Shoulder Occluded")
            if lm[mp_pose.PoseLandmark.LEFT_ELBOW].visibility < 0.5:
                causes.append("Left Elbow Occluded")
            if lm[mp_pose.PoseLandmark.RIGHT_ELBOW].visibility < 0.5:
                causes.append("Right Elbow Occluded")
            if lm[mp_pose.PoseLandmark.LEFT_HIP].visibility < 0.5:
                causes.append("Left Hip Occluded")
            if lm[mp_pose.PoseLandmark.RIGHT_HIP].visibility < 0.5:
                causes.append("Right Hip Occluded")
                
            # If no specific joint is blatantly occluded, it might be a general avatar stylization mismatch
            if not causes:
                causes.append("Stylized Mesh Landmark Ambiguity")
                
        analysis_results.append({
            "frame": frame_name,
            "causes": causes
        })
        
    out_path = os.path.join(folder, "visibility_analysis.json")
    with open(out_path, "w") as f:
        json.dump(analysis_results, f, indent=2)
        
    print(f"Analyzed {len(frames)} failed frames. Results written to {out_path}")

if __name__ == "__main__":
    main()
