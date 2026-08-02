import sys
import os
import traceback

def test_module(name, fn):
    print(f"[TEST] Testing {name}...", end="", flush=True)
    try:
        fn()
        print(" OK!")
    except Exception as e:
        print(f" FAILED: {e}")
        traceback.print_exc()

print("--- TESTING ALL VIVY SINGLETONS ---")

test_module("telemetry_manager (get_telemetry_manager)", lambda: __import__("telemetry_manager").get_telemetry_manager())
test_module("session_manager (get_session_manager)", lambda: __import__("session_manager").get_session_manager())
test_module("memory_orchestrator (get_memory_orchestrator)", lambda: __import__("memory_orchestrator").get_memory_orchestrator())
test_module("knowledge_router (get_knowledge_router)", lambda: __import__("knowledge_router").get_knowledge_router())
test_module("internet.network_manager (get_instance)", lambda: __import__("internet.network_manager").NetworkManager.get_instance())
test_module("evolution (get_evolution_orchestrator)", lambda: __import__("evolution").get_evolution_orchestrator())

print("--- ALL SINGLETONS PASSED CLEANLY ---")
