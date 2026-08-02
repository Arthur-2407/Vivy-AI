import time
import sys
from avatar_bridge import start_server_thread, push_animation, is_connected

def main():
    print("Starting server thread...")
    start_server_thread()
    
    print("Waiting for Unity to connect...")
    retries = 5
    while not is_connected() and retries > 0:
        time.sleep(1)
        retries -= 1
        
    if not is_connected():
        print("[FAIL] Unity did not connect. Cannot perform runtime validation.")
        sys.exit(1)
        
    print("[SUCCESS] Connected. Sending 'Idle0'...")
    push_animation("Idle0")
    time.sleep(1)
    
    print("[SUCCESS] Sending 'Sleeping'...")
    push_animation("Sleeping")
    time.sleep(1)
    
    print("[SUCCESS] Sending 'Dance0'...")
    push_animation("Dance0")
    time.sleep(1)
    
    print("[DONE] Transmission successful.")
    sys.exit(0)

if __name__ == "__main__":
    main()
