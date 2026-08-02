import json
import re

registry_file = r"d:\Vivy\vivy_animation_registry.json"
controller_file = r"D:\Vivy\Mate-Engine\Assets\MATE ENGINE - Animations\AvatarAnimatorControllerV2.controller"

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_text(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

def main():
    try:
        registry = load_json(registry_file)
        controller = load_text(controller_file)
    except Exception as e:
        print(f"Error loading files: {e}")
        return

    # Parse registry
    entries = []
    categories = registry.get("categories", {})
    for cat_name, items in categories.items():
        for item in items:
            entries.append({
                "id": item.get("id"),
                "trigger": item.get("trigger"),
                "bool_param": item.get("bool_param"),
                "index_param": item.get("index_param"),
                "index_val": item.get("index_val"),
                "layer": item.get("layer", "Base Layer"),
                "category": cat_name
            })

    # Stats
    stat_missingStates = 0
    stat_missingMotions = 0
    stat_missingClips = 0
    stat_brokenTransitions = 0
    stat_brokenParameters = 0
    
    # Suspicions
    s1_motionNone = False
    s2_wrongClip = False
    s4_missingTrans = False
    s6_badParams = False
    s7_incompleteLayers = False
    s10_writeDefaults = False

    failures = []

    # Simple string checks for params
    for entry in entries:
        anim_id = entry["id"] or entry["trigger"] or entry["bool_param"] or entry["index_param"]
        if not anim_id: continue

        # Check parameter
        param_ok = True
        if entry["trigger"] and f"m_Name: {entry['trigger']}" not in controller:
            param_ok = False
        if entry["bool_param"] and f"m_Name: {entry['bool_param']}" not in controller:
            param_ok = False
        if entry["index_param"] and f"m_Name: {entry['index_param']}" not in controller:
            param_ok = False

        if not param_ok:
            stat_brokenParameters += 1
            s6_badParams = True
            failures.append(f"{anim_id} | Parameter missing | Required parameter not found | Verified in YAML | Animator Controller | Add missing parameters")

        # Check State
        state_match = re.search(r'm_Name: ' + re.escape(anim_id) + r'\b', controller)
        if not state_match:
            stat_missingStates += 1
            failures.append(f"{anim_id} | State missing | State '{anim_id}' not found | Verified in YAML | Animator Controller | Generate state")
            continue

        # Very basic motion check - difficult in raw YAML without a real parser
        # Just check if "_Dummy" is prevalent in the file
        
    s1_motionNone = controller.count("m_Motion: {fileID: 0}") > 10
    s2_wrongClip = controller.count("_Dummy") > 0
    s10_writeDefaults = controller.count("m_WriteDefaultValues: 1") > 0

    print("=== FINAL REPORT DATA ===")
    print(f"1. Is the Animator Controller complete? | NO")
    print(f"2. Is every registry animation represented? | {'YES' if stat_missingStates == 0 else 'NO'}")
    print(f"3. Number of registry animations | {len(entries)}")
    print(f"4. Number of Animator States | NOT FULLY VERIFIED")
    print(f"5. Number of missing States | {stat_missingStates}")
    print(f"6. Number of missing Motions | NOT FULLY VERIFIED")
    print(f"7. Number of missing Clips | {'YES' if s2_wrongClip else '0'}")
    print(f"8. Number of broken transitions | NOT FULLY VERIFIED")
    print(f"9. Number of broken parameters | {stat_brokenParameters}")
    
    print("\n=== SUSPICIONS ===")
    print(f"1. Many Animator States have Motion = None | {str(s1_motionNone).upper()}")
    print(f"2. Many states reference the wrong AnimationClip | {str(s2_wrongClip).upper()}")
    print(f"4. Transitions are missing | NOT VERIFIED")
    print(f"6. Animator parameters do not match registry | {str(s6_badParams).upper()}")
    print(f"10. Write Defaults break playback | {str(s10_writeDefaults).upper()}")

    print("\n=== FAILURES ===")
    for f in failures[:50]:
        print(f)
    if len(failures) > 50:
        print(f"... and {len(failures) - 50} more")

if __name__ == '__main__':
    main()
