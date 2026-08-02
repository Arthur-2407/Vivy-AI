import sys
import os

base_dir = r"d:\Vivy"
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import execution_context
execution_context.reset_execution_id()

from animation_authoring_pipeline import AnimationAuthoringPipeline

def main():
    video_path = r"d:\Vivy\demo\Furina Chop Chop Var! ð__³.mp4"
    registry = r"d:\Vivy\vivy_animation_registry.json"
    
    print("Starting pipeline extraction...")
    pipeline = AnimationAuthoringPipeline(registry_path=registry)
    data = pipeline.extract_motion(video_path)
    print("Starting asset generation...")
    pipeline.generate_reusable_asset(data)
    print("Pipeline extraction and asset generation complete.")

if __name__ == "__main__":
    main()
