import os
import sys
import time
from PIL import Image

BASE_DIR = r"d:\Vivy"
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import perception.screen_pipeline as sp

def main():
    img_path = os.path.join(BASE_DIR, "static", "avatar_default.png")
    if not os.path.exists(img_path):
        print(f"Image not found at {img_path}")
        return
        
    img = Image.open(img_path)
    print("Loaded image of size:", img.size)
    
    # We call analyze_frame in a loop or once
    # Note that OCR runs asynchronously, so we may need to wait for it to finish
    try:
        print("Calling analyze_frame...")
        res = sp.analyze_frame(img)
        print("First call result:")
        print("App type:", res.get("app_type"))
        print("OCR Text (len):", len(res.get("ocr_text", "")))
        
        # Wait a bit for the async OCR to finish
        print("Waiting for async OCR to complete...")
        for _ in range(20):
            time.sleep(0.5)
            if not sp.is_ocr_in_progress():
                break
        
        print("Second call to analyze_frame (should have cached OCR)...")
        res2 = sp.analyze_frame(img)
        print("App type:", res2.get("app_type"))
        print("OCR Text (len):", len(res2.get("ocr_text", "")))
        print("Success!")
    except Exception as e:
        import traceback
        print("ERROR caught:")
        traceback.print_exc()

if __name__ == "__main__":
    main()
