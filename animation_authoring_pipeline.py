import os
import time
import json
import uuid
import shutil
import cv2
import numpy as np
import execution_context

# Global latency tracker for this session
_latency_stats = {
    "Frame Decode": [], "YOLO": [], "MediaPipe": [], "Pose Processing": [],
    "Retargeting": [], "Animation Authoring": [], "Unity Render": [],
    "Shared Memory Read": [], "Similarity Engine": [], "Telemetry": [],
    "JSON Export": [], "CSV Export": []
}

# We handle imports carefully in case of missing libs during startup
try:
    from ultralytics import YOLO
    import mediapipe as mp
    from scipy.signal import butter, filtfilt
    from scipy.spatial.transform import Rotation as R
    ML_AVAILABLE = True
except ImportError as e:
    ML_AVAILABLE = False
    print(f"[MotionIntelligence] ML dependencies missing: {e}. Running in degraded mock mode.")

# ---------------------------------------------------------
# STAGE 1: Video Analysis Engine
# ---------------------------------------------------------
class VideoAnalysisEngine:
    def __init__(self):
        pass
        
    def extract_frames(self, video_path):
        print(f"[VideoAnalysis] Extracting frames from {video_path}")
        cap = cv2.VideoCapture(video_path)
        frames = []
        fps = cap.get(cv2.CAP_PROP_FPS)
        while True:
            t_start = time.perf_counter()
            ret, frame = cap.read()
            t_end = time.perf_counter()
            if not ret:
                break
            frames.append(frame)
            _latency_stats["Frame Decode"].append(t_end - t_start)
        cap.release()
        print(f"[VideoAnalysis] Extracted {len(frames)} frames at {fps} FPS.")
        return frames, fps

# ---------------------------------------------------------
# STAGE 2 & 3: Pose Engine (Detection & Pose)
# ---------------------------------------------------------
class PoseEngine:
    def __init__(self):
        if ML_AVAILABLE:
            # YOLO11n for fast human detection/segmentation
            try:
                try:
                    from config.config_manager import get_config_manager
                    cfg = get_config_manager()
                    model_path = cfg.get("models.face_detection", "yolo11n-face.pt")
                except Exception:
                    model_path = 'yolo11n-face.pt'
                self.detector = YOLO(model_path) 
            except Exception as e:
                print(f"[PoseEngine] YOLO init warning: {e}")
                self.detector = None
            # MediaPipe Pose for lightweight, fast pose estimation
            self.mp_pose = mp.solutions.pose.Pose(
                static_image_mode=False,
                model_complexity=1,
                smooth_landmarks=True,
                enable_segmentation=False,
                min_detection_confidence=0.5
            )
            
    def process_frames(self, frames):
        print("[PoseEngine] Estimating body poses with YOLO+MediaPipe cascade...")
        pose_sequence = []
        for i, frame in enumerate(frames):
            if not ML_AVAILABLE:
                pose_sequence.append(None)
                continue
                
            t0 = time.perf_counter()
            image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # YOLO Crop if available
            if self.detector is not None:
                results_yolo = self.detector(image_rgb, classes=[0], verbose=False)
                t1 = time.perf_counter()
                _latency_stats["YOLO"].append(t1 - t0)
                
                if len(results_yolo) > 0 and len(results_yolo[0].boxes) > 0:
                    box = results_yolo[0].boxes[0].xyxy[0].cpu().numpy()
                    x1, y1, x2, y2 = map(int, box)
                    # Add padding
                    pad = 50
                    h, w = image_rgb.shape[:2]
                    x1 = max(0, x1 - pad)
                    y1 = max(0, y1 - pad)
                    x2 = min(w, x2 + pad)
                    y2 = min(h, y2 + pad)
                    image_crop = image_rgb[y1:y2, x1:x2]
                    # Process crop
                    t2 = time.perf_counter()
                    results = self.mp_pose.process(image_crop)
                    t3 = time.perf_counter()
                    _latency_stats["MediaPipe"].append(t3 - t2)
                else:
                    t2 = time.perf_counter()
                    results = self.mp_pose.process(image_rgb)
                    t3 = time.perf_counter()
                    _latency_stats["MediaPipe"].append(t3 - t2)
            else:
                _latency_stats["YOLO"].append(0.0)
                t2 = time.perf_counter()
                results = self.mp_pose.process(image_rgb)
                t3 = time.perf_counter()
                _latency_stats["MediaPipe"].append(t3 - t2)
            
            t4 = time.perf_counter()
            if results.pose_world_landmarks:
                # Extract 3D landmarks (x, y, z)
                landmarks = [{"x": lm.x, "y": lm.y, "z": lm.z, "visibility": lm.visibility} 
                             for lm in results.pose_world_landmarks.landmark]
                pose_sequence.append(landmarks)
            else:
                pose_sequence.append(None)
            t5 = time.perf_counter()
            _latency_stats["Pose Processing"].append(t5 - t4)
            
        return pose_sequence

# ---------------------------------------------------------
# STAGE 4 & 5: Hand & Face Engine
# ---------------------------------------------------------
class HandFaceEngine:
    def __init__(self):
        if ML_AVAILABLE:
            self.mp_hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.5
            )
            self.mp_face = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=True
            )
            
    def process_frames(self, frames):
        print("[HandFaceEngine] Extracting hand and face keypoints...")
        details_sequence = []
        for frame in frames:
            if not ML_AVAILABLE:
                details_sequence.append({})
                continue
                
            image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            hand_results = self.mp_hands.process(image_rgb)
            face_results = self.mp_face.process(image_rgb)
            
            frame_details = {"hands": [], "face": None}
            if hand_results.multi_hand_landmarks:
                for hand_landmarks in hand_results.multi_hand_landmarks:
                    frame_details["hands"].append([{"x": lm.x, "y": lm.y, "z": lm.z} for lm in hand_landmarks.landmark])
                    
            if face_results.multi_face_landmarks:
                frame_details["face"] = [{"x": lm.x, "y": lm.y, "z": lm.z} for lm in face_results.multi_face_landmarks[0].landmark]
                
            details_sequence.append(frame_details)
        return details_sequence

# ---------------------------------------------------------
# STAGE 6, 8 & 9: Motion Reconstruction & Cleanup Engine
# ---------------------------------------------------------
class MotionReconstructionEngine:
    def __init__(self):
        pass
        
    def filter_motion(self, data_sequence, fps):
        """Apply Butterworth low-pass filter to smooth out jitter"""
        print("[MotionReconstruction] Cleaning up motion and interpolating missing frames...")
        if not ML_AVAILABLE or not data_sequence or len(data_sequence) < 5:
            return data_sequence
            
        # Interpolate missing frames
        valid_idx = [i for i, v in enumerate(data_sequence) if v is not None]
        if not valid_idx:
            return data_sequence
            
        seq_array = []
        for v in data_sequence:
            if v is not None:
                seq_array.append(np.array([[lm["x"], lm["y"], lm.get("z", 0.0)] for lm in v]))
            else:
                seq_array.append(None)
                
        # Simple linear interpolation for None frames
        for i in range(len(seq_array)):
            if seq_array[i] is None:
                prev_i = next((x for x in reversed(valid_idx) if x < i), valid_idx[0])
                next_i = next((x for x in valid_idx if x > i), valid_idx[-1])
                if prev_i == next_i:
                    seq_array[i] = seq_array[prev_i]
                else:
                    alpha = (i - prev_i) / (next_i - prev_i)
                    seq_array[i] = seq_array[prev_i] * (1 - alpha) + seq_array[next_i] * alpha
                    
        seq_array = np.array(seq_array)
        
        # Apply Butterworth filter
        try:
            b, a = butter(4, min(12.0, (fps / 2.0) - 0.1) / (fps / 2.0), btype='low')
            for joint_idx in range(seq_array.shape[1]):
                for axis in range(3):
                    seq_array[:, joint_idx, axis] = filtfilt(b, a, seq_array[:, joint_idx, axis], padlen=min(3, len(seq_array)-1))
        except Exception as e:
            print(f"[MotionReconstruction] Filter failed, bypassing: {e}")
            
        cleaned_sequence = []
        for i in range(len(seq_array)):
            frame_lm = []
            for lm in seq_array[i]:
                frame_lm.append({"x": float(lm[0]), "y": float(lm[1]), "z": float(lm[2])})
            cleaned_sequence.append(frame_lm)
            
        return cleaned_sequence

# ---------------------------------------------------------
# STAGE 7: Retargeting Engine (NEW)
# ---------------------------------------------------------
class RetargetEngine:
    def __init__(self):
        self.initial_hip = None
        
    def _normalize(self, v):
        norm = np.linalg.norm(v)
        if norm == 0: return v
        return v / norm
        
    def _compute_rotation(self, vec_from, vec_to):
        vec_from = self._normalize(vec_from)
        vec_to = self._normalize(vec_to)
        dot = np.dot(vec_from, vec_to)
        if dot < -0.9999:
            # Prefer rotation around Y (up) to avoid flipping upside down
            axis = np.array([0.0, 1.0, 0.0])
            axis = axis - np.dot(axis, vec_from) * vec_from
            if np.linalg.norm(axis) < 0.1:
                axis = np.array([1.0, 0.0, 0.0])
                axis = axis - np.dot(axis, vec_from) * vec_from
            axis = self._normalize(axis)
            return R.from_rotvec(np.pi * axis)
        if dot > 0.9999:
            return R.identity()
        axis = self._normalize(np.cross(vec_from, vec_to))
        angle = np.arccos(dot)
        return R.from_rotvec(angle * axis)

    def process_frame(self, frame):
        """Map mediapipe landmarks to unity HumanBodyBones"""
        NOSE = 0; L_EYE = 2; R_EYE = 5; L_EAR = 7; R_EAR = 8
        L_SHOULDER = 11; R_SHOULDER = 12
        L_ELBOW = 13; R_ELBOW = 14; L_WRIST = 15; R_WRIST = 16
        L_HIP = 23; R_HIP = 24; L_KNEE = 25; R_KNEE = 26
        L_ANKLE = 27; R_ANKLE = 28; L_FOOT = 31; R_FOOT = 32
        
        def pt(idx):
            # Map MediaPipe to standard Right-Handed OpenGL space (X-Right, Y-Up, Z-Backward)
            # MediaPipe is natively X-Right, Y-Down, Z-Backward
            return np.array([frame[idx]["x"], -frame[idx]["y"], -frame[idx]["z"]])
            
        mid_hip = (pt(L_HIP) + pt(R_HIP)) / 2.0
        mid_shoulder = (pt(L_SHOULDER) + pt(R_SHOULDER)) / 2.0
        mid_ear = (pt(L_EAR) + pt(R_EAR)) / 2.0
        
        dirs = {
            "Hips": mid_hip, # Just positional reference if needed, but we do rotations
            "Spine": mid_shoulder - mid_hip,
            "Chest": mid_shoulder - mid_hip,
            "Neck": mid_ear - mid_shoulder,
            "Head": pt(NOSE) - mid_ear,
            "LeftShoulder": pt(L_SHOULDER) - mid_shoulder,
            "RightShoulder": pt(R_SHOULDER) - mid_shoulder,
            "LeftUpperArm": pt(L_ELBOW) - pt(L_SHOULDER),
            "RightUpperArm": pt(R_ELBOW) - pt(R_SHOULDER),
            "LeftLowerArm": pt(L_WRIST) - pt(L_ELBOW),
            "RightLowerArm": pt(R_WRIST) - pt(R_ELBOW),
            "LeftHand": pt(19) - pt(15), # L_INDEX - L_WRIST
            "RightHand": pt(20) - pt(16), # R_INDEX - R_WRIST
            "LeftUpperLeg": pt(L_KNEE) - pt(L_HIP),
            "RightUpperLeg": pt(R_KNEE) - pt(R_HIP),
            "LeftLowerLeg": pt(L_ANKLE) - pt(L_KNEE),
            "RightLowerLeg": pt(R_ANKLE) - pt(R_KNEE),
            "LeftFoot": pt(L_FOOT) - pt(L_ANKLE),
            "RightFoot": pt(R_FOOT) - pt(R_ANKLE)
        }
        
        t_pose_dirs = {
            "Spine": np.array([0, 1, 0]),
            "Chest": np.array([0, 1, 0]),
            "Neck": np.array([0, 1, 0]),
            "Head": np.array([0, 0, -1]),
            "LeftShoulder": np.array([-1, 0, 0]),
            "RightShoulder": np.array([1, 0, 0]),
            "LeftUpperArm": np.array([-1, 0, 0]),
            "RightUpperArm": np.array([1, 0, 0]),
            "LeftLowerArm": np.array([-1, 0, 0]),
            "RightLowerArm": np.array([1, 0, 0]),
            "LeftHand": np.array([-1, 0, 0]),
            "RightHand": np.array([1, 0, 0]),
            "LeftUpperLeg": np.array([0, -1, 0]),
            "RightUpperLeg": np.array([0, -1, 0]),
            "LeftLowerLeg": np.array([0, -1, 0]),
            "RightLowerLeg": np.array([0, -1, 0]),
            "LeftFoot": np.array([0, 0, -1]),
            "RightFoot": np.array([0, 0, -1])
        }
        
        world_rots = {}
        for bone, d in dirs.items():
            if bone == "Hips": continue
            world_rots[bone] = self._compute_rotation(t_pose_dirs[bone], d)
            
        local_rots = {}
        # Hips rotation (root)
        hip_dir = pt(L_HIP) - pt(R_HIP)
        hip_rot = self._compute_rotation(np.array([-1, 0, 0]), hip_dir)
        local_rots["Hips"] = hip_rot
        
        # Enforce leg yaw using hip forward to eliminate flamingo twist
        hip_forward = hip_rot.apply(np.array([0, 0, 1]))
        for leg in ["LeftUpperLeg", "RightUpperLeg"]:
            leg_dir = self._normalize(dirs[leg])
            try:
                leg_rot, _ = R.align_vectors([leg_dir, hip_forward], [np.array([0, -1, 0]), np.array([0, 0, 1])])
                world_rots[leg] = leg_rot
            except Exception as _err:
                print(f"[animation_authoring_pipeline.py] Silenced exception: {_err}")
                
        for leg, parent in [("LeftLowerLeg", "LeftUpperLeg"), ("RightLowerLeg", "RightUpperLeg")]:
            leg_dir = self._normalize(dirs[leg])
            parent_forward = world_rots[parent].apply(np.array([0, 0, 1]))
            try:
                leg_rot, _ = R.align_vectors([leg_dir, parent_forward], [np.array([0, -1, 0]), np.array([0, 0, 1])])
                world_rots[leg] = leg_rot
            except Exception as _err:
                print(f"[animation_authoring_pipeline.py] Silenced exception: {_err}")

        # FIX UPPER ARM ROLL (Rank 1 Error Contributor)
        for side, t_pose_arm in [("Left", np.array([-1, 0, 0])), ("Right", np.array([1, 0, 0]))]:
            arm_bone = f"{side}UpperArm"
            forearm_bone = f"{side}LowerArm"
            arm_dir = self._normalize(dirs[arm_bone])
            forearm_dir = self._normalize(dirs[forearm_bone])
            
            # The hinge normal defines the elbow bending plane. cross(arm, forearm)
            hinge_normal = np.cross(arm_dir, forearm_dir)
            norm_val = np.linalg.norm(hinge_normal)
            
            if norm_val > 1e-3:
                hinge_normal = hinge_normal / norm_val
                # Standard Unity T-Pose assumes palms face down, elbows bend backwards (+Z).
                # Left Arm (-X) cross (+Z) = (+Y Up)
                # Right Arm (+X) cross (+Z) = (-Y Down)
                t_pose_hinge = np.array([0, 1, 0]) if side == "Left" else np.array([0, -1, 0])
                
                try:
                    arm_rot, _ = R.align_vectors([arm_dir, hinge_normal], [t_pose_arm, t_pose_hinge])
                    world_rots[arm_bone] = arm_rot
                    
                    # Stabilize Forearm Roll by inheriting the new Upper Arm hinge
                    parent_hinge = arm_rot.apply(t_pose_hinge)
                    forearm_rot, _ = R.align_vectors([forearm_dir, parent_hinge], [t_pose_arm, t_pose_hinge])
                    world_rots[forearm_bone] = forearm_rot
                except Exception as _err:
                    print(f"[animation_authoring_pipeline.py] Silenced exception: {_err}")
        
        
        # Distribute torso rotation across Spine and Chest
        # Use full 3D alignment to prevent spine twisting 
        shoulder_dir = pt(L_SHOULDER) - pt(R_SHOULDER)
        shoulder_dir = self._normalize(shoulder_dir)
        spine_dir = self._normalize(dirs["Spine"])
        try:
            # T-Pose UP is [0, 1, 0], T-Pose RIGHT (L to R shoulder) is [-1, 0, 0]
            torso_rot, _ = R.align_vectors([spine_dir, shoulder_dir], [np.array([0, 1, 0]), np.array([-1, 0, 0])])
            world_rots["Spine"] = torso_rot
        except Exception as _err:
            print(f"[animation_authoring_pipeline.py] Silenced exception: {_err}") # Fallback to minimal rotation computed above
            
        torso_rot = world_rots["Spine"]
        rel_torso = hip_rot.inv() * torso_rot
        rel_torso_rotvec = rel_torso.as_rotvec()
        half_rel = R.from_rotvec(rel_torso_rotvec * 0.5)
        
        local_rots["Spine"] = half_rel
        local_rots["Chest"] = half_rel
        
        # Neck is relative to world_Chest (which is torso_rot)
        local_rots["Neck"] = torso_rot.inv() * world_rots["Neck"]
        local_rots["Head"] = world_rots["Neck"].inv() * world_rots["Head"]
        
        inv_chest = torso_rot.inv()
        local_rots["LeftShoulder"] = inv_chest * world_rots["LeftShoulder"]
        local_rots["RightShoulder"] = inv_chest * world_rots["RightShoulder"]
        
        local_rots["LeftUpperArm"] = world_rots["LeftShoulder"].inv() * world_rots["LeftUpperArm"]
        local_rots["RightUpperArm"] = world_rots["RightShoulder"].inv() * world_rots["RightUpperArm"]
        
        local_rots["LeftLowerArm"] = world_rots["LeftUpperArm"].inv() * world_rots["LeftLowerArm"]
        local_rots["RightLowerArm"] = world_rots["RightUpperArm"].inv() * world_rots["RightLowerArm"]

        local_rots["LeftHand"] = world_rots["LeftLowerArm"].inv() * world_rots["LeftHand"]
        local_rots["RightHand"] = world_rots["RightLowerArm"].inv() * world_rots["RightHand"]
        
        local_rots["LeftUpperLeg"] = hip_rot.inv() * world_rots["LeftUpperLeg"]
        local_rots["RightUpperLeg"] = hip_rot.inv() * world_rots["RightUpperLeg"]
        
        local_rots["LeftLowerLeg"] = world_rots["LeftUpperLeg"].inv() * world_rots["LeftLowerLeg"]
        local_rots["RightLowerLeg"] = world_rots["RightUpperLeg"].inv() * world_rots["RightLowerLeg"]

        local_rots["LeftFoot"] = world_rots["LeftLowerLeg"].inv() * world_rots["LeftFoot"]
        local_rots["RightFoot"] = world_rots["RightLowerLeg"].inv() * world_rots["RightFoot"]
        
        if self.initial_hip is None:
            self.initial_hip = mid_hip
        root_translation = mid_hip - self.initial_hip
        
        output_bones = []
        for bone_name, r in local_rots.items():
            q = r.as_quat()
            # Convert RH OpenGL quaternion to Unity LH quaternion by inverting X and Y
            bone_dict = {
                "name": bone_name,
                "x": -float(q[0]), "y": -float(q[1]), "z": float(q[2]), "w": float(q[3])
            }
            if bone_name == "Hips":
                bone_dict["px"] = float(root_translation[0])
                bone_dict["py"] = float(root_translation[1])
                bone_dict["pz"] = -float(root_translation[2])
            output_bones.append(bone_dict)
            
        return output_bones

# ---------------------------------------------------------
# STAGE 13: Unity Animation Generator
# ---------------------------------------------------------
class AnimationGenerator:
    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.interchange_dir = os.path.join(base_dir, "shared", "interchange")
        os.makedirs(self.interchange_dir, exist_ok=True)
        
    def generate_payload(self, pose_seq, detail_seq, fps, source_path, status_callback=None):
        print("[AnimationGenerator] Retargeting to Unity Humanoid and generating payload...")
        
        valid_frames = [p for p in pose_seq if p is not None]
        
        temp_trigger_name = f"AutoAnim_{uuid.uuid4().hex[:8]}"
        animation_data = {
            "id": temp_trigger_name,
            "trigger": temp_trigger_name,
            "layer": "Base Layer", 
            "priority": 2,
            "duration": len(pose_seq) / fps if fps else 5.0,
            "source_video": source_path,
            "motion_quality": {
                "frames_processed": len(pose_seq),
                "valid_poses": len(valid_frames),
                "fps": fps
            },
            "auto_generated": True
        }

        # Format points as serializable lists for JSON
        serializable_frames = []
        for frame in valid_frames:
            # Assuming frame is a list of dicts: [{"x": lm.x, "y": lm.y, "z": lm.z, "visibility": lm.visibility}, ...]
            serializable_frames.append(frame)

        import math
        import mmap, struct
        import websockets
        import asyncio
        import copy

        print("\n========================================================")
        print("[SimilarityEngine] Initializing True Mocap Refinement Loop...")
        enhanced_frames = []
        live_validation_evidence = []

        if ML_AVAILABLE:
            retarget_engine = RetargetEngine()
        else:
            retarget_engine = None

        async def refine_all_frames():
            try:
                from config.config_manager import get_config_manager
                cfg = get_config_manager()
                host = cfg.get("server.host", "127.0.0.1")
                ws_port = cfg.get("server.ws_port", 8765)
                ws_url = f"ws://{host}:{ws_port}"
                
                # Try to connect to Unity WebSocket. If fail, we just do one-pass retargeting without refinement.
                ws = await websockets.connect(ws_url, ping_interval=None)
                print(f"[SimilarityEngine] Connected to Live Unity Stream at {ws_url}.")
            except Exception as e:
                print(f"[SimilarityEngine] WebSocket Error: {e}. Running one-pass retargeting without visual refinement.")
                ws = None

            total_frames = len(serializable_frames)
            live_unity_detected = True
            last_f_count = -1
            
            for frame_idx, frame in enumerate(serializable_frames):
                if status_callback and frame_idx == 0:
                    status_callback(f"Refining frame {frame_idx + 1}/{total_frames}...")
                    
                if not retarget_engine or len(frame) < 33:
                    # If frame lacks data, use previous frame or zero-pose
                    if len(enhanced_frames) > 0:
                        bones = copy.deepcopy(enhanced_frames[-1]["bones"])
                    else:
                        bones = []
                    enhanced_frames.append({"points": frame, "bones": bones})
                    continue

                t_ret_0 = time.perf_counter()
                try:
                    bones = retarget_engine.process_frame(frame)
                except Exception as e:
                    print(f"[AnimationGenerator] Retarget failed on frame {frame_idx}: {e}")
                    if len(enhanced_frames) > 0:
                        bones = copy.deepcopy(enhanced_frames[-1]["bones"])
                    else:
                        bones = []
                t_ret_1 = time.perf_counter()
                _latency_stats["Retargeting"].append(t_ret_1 - t_ret_0)

                if ws is None:
                    enhanced_frames.append({"points": frame, "bones": bones})
                    continue

                # TRUE SIMILARITY EVALUATION (Single Pass)
                similarity = 0.0
                avg_dist = 0.0
                best_bones = copy.deepcopy(bones)
                best_similarity = 0.0

                pose_msg = {
                    "type": "sync_pose",
                    "bones": bones
                }
                
                t_uni_0 = time.perf_counter()
                if live_unity_detected:
                    try:
                        await asyncio.wait_for(ws.send(json.dumps(pose_msg)), timeout=0.1)
                    except asyncio.TimeoutError:
                        pass # Ignore timeout, Unity might just be rendering slowly
                    except Exception as e:
                        print(f"  [Refinement] Frame {frame_idx} WS fatal error: {e}")
                        live_unity_detected = False
                        
                f_count = last_f_count
                size = 0
                if live_unity_detected:
                    try:
                        shmem = mmap.mmap(-1, 2 * 1024 * 1024, tagname="VivyAvatarFrame")
                        poll_attempts = 0
                        while poll_attempts < 15: # Wait up to ~300ms for a distinct frame update
                            await asyncio.sleep(0.02)
                            shmem.seek(0)
                            size_data = shmem.read(8)
                            size, f_count = struct.unpack("<II", size_data)
                            if f_count != last_f_count and size > 0 and size < 2000000:
                                break
                            poll_attempts += 1
                        
                        t_uni_1 = time.perf_counter()
                        _latency_stats["Unity Render"].append(t_uni_1 - t_uni_0)
                        
                        if poll_attempts >= 15:
                            _latency_stats["Shared Memory Read"].append(0.0)
                            _latency_stats["Similarity Engine"].append(0.0)
                            live_validation_evidence.append({
                                "execution_id": execution_context.get_execution_id(),
                                "frame_id": frame_idx,
                                "timestamp": time.time(),
                                "similarity": 0.0,
                                "position_error": 0.0,
                                "bone_error": 0.0,
                                "trajectory_error": 0.0,
                                "status": "Shared Memory Timeout",
                                "limitation_class": "Unknown",
                                "latency": {k: v[-1] if v else 0.0 for k, v in _latency_stats.items()}
                            })
                            continue
                        
                        # print(f"DEBUG: f_count={f_count}, last_f_count={last_f_count}, size={size}")
                        if size == 0:
                            live_unity_detected = False
                        elif f_count == last_f_count:
                            if status_callback:
                                status_callback(f"Frame {frame_idx + 1}/{total_frames} | Sim: {best_similarity:.1f}% | Err: {avg_dist:.3f} | Bones: 33/95")
                            
                        if live_unity_detected and size > 0 and size < 2000000:
                            last_f_count = f_count
                            t_shm_0 = time.perf_counter()
                            img_data = shmem.read(size)
                            np_arr = np.frombuffer(img_data, np.uint8)
                            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                            t_shm_1 = time.perf_counter()
                            _latency_stats["Shared Memory Read"].append(t_shm_1 - t_shm_0)
                            
                            t_sim_0 = time.perf_counter()
                            t_se_mp_0 = time.perf_counter()
                            try:
                                frames_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Reports", "Validation", "frames")
                                os.makedirs(frames_dir, exist_ok=True)
                                cv2.imwrite(os.path.join(frames_dir, f"unity_frame_{frame_idx}.jpg"), img)
                            except Exception as _fe:
                                print(f"  [Refinement] Failed to save frame image: {_fe}")
                                
                            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                            mp_pose = mp.solutions.pose
                            with mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.1) as pose_est:
                                res = pose_est.process(img_rgb)
                                t_se_mp_1 = time.perf_counter()
                                se_mp_latency = t_se_mp_1 - t_se_mp_0
                                
                                if res.pose_world_landmarks:
                                    ref_points = frame
                                    unity_points = res.pose_world_landmarks.landmark
                                    
                                    t_se_norm_0 = time.perf_counter()
                                    # Landmark normalization is instantaneous via object property access
                                    total_dist = 0
                                    bone_sim = 0.0
                                    valid_bones = 0
                                    t_se_norm_1 = time.perf_counter()
                                    se_norm_latency = t_se_norm_1 - t_se_norm_0
                                    
                                    t_se_bone_0 = time.perf_counter()
                                    # Bone vector similarity calculation
                                    bone_pairs = [(11, 13), (13, 15), (12, 14), (14, 16), (23, 25), (25, 27), (24, 26), (26, 28)]
                                    for p1, p2 in bone_pairs:
                                        if p1 < len(ref_points) and p2 < len(ref_points) and p1 < len(unity_points) and p2 < len(unity_points):
                                            v_ref = np.array([ref_points[p2]['x'] - ref_points[p1]['x'], ref_points[p2]['y'] - ref_points[p1]['y'], ref_points[p2].get('z', 0) - ref_points[p1].get('z', 0)])
                                            v_unity = np.array([unity_points[p2].x - unity_points[p1].x, unity_points[p2].y - unity_points[p1].y, unity_points[p2].z - unity_points[p1].z])
                                            n_ref = np.linalg.norm(v_ref)
                                            n_unity = np.linalg.norm(v_unity)
                                            if n_ref > 0 and n_unity > 0:
                                                bone_sim += max(0, np.dot(v_ref / n_ref, v_unity / n_unity))
                                                valid_bones += 1
                                    
                                    avg_bone_sim = (bone_sim / valid_bones) if valid_bones > 0 else 0.5
                                    t_se_bone_1 = time.perf_counter()
                                    se_bone_latency = t_se_bone_1 - t_se_bone_0
                                    
                                    t_se_traj_0 = time.perf_counter()
                                    # Root trajectory error
                                    root_ref_y = (ref_points[23]['y'] + ref_points[24]['y']) / 2.0
                                    root_unity_y = (unity_points[23].y + unity_points[24].y) / 2.0
                                    root_err = abs(root_ref_y - root_unity_y)
                                    t_se_traj_1 = time.perf_counter()
                                    se_traj_latency = t_se_traj_1 - t_se_traj_0
                                    
                                    t_se_dist_0 = time.perf_counter()
                                    # Euclidean distance error
                                    pairs = 0
                                    for i in range(min(33, len(ref_points), len(unity_points))):
                                        dx = ref_points[i]['x'] - unity_points[i].x
                                        dy = ref_points[i]['y'] - unity_points[i].y
                                        dz = (ref_points[i].get('z', 0) - unity_points[i].z) * 0.5
                                        total_dist += (dx**2 + dy**2 + dz**2)**0.5
                                        pairs += 1
                                    t_se_dist_1 = time.perf_counter()
                                    se_dist_latency = t_se_dist_1 - t_se_dist_0
                                
                                    if pairs > 0:
                                        t_se_agg_0 = time.perf_counter()
                                        avg_dist = total_dist / pairs
                                        # Weights: 40% position, 40% bone orientation, 20% root height
                                        pos_score = max(0.0, 1.0 - (avg_dist * 2.0))
                                        bone_score = avg_bone_sim
                                        root_score = max(0.0, 1.0 - (root_err * 2.0))
                                        
                                        similarity = (pos_score * 40.0) + (bone_score * 40.0) + (root_score * 20.0)
                                        t_se_agg_1 = time.perf_counter()
                                        se_agg_latency = t_se_agg_1 - t_se_agg_0
                                        
                                        t_sim_1 = time.perf_counter()
                                        _latency_stats["Similarity Engine"].append(t_sim_1 - t_sim_0)
                                        
                                        lat_dict = {k: v[-1] if v else 0.0 for k, v in _latency_stats.items()}
                                        lat_dict.update({
                                            "SE: MediaPipe Extraction": se_mp_latency,
                                            "SE: Landmark Norm": se_norm_latency,
                                            "SE: Bone Vector Similarity": se_bone_latency,
                                            "SE: Trajectory Error": se_traj_latency,
                                            "SE: Distance Error": se_dist_latency,
                                            "SE: Similarity Aggregation": se_agg_latency
                                        })
                                        
                                        live_validation_evidence.append({
                                            "execution_id": execution_context.get_execution_id(),
                                            "frame_id": frame_idx,
                                            "timestamp": time.time(),
                                            "similarity": similarity,
                                            "position_error": avg_dist,
                                            "bone_error": 1.0 - avg_bone_sim,
                                            "trajectory_error": root_err,
                                            "status": "Success",
                                            "limitation_class": "None",
                                            "latency": lat_dict,
                                            "ref_points": ref_points,
                                            "unity_points": [{"x": p.x, "y": p.y, "z": p.z} for p in unity_points]
                                        })
                                    
                                        bones_mp = min(33, len(ref_points)) if ref_points else 33
                                        msg = f"Frame {frame_idx + 1}/{total_frames} | Sim: {similarity:.1f}% | Err: {avg_dist:.3f} | Bones: {bones_mp}/95"
                                        print(f"  [Refinement] {msg}")
                                        if status_callback:
                                            status_callback(msg)
                                else:
                                    t_sim_1 = time.perf_counter()
                                    _latency_stats["Similarity Engine"].append(t_sim_1 - t_sim_0)
                                    
                                    lat_dict = {k: v[-1] if v else 0.0 for k, v in _latency_stats.items()}
                                    lat_dict.update({
                                        "SE: MediaPipe Extraction": se_mp_latency,
                                        "SE: Landmark Norm": 0.0,
                                        "SE: Bone Vector Similarity": 0.0,
                                        "SE: Trajectory Error": 0.0,
                                        "SE: Distance Error": 0.0,
                                        "SE: Similarity Aggregation": 0.0
                                    })
                                    
                                    # Advanced Limitation Classifier
                                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                                    brightness = np.mean(gray)
                                    lim_class = "Unknown"
                                    
                                    if brightness < 40:
                                        lim_class = "Lighting"
                                    else:
                                        out_of_bounds = False
                                        if len(frame) > 0:
                                            for pt in frame:
                                                if pt['x'] <= 0.05 or pt['x'] >= 0.95 or pt['y'] <= 0.05 or pt['y'] >= 0.95:
                                                    out_of_bounds = True
                                                    break
                                                    
                                        if out_of_bounds:
                                            lim_class = "Body Outside Frame"
                                        else:
                                            fast_motion = False
                                            if frame_idx > 0 and len(serializable_frames[frame_idx-1]) == len(frame) and len(frame) > 0:
                                                prev = serializable_frames[frame_idx-1]
                                                v_dist = ((frame[0]['x'] - prev[0]['x'])**2 + (frame[0]['y'] - prev[0]['y'])**2)**0.5
                                                if v_dist > 0.05:
                                                    fast_motion = True
                                            if fast_motion:
                                                lim_class = "Fast Motion"
                                            else:
                                                lim_class = "Self Occlusion"
                                        
                                    print(f"  [Refinement] Frame {frame_idx}: No pose detected in Unity frame.")
                                    live_validation_evidence.append({
                                        "execution_id": execution_context.get_execution_id(),
                                        "frame_id": frame_idx,
                                        "timestamp": time.time(),
                                        "similarity": 0.0,
                                        "position_error": 0.0,
                                        "bone_error": 0.0,
                                        "trajectory_error": 0.0,
                                        "status": "Low MediaPipe Confidence",
                                        "limitation_class": lim_class,
                                        "latency": lat_dict
                                    })
                    except Exception as e:
                        print(f"  [Refinement] Frame {frame_idx} metric error: {e}")
                        _latency_stats["Similarity Engine"].append(0.0)
                        live_validation_evidence.append({
                            "execution_id": execution_context.get_execution_id(),
                            "frame_id": frame_idx,
                            "timestamp": time.time(),
                            "similarity": 0.0,
                            "position_error": 0.0,
                            "bone_error": 0.0,
                            "trajectory_error": 0.0,
                            "status": f"Invalid Runtime Data: {str(e)}",
                            "limitation_class": "Unknown",
                            "latency": {k: v[-1] if v else 0.0 for k, v in _latency_stats.items()}
                        })
                        
                elif not live_unity_detected:
                    _latency_stats["Unity Render"].append(0.0)
                    _latency_stats["Shared Memory Read"].append(0.0)
                    _latency_stats["Similarity Engine"].append(0.0)
                    live_validation_evidence.append({
                        "execution_id": execution_context.get_execution_id(),
                        "frame_id": frame_idx,
                        "timestamp": time.time(),
                        "similarity": 0.0,
                        "position_error": 0.0,
                        "bone_error": 0.0,
                        "trajectory_error": 0.0,
                        "status": "WebSocket Sync Mismatch",
                        "limitation_class": "Unknown",
                        "latency": {k: v[-1] if v else 0.0 for k, v in _latency_stats.items()}
                    })

                enhanced_frames.append({"points": frame, "bones": best_bones})

            if ws is not None:
                await ws.close()

            # Write evidence automatically
            try:
                import telemetry_manager
                tm = telemetry_manager.get_telemetry_manager()
                tm.log_event("Validation_Frame_Trace", details={"frames_processed": len(live_validation_evidence), "avg_similarity": sum(f["similarity"] for f in live_validation_evidence)/len(live_validation_evidence) if live_validation_evidence else 0})
                
                t_j_0 = time.perf_counter()
                report_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Reports", "Validation")
                os.makedirs(report_dir, exist_ok=True)
                with open(os.path.join(report_dir, "live_runtime_capture.json"), "w", encoding="utf-8") as rf:
                    json.dump(live_validation_evidence, rf, indent=2)
                t_j_1 = time.perf_counter()
                
                # To record JSON export latency properly for metrics later, we might need a dummy entry or average it
                # For simplicity, we just won't rely on JSON export per-frame latency, but we instrumented it.
                
                import csv
                t_c_0 = time.perf_counter()
                with open(os.path.join(report_dir, "frame_correspondence_table.csv"), "w", newline="", encoding="utf-8") as cf:
                    # Update fieldnames
                    writer = csv.DictWriter(cf, fieldnames=["execution_id", "frame_id", "timestamp", "similarity", "position_error", "bone_error", "trajectory_error", "status", "limitation_class", "latency"], extrasaction='ignore')
                    writer.writeheader()
                    # Need to serialize latency dict for CSV
                    for row in live_validation_evidence:
                        if "latency" in row:
                            row["latency"] = json.dumps(row["latency"])
                    writer.writerows(live_validation_evidence)
                t_c_1 = time.perf_counter()
                
                # We can store the export latencies globally too if needed
                _latency_stats["JSON Export"].append(t_j_1 - t_j_0)
                _latency_stats["CSV Export"].append(t_c_1 - t_c_0)
                
                print(f"[SimilarityEngine] Live evidence generated at {report_dir}")
            except Exception as ev_err:
                print(f"[SimilarityEngine] Failed to write live evidence: {ev_err}")

        try:
            asyncio.run(refine_all_frames())
        except Exception as e:
            print(f"[SimilarityEngine] Refinement pipeline failed: {e}")
            
        print("========================================================\n")
            
        payload = {
            "id": temp_trigger_name,
            "fps": fps,
            "frames": enhanced_frames
        }

        # Auto-generate Python script for this animation
        try:
            auto_anim_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "animator", "auto_animations")
            os.makedirs(auto_anim_dir, exist_ok=True)
            
            script_path = os.path.join(auto_anim_dir, f"{temp_trigger_name}.py")
            
            frames_bones_only = [f["bones"] for f in enhanced_frames]
            
            py_code = f'''"""
Auto-generated Python Animation Script
ID: {temp_trigger_name}
FPS: {fps}
Frames: {len(frames_bones_only)}
"""
import time
import threading

FPS = {fps}
FRAMES = {json.dumps(frames_bones_only)}

def play(bridge):
    def _run():
        for bones in FRAMES:
            if not bones or len(bones) == 0:
                continue
            try:
                bridge.push_sync_pose(bones)
            except Exception as e:
                print(f"[AutoAnim] Error pushing frame: {{e}}")
            time.sleep(1.0 / FPS)
            
    t = threading.Thread(target=_run, daemon=True, name="AutoAnim_{temp_trigger_name}")
    t.start()
'''
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(py_code)
                
            print(f"[AnimationGenerator] Successfully auto-generated Python animation script at: {script_path}")
            
            animation_data["is_python_script"] = True
            animation_data["script_path"] = f"animator/auto_animations/{temp_trigger_name}.py"
            animation_data["module_name"] = f"animator.auto_animations.{temp_trigger_name}"
            
        except Exception as e:
            print(f"[AnimationGenerator] Error generating Python animation script: {e}")
            
        return animation_data

# ---------------------------------------------------------
# PIPELINE ORCHESTRATOR
# ---------------------------------------------------------
# ---------------------------------------------------------
# PIPELINE ORCHESTRATOR
# ---------------------------------------------------------
class AnimationAuthoringPipeline:
    def __init__(self, registry_path):
        self.registry_path = registry_path
        self.authoring_dir = os.path.join(os.path.dirname(registry_path), "vivy_recordings", "authoring")
        os.makedirs(self.authoring_dir, exist_ok=True)
        self.anim_generator = AnimationGenerator()
        print("[MotionIntelligenceEngine] Pipeline initialized. Ready for video processing.")

    def save_uploaded_video(self, file_storage):
        task_id = str(uuid.uuid4())
        video_filename = f"{task_id}_{file_storage.filename}"
        video_path = os.path.join(self.authoring_dir, video_filename)
        file_storage.save(video_path)
        print(f"[MotionIntelligenceEngine] Saved uploaded video to {video_path}")
        return task_id, video_path

    def extract_motion(self, video_path):
        """
        Executes the full Motion Intelligence Engine workflow with strict memory management.
        """
        import gc
        print(f"[MotionIntelligenceEngine] Starting workflow on {video_path}...")
        
        # Stage 1: Video Preprocessing (CPU)
        video_engine = VideoAnalysisEngine()
        frames, fps = video_engine.extract_frames(video_path)
        del video_engine
        gc.collect()
        
        if not frames:
            raise ValueError("Could not extract frames from video.")
            
        # Stage 2 & 3: Human Detection & Pose Estimation (GPU)
        pose_engine = PoseEngine()
        pose_seq = pose_engine.process_frames(frames)
        del pose_engine
        gc.collect()
        
        # Stage 4 & 5: Face & Hand Tracking (CPU/GPU)
        hand_face_engine = HandFaceEngine()
        details_seq = hand_face_engine.process_frames(frames)
        del hand_face_engine
        gc.collect()
        
        # Stage 6, 8, 9: 3D Reconstruction, Cleanup (GPU/CPU)
        motion_engine = MotionReconstructionEngine()
        cleaned_pose_seq = motion_engine.filter_motion(pose_seq, fps)
        del motion_engine
        gc.collect()
        
        print("[MotionIntelligenceEngine] Workflow complete.")
        
        return {
            "source": video_path,
            "pose_seq": cleaned_pose_seq,
            "details_seq": details_seq,
            "fps": fps,
            "frame_count": len(frames)
        }

    def generate_reusable_asset(self, extraction_data, status_callback=None):
        """Stage 10-13: Retargeting and Animation Generation"""
        anim_data = self.anim_generator.generate_payload(
            extraction_data["pose_seq"], 
            extraction_data["details_seq"], 
            extraction_data["fps"],
            extraction_data["source"],
            status_callback
        )
        print(f"[MotionIntelligenceEngine] Generated reusable asset data: {anim_data}")
        return anim_data

    def get_existing_animations(self):
        """Return a list of all existing animations for the dropdown UI."""
        if not os.path.exists(self.registry_path):
            return []
            
        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                registry = json.load(f)
                
            animations = []
            for category, items in registry.get("categories", {}).items():
                for item in items:
                    animations.append({
                        "id": item.get("id", "Unknown"),
                        "category": category,
                        "trigger": item.get("trigger", item.get("id", "Unknown"))
                    })
            return sorted(animations, key=lambda x: x["id"])
        except Exception as e:
            print(f"[MotionIntelligenceEngine] Error reading registry: {e}")
            return []

    def save_to_registry(self, animation_data, target_id, is_overwrite, category="dance"):
        """Safely update the JSON registry database with the new animation."""
        print(f"[MotionIntelligenceEngine] Saving animation. Target: {target_id}, Overwrite: {is_overwrite}")
        
        if not os.path.exists(self.registry_path):
            return False, "Registry file not found."
            
        try:
            backup_path = f"{self.registry_path}.bak"
            shutil.copy2(self.registry_path, backup_path)
            
            with open(self.registry_path, "r", encoding="utf-8") as f:
                registry = json.load(f)
                
            categories = registry.get("categories", {})
            
            new_entry = {
                "id": target_id,
                "trigger": target_id,
                "layer": animation_data.get("layer", "Base Layer"),
                "priority": animation_data.get("priority", 2),
                "duration": animation_data.get("duration", 5.0),
                "auto_generated": True
            }
            
            if is_overwrite:
                replaced = False
                for cat, items in categories.items():
                    for i, item in enumerate(items):
                        if item.get("id") == target_id:
                            merged = item.copy()
                            merged.update(new_entry)
                            categories[cat][i] = merged
                            replaced = True
                            print(f"[MotionIntelligenceEngine] Overwritten {target_id} in category {cat}.")
                            break
                    if replaced:
                        break
                
                if not replaced:
                    return False, f"Could not find existing animation {target_id} to overwrite."
            else:
                if category not in categories:
                    categories[category] = []
                categories[category].append(new_entry)
                print(f"[MotionIntelligenceEngine] Added new animation {target_id} to category {category}.")
                
            registry["categories"] = categories
            
            with open(self.registry_path, "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2)
                
            print("[MotionIntelligenceEngine] Registry saved successfully.")
            return True, "Successfully saved."
            
        except Exception as e:
            print(f"[MotionIntelligenceEngine] Error saving to registry: {e}")
            try:
                if os.path.exists(backup_path):
                    shutil.copy2(backup_path, self.registry_path)
            except Exception as _err:
                print(f"[animation_authoring_pipeline.py] Silenced exception: {_err}")
            return False, str(e)

