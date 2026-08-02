import sys

with open('D:/Vivy/animation_authoring_pipeline.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_block = """                if live_unity_detected:
                    try:
                        shmem = mmap.mmap(-1, 2 * 1024 * 1024, tagname="VivyAvatarFrame")
                        shmem.seek(0)
                        size_data = shmem.read(8)
                        size, f_count = struct.unpack("<II", size_data)
                        
                        if size == 0 or f_count == last_f_count:
                            live_unity_detected = False
                            
                        if live_unity_detected and size > 0 and size < 2000000:
                            last_f_count = f_count
                            img_data = shmem.read(size)
                            np_arr = np.frombuffer(img_data, np.uint8)
                            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                            
                            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                            mp_pose = mp.solutions.pose
                            with mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.5) as pose_est:
                                res = pose_est.process(img_rgb)
                                if res.pose_landmarks:
                                    ref_points = frame
                                    unity_points = res.pose_landmarks.landmark
                                    
                                    total_dist = 0
                                    pairs = 0
                                    for i in range(min(33, len(ref_points), len(unity_points))):
                                        dx = ref_points[i]['x'] - unity_points[i].x
                                        dy = ref_points[i]['y'] - unity_points[i].y
                                        # MediaPipe Z is relative, scale it down for error metric
                                        dz = (ref_points[i].get('z', 0) - unity_points[i].z) * 0.5
                                        total_dist += (dx**2 + dy**2 + dz**2)**0.5
"""

lines.insert(453, new_block)

with open('D:/Vivy/animation_authoring_pipeline.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
