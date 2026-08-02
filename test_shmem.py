import mmap
import struct
import cv2
import numpy as np
import time

def check_shmem():
    try:
        shmem = mmap.mmap(-1, 2 * 1024 * 1024, tagname="VivyAvatarFrame")
        shmem.seek(0)
        size_data = shmem.read(8)
        size, f_count = struct.unpack("<II", size_data)
        
        print(f"Read f_count: {f_count}, size: {size}")
        if size > 0 and size < 2000000:
            img_data = shmem.read(size)
            np_arr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            
            if img is not None:
                cv2.imwrite(r"D:\Vivy\Reports\Validation\test_shmem_capture.jpg", img)
                print("Image saved successfully.")
                
                import mediapipe as mp
                mp_pose = mp.solutions.pose
                with mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.5) as pose_est:
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    res = pose_est.process(img_rgb)
                    if res.pose_world_landmarks:
                        print("MediaPipe successfully detected pose.")
                    else:
                        print("MediaPipe FAILED to detect pose in this image.")
            else:
                print("Failed to decode image!")
        else:
            print("Size is invalid.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_shmem()
