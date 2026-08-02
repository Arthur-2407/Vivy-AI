import os
import sys
import base64
from io import BytesIO
from PIL import Image

# Ensure the root project directory is in the path
BASE_DIR = r"d:\Vivy"
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import perception.screen_pipeline as sp

def main():
    img = Image.new("RGB", (1280, 720), (30, 30, 40))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    try:
        # Call analyze_frame directly to bypass process_frame_bytes' try-except
        res = sp.analyze_frame(img)
        print("Success! Result:", res)
    except Exception as e:
        import traceback
        print("ERROR caught in analyze_frame:")
        traceback.print_exc()

if __name__ == "__main__":
    main()
