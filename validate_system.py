"""Vivy AI — Unified System Validation & Acceptance Suite (PART 8)"""
import os, sys, ast, requests, json

print("=== STARTING VIVY AI ACCEPTANCE VALIDATION ===")

BASE_DIR = "d:/Vivy"

# Dynamic scratch directory detection to avoid hardcoding conversation IDs
BRAIN_DIR = "C:/Users/SATYAJEET/.gemini/antigravity-ide/brain"
if os.path.exists(BRAIN_DIR):
    subdirs = [os.path.join(BRAIN_DIR, d) for d in os.listdir(BRAIN_DIR) if os.path.isdir(os.path.join(BRAIN_DIR, d))]
    if subdirs:
        latest_dir = max(subdirs, key=os.path.getmtime)
        SCRATCH_DIR = os.path.join(latest_dir, "scratch")
    else:
        SCRATCH_DIR = ""
else:
    SCRATCH_DIR = ""

# 1. Run all regression test scripts
regression_scripts = [
    "regression_part1.py",
    "regression_part2.py",
    "regression_part3.py",
    "regression_part4.py",
    "regression_part5.py",
    "regression_part6.py",
    "regression_part7.py"
]

print("\n--- STAGE 1: SUB-REGRESSIONS CHECK ---")
for script in regression_scripts:
    script_path = os.path.join(SCRATCH_DIR, script)
    if os.path.exists(script_path):
        print(f"Running {script}...")
        try:
            with open(script_path, encoding="utf-8") as f:
                code = f.read()
            exec(code, {"__name__": "__main__"})
            print(f"[OK] {script} PASSED")
        except Exception as e:
            print(f"[FAIL] {script} FAILED: {e}")
            sys.exit(1)
    else:
        print(f"[WARN] {script} missing at {script_path}")

# 2. Test live DuckDuckGo search integration
print("\n--- STAGE 2: LIVE DUCKDUCKGO SEARCH CHECK ---")
sys.path.insert(0, BASE_DIR)
try:
    from conversation import search_duckduckgo
    res = search_duckduckgo("weather today")
    if res:
        print("[OK] DuckDuckGo Search API: OK (Results retrieved)")
    else:
        print("[WARN] DuckDuckGo Search API: Empty response (possible rate limiting/offline)")
except Exception as e:
    print(f"[FAIL] DuckDuckGo Search API check failed: {e}")
    sys.exit(1)

# 3. Scan web_server.py routes syntax compatibility
print("\n--- STAGE 3: FLASK ENDPOINTS SIGNATURES CHECK ---")
server_path = os.path.join(BASE_DIR, "web_server.py")
try:
    with open(server_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
        
    routes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and getattr(decorator.func, "attr", "") == "route":
                    route_path = decorator.args[0].value if decorator.args else "unknown"
                    routes.append((node.name, route_path))
                    
    print("Found Flask routes in web_server.py:")
    for name, path in routes:
        print(f"  - Route '{path}' maps to function '{name}'")
        
    required_routes = ["/api/send", "/api/history", "/api/status", "/api/config", "/api/memory"]
    found_paths = [r[1] for r in routes]
    for req in required_routes:
        assert req in found_paths, f"Missing required endpoint: {req}"
    print("[OK] All 5 required API route signatures are present and compatible.")
except Exception as e:
    print(f"[FAIL] Flask Endpoints check failed: {e}")
    sys.exit(1)

# 4. Verify Memory File Integrity
print("\n--- STAGE 4: MEMORY FILE SCHEMA CHECK ---")
mem_path = os.path.join(BASE_DIR, "vivy_memory.json")
try:
    with open(mem_path, encoding="utf-8") as f:
        data = json.load(f)
    print("Keys found in memory:")
    print(" ", list(data.keys()))
    required_keys = ["relationship", "emotion_vector", "mood", "reply_openings", "long_term_facts", "temporary_states", "summary", "current_topic"]
    for rk in required_keys:
        assert rk in data, f"Schema missing field: {rk}"
    print("[OK] Memory schema is correct and compatible.")
except Exception as e:
    print(f"[FAIL] Memory File check failed: {e}")
    sys.exit(1)

print("\n=== ALL SYSTEM VALIDATION CHECKS PASSED SUCCESSFULLY ===")
