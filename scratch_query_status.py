import subprocess
import time
import requests
import sys

def main():
    # Spawn the simulated unity client in background using venv_avatar python
    print("Launching simulated Unity client...")
    unity_proc = subprocess.Popen(
        [r"d:\Vivy\venv_avatar\Scripts\python.exe", "scratch_test_ws.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait 3 seconds for connection to establish
    time.sleep(3)
    
    # Query Flask API status
    try:
        r = requests.get("http://127.0.0.1:8080/api/avatar/status", timeout=2)
        print(f"Status Code: {r.status_code}")
        print(f"Response: {r.json()}")
        
        r_frame = requests.get("http://127.0.0.1:8080/api/avatar/frame", timeout=2)
        print(f"Frame Route Status Code: {r_frame.status_code}")
        print(f"Frame Route Response Data Length: {len(r_frame.content)} bytes")
    except Exception as e:
        print(f"Error querying Flask: {e}")
        
    # Wait for unity proc to finish
    stdout, stderr = unity_proc.communicate()
    print("Unity simulator output:")
    print(stdout)
    if stderr:
        print("Unity simulator errors:")
        print(stderr)

if __name__ == "__main__":
    main()
