import json
import os
import sys
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

def main():
    print("Executing Clean-Process Layered Verification Matrix...")
    modes = ["normal", "no_network", "no_camera"]
    results = {}
    
    # Clean process execution
    runner_script = os.path.join(BASE_DIR, "verification_engine", "degraded_mode_runner.py")
    for mode in modes:
        print(f"Running mode: {mode} (Clean Process)...")
        res = subprocess.run([sys.executable, runner_script, "--mode", mode], cwd=PROJECT_ROOT, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"Failed to run mode {mode}:")
            print(res.stderr)
            sys.exit(1)
        try:
            results[mode] = json.loads(res.stdout)
        except json.JSONDecodeError:
            print(f"Failed to parse JSON for mode {mode}. Raw output:")
            print(res.stdout)
            sys.exit(1)
            
    out_dir = os.path.join(BASE_DIR, "output")
    os.makedirs(out_dir, exist_ok=True)
    out_matrix = os.path.join(out_dir, "architecture_matrix.json")
    with open(out_matrix, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print("Running Regression Gate (pytest)...")
    regression_pass = False
    try:
        res = subprocess.run([sys.executable, "-m", "pytest", "tests/test_pipeline_streaming.py", "-v"], cwd=PROJECT_ROOT, capture_output=True, text=True)
        if res.returncode == 0:
            regression_pass = True
            print("Regression Gate: PASS")
        else:
            print("Regression Gate: FAIL")
            print(res.stdout)
    except Exception as e:
        print(f"Regression Gate Exception: {e}")
        
    print("Running Certification Engine...")
    cert_engine = os.path.join(BASE_DIR, "verification_engine", "certification_engine.py")
    res = subprocess.run([sys.executable, cert_engine, out_matrix, str(regression_pass)], cwd=PROJECT_ROOT, capture_output=True, text=True)
    print(res.stdout)
    if res.returncode != 0:
        sys.exit(1)
        
if __name__ == "__main__":
    main()
