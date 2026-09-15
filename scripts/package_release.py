#!/usr/bin/env python3
"""
Vivy-AI — Production Distribution & Release Packaging Utility
Non-destructive packaging of deployable source archives, edge node components,
and deployment manifests for GitHub Actions CI/CD and release distribution.
"""

import os
import sys
import json
import zipfile
import hashlib
import fnmatch
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

EXCLUDE_PATTERNS = [
    # Git & IDEs
    ".git*",
    ".vscode*",
    ".idea*",
    ".gradle*",
    ".plastic*",
    "Thumbs.db",
    ".DS_Store",
    
    # Virtual Environments & Build Caches
    "venv*",
    "__pycache__*",
    "*.py[cod]",
    "*.class",
    ".pytest_cache*",
    "build*",
    "dist*",
    
    # AI Model Weights & Heavy Checkpoints (>100MB / binary weights)
    "*.gguf",
    "*.bin",
    "*.pt",
    "*.pth",
    "*.onnx",
    "*.safetensors",
    "*.ckpt",
    "*.index",
    "*.npy",
    "*.npz",
    "*.pkl",
    "*.pickle",
    "*.h5",
    "*.tfevents*",
    "models/nlp/*-ct2*",
    "model_cache*",
    
    # Private User Memory & Runtime State
    "vivy_memory*.json",
    "relationship_state*.json",
    "vivy_history*.json",
    "vivy_knowledge_graph*.json",
    "vivy_world_model*.json",
    "vivy_learning_schedule*.json",
    "vivy_skill_memory*.json",
    "data/neural_experiences.json",
    ".agent_progress*",
    "*.override.json",
    
    # Secrets & Credentials
    ".env*",
    "*.secret*",
    "*credentials*.json",
    "*token*.json",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "local.properties",
    
    # Volatile Runtime Buffers, Logs & Temporary Audio
    "*.log",
    "*.tmp",
    "*.lock",
    "*.flag",
    "*.bak",
    "crash_log*.txt",
    "train_crash*.txt",
    "recordings*",
    "vivy_recordings*",
    "transcripts*",
    "Reports*",
    "scratch*",
    "shared*",
    "static/avatar_frame.jpg",
    "static/audio*",
    "test_*.wav",
    "test.wav",
    "test_*.jpg",
    "test_*.png",
    "test_*.mp4",
    "test_out.*",
    "gesture_list.txt",
    "mock_unity.py",
    "mock_unity*.log",
    "unity_direct_start.log",
    
    # Mate-Engine Unity Project (Optional separate package due to >6GB asset size)
    "Mate-Engine*",
    
    # RVC logs and heavy training assets
    "rvc_cpu/logs*",
    "rvc_cpu/assets/weights*",
    "rvc_cpu/assets/indices*",
    "Retrieval-based-Voice-Conversion-WebUI-main/logs*",
    "Retrieval-based-Voice-Conversion-WebUI-main/assets/weights*",
    "Retrieval-based-Voice-Conversion-WebUI-main/assets/indices*",
]

def should_exclude(rel_path: str) -> bool:
    norm_path = rel_path.replace("\\", "/")
    parts = norm_path.split("/")
    
    for pattern in EXCLUDE_PATTERNS:
        # Match full relative path or filename or path parts
        if fnmatch.fnmatch(norm_path, pattern):
            return True
        for part in parts:
            if fnmatch.fnmatch(part, pattern):
                return True
        if fnmatch.fnmatch(parts[-1], pattern):
            return True
            
    return False

def calculate_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def get_git_commit() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"

def package_core(output_zip: Path, dry_run: bool = False) -> int:
    file_count = 0
    total_bytes = 0
    
    print(f"\n[Packaging] Building Vivy Core distribution: {output_zip.name}")
    
    if not dry_run:
        output_zip.parent.mkdir(parents=True, exist_ok=True)
        zip_file = zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6)
    else:
        zip_file = None

    try:
        for root, dirs, files in os.walk(BASE_DIR):
            rel_dir = os.path.relpath(root, BASE_DIR)
            if rel_dir != "." and should_exclude(rel_dir):
                dirs[:] = []
                continue
                
            for file in files:
                full_path = Path(root) / file
                rel_path = os.path.relpath(full_path, BASE_DIR).replace("\\", "/")
                
                if should_exclude(rel_path):
                    continue
                    
                file_count += 1
                size = full_path.stat().st_size
                total_bytes += size
                
                if not dry_run:
                    zip_file.write(full_path, rel_path)
    finally:
        if zip_file:
            zip_file.close()

    mb = total_bytes / (1024 * 1024)
    print(f"  -> Total files included: {file_count} ({mb:.2f} MB uncompressed)")
    return file_count

def package_windows_node(output_zip: Path, dry_run: bool = False) -> int:
    node_dir = BASE_DIR / "vivy_windows_node"
    if not node_dir.exists():
        print(f"[Warning] vivy_windows_node directory not found at {node_dir}")
        return 0

    print(f"\n[Packaging] Building Vivy Windows Node distribution: {output_zip.name}")
    file_count = 0
    total_bytes = 0

    if not dry_run:
        output_zip.parent.mkdir(parents=True, exist_ok=True)
        zip_file = zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6)
    else:
        zip_file = None

    try:
        for root, dirs, files in os.walk(node_dir):
            for file in files:
                full_path = Path(root) / file
                rel_path = os.path.relpath(full_path, BASE_DIR).replace("\\", "/")
                
                if should_exclude(rel_path):
                    continue
                    
                file_count += 1
                size = full_path.stat().st_size
                total_bytes += size
                
                if not dry_run:
                    # In node zip, store relative to vivy_windows_node
                    archive_path = os.path.relpath(full_path, node_dir).replace("\\", "/")
                    zip_file.write(full_path, archive_path)
                    
        # Add launcher script
        launcher_content = (
            "@echo off\r\n"
            "echo ========================================\r\n"
            "echo Starting Vivy Windows Edge Node...\r\n"
            "echo ========================================\r\n"
            "python -m pip install -r requirements_node.txt\r\n"
            "python node_agent.py\r\n"
            "pause\r\n"
        )
        if not dry_run:
            zip_file.writestr("start_windows_node.bat", launcher_content)
            file_count += 1
    finally:
        if zip_file:
            zip_file.close()

    mb = total_bytes / (1024 * 1024)
    print(f"  -> Total files included: {file_count} ({mb:.2f} MB uncompressed)")
    return file_count

def create_manifest(output_dir: Path, artifacts: dict) -> Path:
    manifest_path = output_dir / "deployment-manifest.json"
    commit_sha = get_git_commit()
    timestamp = datetime.now(timezone.utc).isoformat()
    
    manifest = {
        "project": "Vivy AI",
        "version": "2.0.0",
        "commit_sha": commit_sha,
        "built_at_utc": timestamp,
        "deployment_type": "Local-first AI runtime with GitHub automated build & distribution",
        "artifacts": artifacts,
        "prerequisites": {
            "os": "Windows 10 / 11 (64-bit)",
            "python": "Python 3.10+",
            "ram": "16 GB minimum (32 GB recommended)",
            "hardware": "NVIDIA GPU with CUDA support recommended for LLM/RVC acceleration",
            "peripherals": "Microphone, Speakers/Headphones, Webcam (optional for vision)",
            "avatar_engine": "Unity MateEngine (optional for 3D live avatar)"
        },
        "model_requirements": {
            "llm": {
                "file": "models/Qwen3-8B-Q4_K_M.gguf",
                "description": "Primary local reasoning engine (place under models/)"
            },
            "stt": {
                "file": "models/ggml-small.bin",
                "description": "Whisper.cpp speech-to-text model"
            },
            "rvc": {
                "file": "rvc_cpu/assets/weights/vivy_voice.pth",
                "description": "Retrieval-based Voice Conversion voice model"
            }
        },
        "installation_guide": [
            "1. Extract vivy-core-distribution.zip to desired working directory (e.g., C:\\Vivy)",
            "2. Create virtual environment: python -m venv venv",
            "3. Activate environment: .\\venv\\Scripts\\activate",
            "4. Download required models and place them in the models/ and rvc_cpu/ directories",
            "5. Launch Vivy runtime: python run_vivy.py",
            "6. Access local dashboard: http://127.0.0.1:8080"
        ]
    }
    
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        
    print(f"\n[Manifest] Generated deployment manifest: {manifest_path.name}")
    return manifest_path

def main():
    parser = argparse.ArgumentParser(description="Vivy-AI Release Packager")
    parser.add_argument("--output-dir", default=str(BASE_DIR / "dist"), help="Output directory for archives")
    parser.add_argument("--dry-run", action="store_true", help="Audit files without writing zip files")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    print("==================================================")
    print("VIVY-AI RELEASE PACKAGING PIPELINE")
    print(f"Base Directory : {BASE_DIR}")
    print(f"Output Directory: {out_dir}")
    print(f"Dry Run Mode    : {args.dry_run}")
    print("==================================================")

    core_zip = out_dir / "vivy-core-distribution.zip"
    node_zip = out_dir / "vivy-windows-node.zip"

    package_core(core_zip, dry_run=args.dry_run)
    package_windows_node(node_zip, dry_run=args.dry_run)

    if not args.dry_run:
        artifacts = {
            "vivy-core-distribution.zip": {
                "size_bytes": core_zip.stat().st_size,
                "sha256": calculate_sha256(core_zip)
            },
            "vivy-windows-node.zip": {
                "size_bytes": node_zip.stat().st_size,
                "sha256": calculate_sha256(node_zip)
            }
        }
        create_manifest(out_dir, artifacts)
        print("\n[SUCCESS] Release packaging completed cleanly.")
    else:
        print("\n[SUCCESS] Dry-run completed. No files written.")

if __name__ == "__main__":
    main()
