import numpy as np
import random
import sys

class Landmark:
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z

def compute_similarity(ref_points, unity_points):
    total_dist = 0
    bone_sim = 0.0
    valid_bones = 0
    
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
    
    root_ref_y = (ref_points[23]['y'] + ref_points[24]['y']) / 2.0 if len(ref_points) > 24 else 0
    root_unity_y = (unity_points[23].y + unity_points[24].y) / 2.0 if len(unity_points) > 24 else 0
    root_err = abs(root_ref_y - root_unity_y)
    
    pairs = 0
    for i in range(min(33, len(ref_points), len(unity_points))):
        dx = ref_points[i]['x'] - unity_points[i].x
        dy = ref_points[i]['y'] - unity_points[i].y
        dz = (ref_points[i].get('z', 0) - unity_points[i].z) * 0.5
        total_dist += (dx**2 + dy**2 + dz**2)**0.5
        pairs += 1
        
    if pairs > 0:
        avg_dist = total_dist / pairs
        pos_score = max(0.0, 1.0 - (avg_dist * 2.0))
        bone_score = avg_bone_sim
        root_score = max(0.0, 1.0 - (root_err * 2.0))
        
        similarity = (pos_score * 40.0) + (bone_score * 40.0) + (root_score * 20.0)
        return similarity, avg_dist, avg_bone_sim, root_err
    return 0.0, 0.0, 0.0, 0.0

def generate_base_pose():
    # Generate 33 landmarks for a basic human T-Pose
    pose = []
    for i in range(33):
        # Rough T-pose approximations
        x, y, z = 0, 0, 0
        if i == 23 or i == 24: y = 0.5 # Hips
        if i == 11 or i == 12: y = 0.1 # Shoulders
        if i == 13: x, y = -0.3, 0.1 # L Elbow
        if i == 15: x, y = -0.6, 0.1 # L Hand
        if i == 14: x, y = 0.3, 0.1 # R Elbow
        if i == 16: x, y = 0.6, 0.1 # R Hand
        pose.append({'x': x, 'y': y, 'z': z})
    return pose

def run_tests():
    print("# VIVY AI - SIMILARITY CALIBRATION (STRICT VALIDATOR MODE)\n")
    
    base_ref = generate_base_pose()
    
    # Test A: Perfect Match
    unity_A = [Landmark(p['x'], p['y'], p['z']) for p in base_ref]
    simA, distA, boneA, rootA = compute_similarity(base_ref, unity_A)
    print("## Test A: Reference vs Identical Match")
    print(f"Similarity: {simA:.2f}% | Avg Dist: {distA:.4f} | Bone Alignment: {boneA:.4f}\n")
    
    # Test B: Minor Noise (Expected 90-95%)
    unity_B = []
    for p in base_ref:
        unity_B.append(Landmark(p['x'] + random.uniform(-0.02, 0.02), p['y'] + random.uniform(-0.02, 0.02), p['z']))
    simB, distB, boneB, rootB = compute_similarity(base_ref, unity_B)
    print("## Test B: Reference vs Minor Noise (+/- 2cm)")
    print(f"Similarity: {simB:.2f}% | Avg Dist: {distB:.4f} | Bone Alignment: {boneB:.4f}\n")
    
    # Test C: Offset Height (Tests root error)
    unity_C = [Landmark(p['x'], p['y'] - 0.2, p['z']) for p in base_ref]
    simC, distC, boneC, rootC = compute_similarity(base_ref, unity_C)
    print("## Test C: Reference vs Height Offset (-20cm)")
    print(f"Similarity: {simC:.2f}% | Avg Dist: {distC:.4f} | Bone Alignment: {boneC:.4f}\n")

    # Test D: Complete Random Noise
    unity_D = [Landmark(random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(-1, 1)) for _ in range(33)]
    simD, distD, boneD, rootD = compute_similarity(base_ref, unity_D)
    print("## Test D: Reference vs Complete Random Noise")
    print(f"Similarity: {simD:.2f}% | Avg Dist: {distD:.4f} | Bone Alignment: {boneD:.4f}\n")
    
    # Test E: Mirrored Left/Right
    unity_E = [Landmark(-p['x'], p['y'], p['z']) for p in base_ref]
    simE, distE, boneE, rootE = compute_similarity(base_ref, unity_E)
    print("## Test E: Reference vs Mirrored Pose")
    print(f"Similarity: {simE:.2f}% | Avg Dist: {distE:.4f} | Bone Alignment: {boneE:.4f}\n")

if __name__ == "__main__":
    run_tests()
