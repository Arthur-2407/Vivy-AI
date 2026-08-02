import cv2
import mediapipe as mp
import numpy as np
import json

def test():
    # create a dummy blank image
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # draw a person-like shape so MediaPipe detects something?
    # Or just use an image from vivy_recordings/authoring or shared/interchange
    import os
    img_path = os.path.join("shared", "interchange", "capture_000.png")
    if os.path.exists(img_path):
        img = cv2.imread(img_path)
    else:
        print("capture_000.png not found")
        return

    mp_pose = mp.solutions.pose
    with mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.1) as pose_est:
        res = pose_est.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if res.pose_landmarks and res.pose_world_landmarks:
            print("--- FRAME MEASUREMENTS ---")
            for i in [0, 11, 12]: # Nose, L Shoulder, R Shoulder
                lm = res.pose_landmarks.landmark[i]
                wlm = res.pose_world_landmarks.landmark[i]
                print(f"Joint {i}:")
                print(f"  pose_landmarks (Normalized 2D/3D): x={lm.x:.4f}, y={lm.y:.4f}, z={lm.z:.4f}")
                print(f"  pose_world_landmarks (Metric 3D): x={wlm.x:.4f}, y={wlm.y:.4f}, z={wlm.z:.4f}")
                dist = ((lm.x - wlm.x)**2 + (lm.y - wlm.y)**2 + (lm.z - wlm.z)**2)**0.5
                print(f"  Euclidean distance: {dist:.4f}")
        else:
            print("No pose detected in image.")

if __name__ == "__main__":
    test()
