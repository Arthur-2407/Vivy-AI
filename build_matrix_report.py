import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def main():
    static_file = os.path.join(BASE_DIR, "Reports", "static_dependency_graph.json")
    trace_file = os.path.join(BASE_DIR, "Reports", "runtime_execution_trace.json")
    
    with open(static_file, "r", encoding="utf-8") as f:
        static_graph = json.load(f)
        
    runtime_trace = {}
    if os.path.exists(trace_file):
        with open(trace_file, "r", encoding="utf-8") as f:
            runtime_trace = json.load(f)
            
    # Matrix mapping logic
    levels = {
        "Level 1: Hardware Interfacing": ["mic_input.py", "perception/camera_manager.py", "perception/audio_pipeline.py"],
        "Level 2: Multimodal Perception": ["perception/face_detector.py", "perception/screen_pipeline.py", "perception/runner.py"],
        "Level 3: Memory & State Management": ["session_manager.py", "memory_orchestrator.py", "circadian/circadian_engine.py"],
        "Level 4: Emotional Engine": ["emotion/emotion.py"],
        "Level 5: Cognitive Reasoning": ["conversation.py", "cognitive_orchestrator.py"],
        "Level 6: Expression & Synthesis": ["voice.py", "avatar_bridge.py", "animator/animator.py"],
        "Level 7: Network Intelligence": ["internet/internet_manager.py", "internet/duckduckgo_provider.py"],
        "Level 8: Neural Learning Fabric": ["neural/neural_orchestrator.py", "neural/experience_encoder.py", "neural/prediction_engine.py"],
        "Level 9: Executive Agency": ["agi/executive/agency_controller.py", "agi/executive/self_model.py", "agi/executive/goal_motivation_engine.py"],
        "Level 10: Unified Cognitive Event Bus": ["agi/bus/event_bus.py"],
        "Level 11: Long-Term Continuity": ["evolution/evolution_engine.py"]
    }
    
    matrix = {}
    for level, modules in levels.items():
        matrix[level] = {}
        for mod in modules:
            is_present = mod in static_graph
            is_executed = mod in runtime_trace.get("modules_hit", [])
            connections = static_graph.get(mod, [])
            
            matrix[level][mod] = {
                "present_on_disk": is_present,
                "executed_at_runtime": is_executed,
                "connections": connections
            }
            
    out_json = os.path.join(BASE_DIR, "Reports", "vivy_architecture_matrix.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(matrix, f, indent=2)
        
    # Generate MD Report
    report = "# Architecture Validation Matrix Report\n\n"
    report += "## Runtime Execution & Hardware Path Proof\n"
    report += "Hardware Paths Triggered:\n"
    for hw in runtime_trace.get("hardware_paths", []):
        report += f"- {hw}\n"
    
    report += "\n## Matrix by Architectural Level\n"
    
    for level, modules in matrix.items():
        report += f"### {level}\n"
        for mod, data in modules.items():
            status = "✅ CONNECTED" if data['executed_at_runtime'] else ("⚠️ ON-DISK ONLY" if data['present_on_disk'] else "❌ MISSING")
            report += f"- **{mod}**: {status}\n"
            if data['connections']:
                report += f"  - Dependencies: {', '.join(data['connections'][:5])}{'...' if len(data['connections'])>5 else ''}\n"
                
    out_md = os.path.join(BASE_DIR, "Reports", "Architecture_Matrix_Report.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(report)
        
    print("Matrix generation complete.")
    print(f"JSON: {out_json}")
    print(f"MD: {out_md}")

if __name__ == "__main__":
    main()
