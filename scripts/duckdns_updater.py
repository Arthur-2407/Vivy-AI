#!/usr/bin/env python3
"""
Vivy-AI — Automated Dynamic DuckDNS Updater
Maintains vivy-ai.duckdns.org A (IPv4) and AAAA (IPv6) records across dynamic IP changes.
Designed for Windows Task Scheduler, zero secret leakage, safe HTTPS updates, and automatic recovery.
"""

import sys
import os
import json
import time
import socket
import argparse
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
SHARED_DIR = BASE_DIR / "shared"
LOGS_DIR = BASE_DIR / "logs"
CACHE_FILE = SHARED_DIR / "duckdns_last_state.json"
TOKEN_FILE = SHARED_DIR / "duckdns_token.txt"
LOG_FILE = LOGS_DIR / "duckdns_updater.log"

DOMAIN = "vivy-ai"
FULL_HOSTNAME = f"{DOMAIN}.duckdns.org"


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_token() -> str | None:
    # 1. Check environment variable
    token = os.environ.get("DUCKDNS_TOKEN", "").strip()
    if token:
        return token

    # 2. Check local protected file in shared directory
    if TOKEN_FILE.exists():
        try:
            tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
            if tok:
                return tok
        except Exception:
            pass

    # 3. Check user home config ~/.vivy/duckdns_token
    user_tok = Path.home() / ".vivy" / "duckdns_token"
    if user_tok.exists():
        try:
            tok = user_tok.read_text(encoding="utf-8").strip()
            if tok:
                return tok
        except Exception:
            pass

    return None


def get_public_ipv4() -> str | None:
    services = [
        "https://api.ipify.org?format=json",
        "https://checkip.amazonaws.com"
    ]
    for url in services:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Vivy-DNS/2.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read().decode("utf-8").strip()
                if "{" in data:
                    data = json.loads(data).get("ip", "").strip()
                if data and "." in data:
                    return data
        except Exception:
            continue
    return None


def get_public_ipv6() -> str | None:
    services = [
        "https://api6.ipify.org?format=json",
        "https://v6.ident.me"
    ]
    for url in services:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Vivy-DNS/2.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read().decode("utf-8").strip()
                if "{" in data:
                    data = json.loads(data).get("ip", "").strip()
                if data and ":" in data:
                    return data
        except Exception:
            continue
    return None


def resolve_dns() -> dict:
    dns_res = {"ipv4": None, "ipv6": None}
    try:
        entries = socket.getaddrinfo(FULL_HOSTNAME, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for e in entries:
            family = e[0]
            addr = e[4][0]
            if family == socket.AF_INET and not dns_res["ipv4"]:
                dns_res["ipv4"] = addr
            elif family == socket.AF_INET6 and not dns_res["ipv6"]:
                dns_res["ipv6"] = addr
    except Exception:
        pass
    return dns_res


def update_duckdns(token: str, ipv4: str | None, ipv6: str | None) -> bool:
    params = {
        "domains": DOMAIN,
        "token": token
    }
    if ipv4:
        params["ip"] = ipv4
    if ipv6:
        params["ipv6"] = ipv6

    query_str = urllib.parse.urlencode(params)
    url = f"https://www.duckdns.org/update?{query_str}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Vivy-DDNS/2.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8").strip()
            if body == "OK":
                log(f"DuckDNS update SUCCESS: IPv4={ipv4 or 'none'}, IPv6={ipv6 or 'none'}")
                return True
            else:
                log("DuckDNS update returned non-OK response from server")
                return False
    except Exception as e:
        log(f"DuckDNS update request failed: {e}")
        return False


def run_check(force: bool = False) -> bool:
    token = get_token()
    if not token:
        log("No DuckDNS token found. (Set DUCKDNS_TOKEN or place in shared/duckdns_token.txt)")
        return False

    cur_ipv4 = get_public_ipv4()
    cur_ipv6 = get_public_ipv6()

    last_state = {}
    if CACHE_FILE.exists():
        try:
            last_state = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    last_ipv4 = last_state.get("ipv4")
    last_ipv6 = last_state.get("ipv6")
    last_time = last_state.get("updated_at", 0)
    now = time.time()

    ip_changed = (cur_ipv4 != last_ipv4) or (cur_ipv6 != last_ipv6)
    time_elapsed = now - last_time

    # Update if IP changed, force flag set, or more than 4 hours passed (heartbeat refresh)
    if not force and not ip_changed and (time_elapsed < 14400):
        log(f"IP addresses unchanged (IPv4: {cur_ipv4}, IPv6: {cur_ipv6}). Skipping update.")
        return True

    log(f"Triggering DuckDNS update (Changed: {ip_changed}, Force: {force}, Elapsed: {int(time_elapsed)}s)...")
    success = update_duckdns(token, cur_ipv4, cur_ipv6)
    if success:
        last_state = {
            "ipv4": cur_ipv4,
            "ipv6": cur_ipv6,
            "updated_at": now,
            "updated_at_iso": datetime.now(timezone.utc).isoformat()
        }
        SHARED_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(last_state, indent=2), encoding="utf-8")
        return True
    return False


def install_scheduled_task() -> bool:
    script_path = str(Path(__file__).resolve())
    py_exe = sys.executable

    task_name = "VivyDuckDNSUpdater"
    cmd = f'"{py_exe}" "{script_path}" --run-once'
    
    log(f"Installing Windows Scheduled Task: {task_name} (every 10 minutes)...")
    try:
        # Delete existing task if present
        subprocess.run(["schtasks", "/delete", "/tn", task_name, "/f"], capture_output=True)
        # Create scheduled task to run every 10 minutes
        res = subprocess.run([
            "schtasks", "/create",
            "/tn", task_name,
            "/tr", cmd,
            "/sc", "minute",
            "/mo", "10",
            "/f"
        ], capture_output=True, text=True)
        if res.returncode == 0:
            log(f"Scheduled Task '{task_name}' installed successfully.")
            return True
        else:
            log(f"Failed to install scheduled task: {res.stderr or res.stdout}")
            return False
    except Exception as e:
        log(f"Exception installing task: {e}")
        return False


def print_status():
    print("=" * 60)
    print("  VIVY-AI DYNAMIC DUCKDNS STATUS")
    print("=" * 60)
    print(f"Target Hostname : {FULL_HOSTNAME}")
    tok = get_token()
    print(f"Token Detected  : {'YES (Configured)' if tok else 'NO (Missing)'}")
    print(f"Current IPv4    : {get_public_ipv4() or 'None'}")
    print(f"Current IPv6    : {get_public_ipv6() or 'None'}")
    
    dns_res = resolve_dns()
    print(f"DNS A (IPv4)    : {dns_res['ipv4'] or 'None'}")
    print(f"DNS AAAA (IPv6) : {dns_res['ipv6'] or 'None'}")

    if CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            print(f"Last Update ISO : {cache.get('updated_at_iso', 'Unknown')}")
            print(f"Cached IPv4     : {cache.get('ipv4', 'Unknown')}")
            print(f"Cached IPv6     : {cache.get('ipv6', 'Unknown')}")
        except Exception:
            pass
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vivy-AI Dynamic DuckDNS Updater")
    parser.add_argument("--run-once", action="store_true", help="Run a single update check")
    parser.add_argument("--force", action="store_true", help="Force update even if IP unchanged")
    parser.add_argument("--install-task", action="store_true", help="Install Windows Scheduled Task")
    parser.add_argument("--status", action="store_true", help="Print current DuckDNS status")

    args = parser.parse_args()

    if args.install_task:
        install_scheduled_task()
    elif args.status:
        print_status()
    else:
        success = run_check(force=args.force)
        sys.exit(0 if success else 1)
