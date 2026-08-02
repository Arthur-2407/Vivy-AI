import time
import mmap
import struct
import numpy as np
import cv2

print("Simulating Unity Live Mode (Streaming REAL Frames to MMap)...")

try:
    _shmem = mmap.mmap(-1, 2 * 1024 * 1024, tagname="VivyAvatarFrame")
except Exception as e:
    print(f"Failed to create shmem: {e}")
    exit(1)

# Extract a real frame from the video so MediaPipe detects a pose
video_path = r"D:\Vivy\vivy_recordings\authoring\0ab21904-930c-4478-bdcd-25beb9f0965c_SaveInta.com_AQPOvWXVJHrQrTYDLZVp09dQ7VhV61h0MSiFX73glcp_eo_BmDR152vYMzgVM5S_Nka8m3DHC8aBS7xLS4aaZOeQvD87pmisxdfbFj0.mp4"
cap = cv2.VideoCapture(video_path)
ret, frame = cap.read()
if not ret:
    print("Failed to read video!")
    exit(1)
cap.release()

# Resize to expected dimensions
frame = cv2.resize(frame, (640, 480))
success, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
img_data = buffer.tobytes()

frame_count = 1000

while True:
    try:
        _shmem.seek(0)
        _shmem.write(struct.pack("<II", len(img_data), frame_count))
        _shmem.write(img_data)
        _shmem.flush()
        frame_count += 1
        time.sleep(1/60.0) # 60 FPS
    except KeyboardInterrupt:
        break
    except Exception as e:
        print(f"Error: {e}")
        break

print("Stopped Unity Simulation.")
