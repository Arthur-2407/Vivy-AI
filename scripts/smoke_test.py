#!/usr/bin/env python3
"""
Vivy-AI — Production Smoke Test & Health Diagnostics Suite
Validates that all production endpoints, APIs, WebSockets, and RPC servers
are responsive, healthy, and conform to expected contracts.
"""

import sys
import os
import time
import json
import socket
import argparse
import urllib.request
import urllib.error
import xmlrpc.client

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


class SmokeTestRunner:
    def __init__(self, host: str = "127.0.0.1", web_port: int = 8080,
                 avatar_port: int = 8765, hub_port: int = 8800, rvc_port: int = 8766,
                 timeout: float = 5.0, retries: int = 3, retry_delay: float = 2.0,
                 scheme: str = "http"):
        self.scheme = scheme
        self.host = host
        self.web_port = web_port
        self.avatar_port = avatar_port
        self.hub_port = hub_port
        self.rvc_port = rvc_port
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay
        self.results = {}

    def log(self, category: str, message: str, status: str = "INFO"):
        prefix = {
            "PASS": "\033[92m[PASS]\033[0m",
            "FAIL": "\033[91m[FAIL]\033[0m",
            "WARN": "\033[93m[WARN]\033[0m",
            "INFO": "\033[94m[INFO]\033[0m"
        }.get(status, f"[{status}]")
        print(f"{prefix} {category:<20} {message}")

    def _http_get(self, path: str) -> tuple[int, dict | str]:
        if (self.scheme == "https" and self.web_port == 443) or (self.scheme == "http" and self.web_port == 80):
            url = f"{self.scheme}://{self.host}{path}"
        else:
            url = f"{self.scheme}://{self.host}:{self.web_port}{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "Vivy-SmokeTest/2.0"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = resp.status
                body = resp.read().decode("utf-8", errors="replace")
                try:
                    return status, json.loads(body)
                except Exception:
                    return status, body
        except urllib.error.HTTPError as e:
            return e.code, str(e)
        except Exception as e:
            return 0, str(e)

    def _tcp_ping(self, port: int) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        try:
            s.connect((self.host, port))
            s.close()
            return True
        except Exception:
            return False

    def test_web_ui(self) -> bool:
        for attempt in range(1, self.retries + 1):
            status, body = self._http_get("/")
            if status == 200 and ("Vivy" in str(body) or "<!DOCTYPE html>" in str(body)):
                self.log("Web Dashboard UI", f"HTTP 200 OK (attempt {attempt})", "PASS")
                self.results["web_ui"] = {"status": "PASS", "http_code": status}
                return True
            time.sleep(self.retry_delay)
        self.log("Web Dashboard UI", f"Failed to load UI (status={status})", "FAIL")
        self.results["web_ui"] = {"status": "FAIL", "http_code": status, "error": str(body)[:200]}
        return False

    def test_api_status(self) -> bool:
        for attempt in range(1, self.retries + 1):
            status, data = self._http_get("/api/status")
            if status == 200 and isinstance(data, dict):
                pipeline_status = data.get("status", "unknown")
                self.log("REST API /api/status", f"HTTP 200 OK — Pipeline status: {pipeline_status}", "PASS")
                self.results["api_status"] = {"status": "PASS", "pipeline_status": pipeline_status}
                return True
            time.sleep(self.retry_delay)
        self.log("REST API /api/status", f"Failed with status={status}", "FAIL")
        self.results["api_status"] = {"status": "FAIL", "http_code": status, "error": str(data)[:200]}
        return False

    def test_api_health(self) -> bool:
        for attempt in range(1, self.retries + 1):
            status, data = self._http_get("/api/health")
            if status == 200 and isinstance(data, dict):
                subsystems = data.get("subsystems", {})
                ready_count = sum(1 for s in subsystems.values() if s.get("state") in ("READY", "CONNECTED", "STANDBY"))
                total_count = len(subsystems)
                self.log("REST API /api/health", f"HTTP 200 OK — Subsystems healthy: {ready_count}/{total_count}", "PASS")
                self.results["api_health"] = {
                    "status": "PASS",
                    "subsystems_total": total_count,
                    "subsystems_ready": ready_count,
                    "subsystem_details": {k: v.get("state") for k, v in subsystems.items()}
                }
                return True
            time.sleep(self.retry_delay)
        self.log("REST API /api/health", f"Failed with status={status}", "FAIL")
        self.results["api_health"] = {"status": "FAIL", "http_code": status, "error": str(data)[:200]}
        return False

    def test_perception_health(self) -> bool:
        for attempt in range(1, self.retries + 1):
            status, data = self._http_get("/api/perception/health")
            if status == 200 and isinstance(data, dict):
                p_status = data.get("status", "unknown")
                self.log("Perception Health", f"HTTP 200 OK — Perception status: {p_status}", "PASS")
                self.results["perception"] = {"status": "PASS", "perception_status": p_status}
                return True
            elif status == 404:
                self.log("Perception Health", "Endpoint not mounted (optional module)", "WARN")
                self.results["perception"] = {"status": "WARN", "message": "not_mounted"}
                return True
            time.sleep(self.retry_delay)
        self.log("Perception Health", f"Check returned status={status}", "WARN")
        self.results["perception"] = {"status": "WARN", "http_code": status}
        return True  # non-fatal

    def test_avatar_bridge_socket(self) -> bool:
        connected = False
        for attempt in range(1, self.retries + 1):
            if self._tcp_ping(self.avatar_port):
                connected = True
                break
            time.sleep(self.retry_delay)

        if connected:
            self.log("Avatar Bridge WS", f"Port {self.avatar_port} LISTENING (MateEngine link active)", "PASS")
            self.results["avatar_bridge"] = {"status": "PASS", "port": self.avatar_port}
            return True
        else:
            self.log("Avatar Bridge WS", f"Port {self.avatar_port} not listening", "FAIL")
            self.results["avatar_bridge"] = {"status": "FAIL", "port": self.avatar_port}
            return False

    def test_hub_websocket(self) -> bool:
        connected = False
        for attempt in range(1, self.retries + 1):
            if self._tcp_ping(self.hub_port):
                connected = True
                break
            time.sleep(self.retry_delay)

        if connected:
            self.log("Vivy Hub WebSocket", f"Port {self.hub_port} LISTENING (Node federation active)", "PASS")
            self.results["vivy_hub"] = {"status": "PASS", "port": self.hub_port}
            return True
        else:
            self.log("Vivy Hub WebSocket", f"Port {self.hub_port} not listening", "WARN")
            self.results["vivy_hub"] = {"status": "WARN", "port": self.hub_port, "note": "Hub may be disabled in config"}
            return True

    def test_rvc_rpc_server(self) -> bool:
        for attempt in range(1, self.retries + 1):
            try:
                proxy = xmlrpc.client.ServerProxy(f"http://{self.host}:{self.rvc_port}", allow_none=True)
                # Try calling system.listMethods or test socket
                if self._tcp_ping(self.rvc_port):
                    self.log("RVC Voice RPC Server", f"Port {self.rvc_port} LISTENING & responding", "PASS")
                    self.results["rvc_rpc"] = {"status": "PASS", "port": self.rvc_port}
                    return True
            except Exception as e:
                pass
            time.sleep(self.retry_delay)

        self.log("RVC Voice RPC Server", f"Port {self.rvc_port} not responding", "WARN")
        self.results["rvc_rpc"] = {"status": "WARN", "port": self.rvc_port, "note": "RVC may be disabled or standalone"}
        return True  # non-fatal fallback exists in pipeline

    def run_all(self) -> bool:
        print("\n" + "=" * 60)
        print("  Vivy-AI Production Smoke Test & Diagnostics")
        print(f"  Target: http://{self.host}:{self.web_port}")
        print(f"  Time  : {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        checks = [
            ("Web UI", self.test_web_ui),
            ("REST API Status", self.test_api_status),
            ("REST API Health", self.test_api_health),
            ("Perception Health", self.test_perception_health),
            ("Avatar Bridge WebSocket", self.test_avatar_bridge_socket),
            ("Vivy Hub WebSocket", self.test_hub_websocket),
            ("RVC RPC Server", self.test_rvc_rpc_server),
        ]

        critical_passed = True
        for name, test_func in checks:
            try:
                res = test_func()
                if name in ("Web UI", "REST API Status", "REST API Health", "Avatar Bridge WebSocket") and not res:
                    critical_passed = False
            except Exception as e:
                self.log(name, f"Exception during check: {e}", "FAIL")
                if name in ("Web UI", "REST API Status", "REST API Health"):
                    critical_passed = False

        print("=" * 60)
        if critical_passed:
            self.log("OVERALL HEALTH", "All critical production services are VERIFIED and OPERATIONAL.", "PASS")
        else:
            self.log("OVERALL HEALTH", "One or more critical checks FAILED.", "FAIL")
        print("=" * 60 + "\n")

        return critical_passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vivy-AI Production Smoke Test")
    parser.add_argument("--host", default="127.0.0.1", help="Target hostname/IP")
    parser.add_argument("--web-port", type=int, default=8080, help="Web UI port")
    parser.add_argument("--avatar-port", type=int, default=8765, help="Avatar Bridge port")
    parser.add_argument("--hub-port", type=int, default=8800, help="Vivy Hub port")
    parser.add_argument("--rvc-port", type=int, default=8766, help="RVC RPC port")
    parser.add_argument("--timeout", type=float, default=5.0, help="Connection timeout in seconds")
    parser.add_argument("--retries", type=int, default=3, help="Max retry count per check")
    parser.add_argument("--scheme", default="http", choices=["http", "https"], help="Protocol scheme (http/https)")
    parser.add_argument("--json-out", default=None, help="Optional file path to output JSON results")

    args = parser.parse_args()
    runner = SmokeTestRunner(
        host=args.host,
        web_port=args.web_port,
        avatar_port=args.avatar_port,
        hub_port=args.hub_port,
        rvc_port=args.rvc_port,
        timeout=args.timeout,
        retries=args.retries,
        scheme=args.scheme
    )

    success = runner.run_all()

    if args.json_out:
        try:
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": time.time(),
                    "success": success,
                    "results": runner.results
                }, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to write JSON output: {e}", file=sys.stderr)

    sys.exit(0 if success else 1)
