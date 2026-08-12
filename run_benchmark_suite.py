import os
import sys
import shutil
import subprocess

def main():
    print("Starting RC1 Validation Suite (5 Runs)...")
    json_path = r"d:\Vivy\Reports\Validation\live_runtime_capture.json"
    dest_dir = r"d:\Vivy\Reports\Validation\suite"
    os.makedirs(dest_dir, exist_ok=True)
    
    for i in range(1, 6):
        print(f"\n=== Executing Benchmark Run {i}/5 ===")
        subprocess.run([sys.executable, "scratch_run_pipeline.py"], check=True)
        
        if os.path.exists(json_path):
            new_path = os.path.join(dest_dir, f"run_{i}_capture.json")
            shutil.copy2(json_path, new_path)
            print(f"Preserved telemetry as: {new_path}")
        else:
            print(f"ERROR: No telemetry found for Run {i}!")
            
    print("\nSuite completed successfully.")

if __name__ == "__main__":
    main()
