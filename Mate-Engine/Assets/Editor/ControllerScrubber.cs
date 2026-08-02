using UnityEditor;
using UnityEngine;
using UnityEditor.Animations;
using System.Linq;
using System.Collections.Generic;

public class ControllerScrubber
{
    public static void Scrub()
    {
        string[] guids = AssetDatabase.FindAssets("t:AnimatorController");
        foreach (string guid in guids)
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            if (path.Contains("AvatarAnimatorController"))
            {
                var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
                if (controller != null)
                {
                    bool dirty = false;
                    foreach (var layer in controller.layers)
                    {
                        var sm = layer.stateMachine;
                        if (sm == null) continue;

                        // Find states to delete (any state whose motion is a Dummy clip)
                        var statesToDelete = new List<ChildAnimatorState>();
                        foreach (var childState in sm.states)
                        {
                            if (childState.state.motion != null && childState.state.motion.name.EndsWith("_Dummy"))
                            {
                                statesToDelete.Add(childState);
                            }
                        }
                        
                        foreach (var childState in statesToDelete)
                        {
                            Debug.Log($"[ControllerScrubber] Removed dummy state: {childState.state.name} from layer {layer.name}");
                            sm.RemoveState(childState.state);
                            dirty = true;
                        }
                    }

                    if (dirty)
                    {
                        EditorUtility.SetDirty(controller);
                        AssetDatabase.SaveAssets();
                    }
                }
            }
        }
        Debug.Log("[ControllerScrubber] Scrubbing complete!");
    }
}
