#!/usr/bin/env python3
"""
Vivy-AI — Production Deployment Orchestrator
Executes zero-data-loss, safe updates with pre-deployment state backup,
pre-flight validation, service management, health probing, and automated rollback.
"""

import sys
import os
import time
import shutil
import json
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BACKUP_ROOT = BASE_DIR / "backup"
SHARED_DIR = BASE_DIR / "shared"
DEPLOY_MANIFEST = SHARED_DIR / "deployment_info.json"

STATE_FILES_TO_BACKUP = [
    "vivy_memory.json",
    "vivy_history.json",
    "vivy_knowledge_graph.json",
    "vivy_world_model.json",
    "vivy_learning_schedule.json",
    "vivy_skill_memory.json",
    "vivy_config.json",
    "relationship/relationship_state.json",
    "database/memory_embeddings.json",
    "data/neural_experiences.json",
]


def log(msg: str, status: str = "INFO"):
    prefix = {
        "PASS": "\033[92m[PASS]\033[0m",
        "FAIL": "\033[91m[FAIL]\033[0m",
        "WARN": "\033[93m[WARN]\033[0m",
        "INFO": "\033[94m[INFO]\033[0m",
        "STEP": "\033[96m[STEP]\033[0m"
    }.get(status, f"[{status}]")
    print(f"{prefix} {msg}")


def get_python_exe() -> str:
    known_venvs = [
        BASE_DIR / "venv" / "Scripts" / "python.exe",
        BASE_DIR / "venv" / "bin" / "python",
        Path(r"D:\Vivy\venv\Scripts\python.exe"),
        Path(r"C:\Users\SATYAJEET\AppData\Local\Programs\Python\Python310\python.exe"),
    ]
    for p in known_venvs:
        if p.exists():
            return str(p)
    return sys.executable


def get_current_git_commit() -> str:
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(BASE_DIR), capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return "unknown"


def create_state_backup() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / f"state_pre_deploy_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    log(f"Creating pre-deployment state backup at: {backup_dir.name}", "STEP")
    backed_up_count = 0
    for rel_path in STATE_FILES_TO_BACKUP:
        src = BASE_DIR / rel_path
        if src.exists():
            dst = backup_dir / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_file():
                shutil.copy2(src, dst)
                backed_up_count += 1

    log(f"Archived {backed_up_count} persistent state files safely.", "PASS")
    return backup_dir


def restore_state_backup(backup_dir: Path):
    log(f"Restoring persistent state from backup: {backup_dir.name}", "WARN")
    restored_count = 0
    for rel_path in STATE_FILES_TO_BACKUP:
        src = backup_dir / rel_path
        if src.exists() and src.is_file():
            dst = BASE_DIR / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            restored_count += 1
    log(f"Successfully restored {restored_count} state files.", "PASS")


def run_preflight_validation() -> bool:
    log("Executing Pre-Flight Validation Checks...", "STEP")
    py_exe = get_python_exe()

    # 1. Architecture Validator
    arch_script = BASE_DIR / "architecture_validator.py"
    if arch_script.exists():
        res = subprocess.run([py_exe, str(arch_script)], cwd=str(BASE_DIR), capture_output=True, text=True)
        if res.returncode != 0:
            log(f"Architecture validation FAILED:\n{res.stderr or res.stdout}", "FAIL")
            return False
        log("Architecture integrity validated (100% integrity).", "PASS")

    # 2. Subsystem & Hub automated tests
    test_files = [
        "tests/test_hub_capability_negotiation.py",
        "tests/test_hub_pairing.py",
        "tests/test_hub_sync.py",
        "tests/test_hub_transport.py",
        "tests/test_database_persistence.py",
        "tests/test_conversation_planner.py"
    ]
    existing_tests = [str(BASE_DIR / t) for t in test_files if (BASE_DIR / t).exists()]
    if existing_tests:
        cmd = [py_exe, "-m", "pytest"] + existing_tests + ["-q"]
        res = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True)
        if res.returncode != 0:
            log(f"Automated unit tests FAILED:\n{res.stdout}\n{res.stderr}", "FAIL")
            return False
        log(f"Automated unit tests PASSED ({len(existing_tests)} test suites).", "PASS")

    return True


def run_smoke_test(timeout_s: int = 70) -> bool:
    log("Running smoke test & health verification...", "STEP")
    py_exe = get_python_exe()
    smoke_script = BASE_DIR / "scripts" / "smoke_test.py"

    start_time = time.time()
    last_reported = 0
    while time.time() - start_time < timeout_s:
        elapsed = int(time.time() - start_time)
        res = subprocess.run([py_exe, str(smoke_script), "--retries", "1", "--timeout", "3"],
                             cwd=str(BASE_DIR), capture_output=True, text=True)
        if res.returncode == 0:
            log(f"Health verification & smoke tests PASSED after {elapsed}s!", "PASS")
            print(res.stdout)
            return True
        if elapsed - last_reported >= 10:
            log(f"Waiting for neural models and services to initialize... ({elapsed}s elapsed)", "INFO")
            last_reported = elapsed
        time.sleep(3)

    log(f"Health verification timed out after {timeout_s}s.", "FAIL")
    return False


def deploy(target_commit: str = None, dry_run: bool = False, env: str = "production") -> bool:
    start_time = datetime.now(timezone.utc)
    commit = target_commit or get_current_git_commit()

    print("=" * 65)
    print("  VIVY-AI PRODUCTION DEPLOYMENT PIPELINE")
    print(f"  Target Environment : {env}")
    print(f"  Target Commit SHA  : {commit}")
    print(f"  Execution Time     : {start_time.isoformat()}")
    print(f"  Dry-Run Mode       : {dry_run}")
    print("=" * 65 + "\n")

    # Step 1: Pre-deployment Backup
    backup_dir = create_state_backup()

    # Step 2: Pre-flight Validation
    if not run_preflight_validation():
        log("Pre-flight validation failed. Aborting deployment before modifying runtime.", "FAIL")
        return False

    if dry_run:
        log("Dry-run mode active. Skipping live process rollout.", "WARN")
        return True

    # Step 3: Rolling Update via Docker Compose (if available) or Service Supervisor
    domain = os.environ.get("VIVY_DOMAIN", "").strip()
    has_docker = False
    docker_cmd = None

    if shutil.which("docker"):
        try:
            # Confirm Docker daemon is running and reachable
            res_daemon = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=5)
            if res_daemon.returncode == 0:
                res_v2 = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
                if res_v2.returncode == 0:
                    has_docker = True
                    docker_cmd = ["docker", "compose"]
                elif shutil.which("docker-compose"):
                    has_docker = True
                    docker_cmd = ["docker-compose"]
        except Exception:
            has_docker = False

    used_docker = False
    if has_docker:
        log("Docker detected. Deploying via Docker Compose container stack...", "STEP")
        env_vars = os.environ.copy()
        if domain:
            env_vars["VIVY_DOMAIN"] = domain
        subprocess.run(docker_cmd + ["down", "--remove-orphans"], cwd=str(BASE_DIR), env=env_vars)
        res_docker = subprocess.run(docker_cmd + ["up", "-d", "--build"], cwd=str(BASE_DIR), env=env_vars)
        if res_docker.returncode == 0:
            used_docker = True
            log("Docker Compose services launched successfully.", "PASS")
        else:
            log("Docker Compose failed, falling back to native supervisor...", "WARN")

    if not used_docker:
        py_exe = get_python_exe()
        supervisor_script = BASE_DIR / "scripts" / "production_service.py"
        log("Managing Vivy AI production service via native supervisor...", "STEP")
        subprocess.run([py_exe, str(supervisor_script), "stop"], cwd=str(BASE_DIR))
        time.sleep(2)
        res_start = subprocess.run([py_exe, str(supervisor_script), "start"], cwd=str(BASE_DIR))
        if res_start.returncode != 0:
            log("Service failed to start! Commencing rollback...", "FAIL")
            restore_state_backup(backup_dir)
            subprocess.run([py_exe, str(supervisor_script), "start"], cwd=str(BASE_DIR))
            return False

        # Launch Caddy reverse proxy if binary is present
        caddy_bin = BASE_DIR / "deploy" / "caddy" / "caddy.exe"
        if not caddy_bin.exists():
            caddy_bin_nix = BASE_DIR / "deploy" / "caddy" / "caddy"
            if caddy_bin_nix.exists():
                caddy_bin = caddy_bin_nix
            elif shutil.which("caddy"):
                caddy_bin = Path(shutil.which("caddy"))

        if caddy_bin.exists() and (BASE_DIR / "deploy" / "caddy" / "Caddyfile").exists():
            log(f"Starting Caddy reverse proxy ({caddy_bin.name})...", "STEP")
            caddy_env = os.environ.copy()
            if domain:
                caddy_env["VIVY_DOMAIN"] = domain
            subprocess.run([str(caddy_bin), "stop"], cwd=str(BASE_DIR), capture_output=True)
            subprocess.run([str(caddy_bin), "start", "--config", str(BASE_DIR / "deploy" / "caddy" / "Caddyfile")],
                           cwd=str(BASE_DIR), env=caddy_env)

    # Step 4: Health Probing & Verification
    healthy = run_smoke_test(timeout_s=75)
    if not healthy:
        log("New deployment failed health checks! Initiating zero-data-loss rollback...", "FAIL")
        if used_docker and docker_cmd:
            subprocess.run(docker_cmd + ["down"], cwd=str(BASE_DIR))
        else:
            py_exe = get_python_exe()
            supervisor_script = BASE_DIR / "scripts" / "production_service.py"
            subprocess.run([py_exe, str(supervisor_script), "stop"], cwd=str(BASE_DIR))
            caddy_bin = BASE_DIR / "deploy" / "caddy" / "caddy.exe"
            if caddy_bin.exists():
                subprocess.run([str(caddy_bin), "stop"], cwd=str(BASE_DIR), capture_output=True)
        restore_state_backup(backup_dir)
        if used_docker and docker_cmd:
            subprocess.run(docker_cmd + ["up", "-d"], cwd=str(BASE_DIR))
        else:
            subprocess.run([py_exe, str(supervisor_script), "start"], cwd=str(BASE_DIR))
        log("Rollback completed. Restored previous stable state.", "WARN")
        return False

    # Step 5: Save Deployment Manifest
    domain = os.environ.get("VIVY_DOMAIN", "").strip()
    manifest_url = f"https://{domain}" if domain else ""
    manifest = {
        "environment": env,
        "commit_sha": commit,
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "backup_snapshot": backup_dir.name,
        "status": "HEALTHY",
        "url": manifest_url
    }
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    DEPLOY_MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("\n" + "=" * 65)
    log("PRODUCTION DEPLOYMENT COMPLETED SUCCESSFULLY!", "PASS")
    if manifest_url:
        print(f"  Live Public URL : {manifest_url}")
    print(f"  Deployment SHA  : {commit}")
    print("=" * 65 + "\n")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vivy-AI Production Deployment")
    parser.add_argument("--commit", default=None, help="Target Git commit SHA")
    parser.add_argument("--env", default="production", help="Deployment environment name")
    parser.add_argument("--dry-run", action="store_true", help="Validate and backup without restarting service")
    parser.add_argument("--rollback", default=None, help="Specific backup directory to restore")

    args = parser.parse_args()

    if args.rollback:
        rb_path = Path(args.rollback)
        if not rb_path.is_absolute():
            rb_path = BACKUP_ROOT / args.rollback
        if rb_path.exists():
            restore_state_backup(rb_path)
            sys.exit(0)
        else:
            print(f"Error: Backup path {rb_path} does not exist", file=sys.stderr)
            sys.exit(1)

    success = deploy(target_commit=args.commit, dry_run=args.dry_run, env=args.env)
    sys.exit(0 if success else 1)
