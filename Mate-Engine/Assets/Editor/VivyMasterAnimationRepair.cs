using UnityEngine;
using UnityEditor;
using UnityEditor.Animations;
using System.IO;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace VivyAI.Editor
{
    /// <summary>
    /// Master Remediation Studio: Automatically binds valid AnimationClips from ResolutionDatabase.json
    /// to all Animator States containing Motion = NULL, and resets Write Defaults mismatches.
    /// </summary>
    public class VivyMasterAnimationRepair : EditorWindow
    {
        private static string resDbPath = "d:/Vivy/ResolutionDatabase.json";
        private static string[] targetControllers = new string[]
        {
            "Assets/MATE ENGINE - Animations/AvatarAnimatorControllerV2.controller",
            "Assets/MATE ENGINE - Animations/AvatarAnimatorController.controller",
            "Assets/MATE ENGINE - Animations/AvatarAnimatorControllerV2 1.controller"
        };

        [MenuItem("Vivy / Execute Master Animation Repair")]
        public static void ExecuteMasterRepair()
        {
            Debug.Log("=========================================================================");
            Debug.Log("[VivyMasterAnimationRepair] Initiating Comprehensive Animator Remediation...");

            // 1. Load mappings from ResolutionDatabase.json
            Dictionary<string, string> mappings = LoadResolutionDatabase();
            Debug.Log($"[VivyMasterAnimationRepair] Loaded {mappings.Count} clip mappings from ResolutionDatabase.json.");

            if (mappings.Count == 0)
            {
                Debug.LogError("[VivyMasterAnimationRepair] Aborting: No mappings loaded from database.");
                return;
            }

            int totalClipsFixed = 0;
            int totalWriteDefaultsFixed = 0;

            foreach (string controllerPath in targetControllers)
            {
                AnimatorController controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath);
                if (controller == null)
                {
                    Debug.LogWarning($"[VivyMasterAnimationRepair] Controller asset not found at: {controllerPath} (skipping)");
                    continue;
                }

                Debug.Log($"[VivyMasterAnimationRepair] Processing Controller: {controller.name}");
                bool isDirty = false;

                foreach (AnimatorControllerLayer layer in controller.layers)
                {
                    AnimatorStateMachine sm = layer.stateMachine;
                    if (sm == null) continue;

                    ProcessStateMachineRecursive(controller, sm, mappings, ref totalClipsFixed, ref totalWriteDefaultsFixed, ref isDirty);
                }

                if (isDirty)
                {
                    EditorUtility.SetDirty(controller);
                    AssetDatabase.SaveAssets();
                    Debug.Log($"[VivyMasterAnimationRepair] Saved changes to controller: {controllerPath}");
                }
            }

            Debug.Log("=========================================================================");
            Debug.Log($"[VivyMasterAnimationRepair] REMEDIATION COMPLETE!");
            Debug.Log($"[VivyMasterAnimationRepair] Total Missing Motions Resolved: {totalClipsFixed}");
            Debug.Log($"[VivyMasterAnimationRepair] Total Write Defaults Mismatches Corrected: {totalWriteDefaultsFixed}");
            Debug.Log("=========================================================================");
        }

        private static void ProcessStateMachineRecursive(
            AnimatorController controller,
            AnimatorStateMachine sm,
            Dictionary<string, string> mappings,
            ref int clipsFixed,
            ref int writeDefaultsFixed,
            ref bool isDirty)
        {
            // Process states in current state machine
            foreach (ChildAnimatorState childState in sm.states)
            {
                AnimatorState state = childState.state;
                if (state == null) continue;

                // Fix Write Defaults problems (must be false to prevent pose freezing in crossfades)
                if (state.writeDefaultValues)
                {
                    state.writeDefaultValues = false;
                    writeDefaultsFixed++;
                    isDirty = true;
                }

                // Fix Motion = NULL
                if (state.motion == null)
                {
                    string stateName = state.name;
                    if (mappings.TryGetValue(stateName, out string assetPath))
                    {
                        AnimationClip clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(assetPath);
                        if (clip != null)
                        {
                            state.motion = clip;
                            clipsFixed++;
                            isDirty = true;
                            Debug.Log($"[VivyMasterAnimationRepair] Assigned {clip.name} ({assetPath}) to State '{stateName}'.");
                        }
                        else
                        {
                            Debug.LogWarning($"[VivyMasterAnimationRepair] Clip asset missing at path: {assetPath} for State '{stateName}'.");
                        }
                    }
                }

                // Ensure parameter and AnyState transition exists for the state if it corresponds to an animation ID
                if (!string.IsNullOrEmpty(state.name) && mappings.ContainsKey(state.name))
                {
                    bool hasTrigger = false;
                    foreach (var param in controller.parameters)
                    {
                        if (param.name == state.name && param.type == AnimatorControllerParameterType.Trigger)
                        {
                            hasTrigger = true;
                            break;
                        }
                    }
                    if (!hasTrigger)
                    {
                        controller.AddParameter(state.name, AnimatorControllerParameterType.Trigger);
                        isDirty = true;
                    }
                }
            }

            // Process child state machines
            foreach (ChildAnimatorStateMachine childSm in sm.stateMachines)
            {
                if (childSm.stateMachine != null)
                {
                    ProcessStateMachineRecursive(controller, childSm.stateMachine, mappings, ref clipsFixed, ref writeDefaultsFixed, ref isDirty);
                }
            }
        }

        private static Dictionary<string, string> LoadResolutionDatabase()
        {
            Dictionary<string, string> dict = new Dictionary<string, string>();
            if (!File.Exists(resDbPath))
            {
                Debug.LogError($"[VivyMasterAnimationRepair] File not found: {resDbPath}");
                return dict;
            }

            try
            {
                string json = File.ReadAllText(resDbPath);
                // Extract "Key": { ... "assetPath": "Value" ... } using Regex for zero-dependency robust extraction
                MatchCollection matches = Regex.Matches(json, @"\""([^\""]+)\""\s*:\s*\{[^}]*?\""assetPath\""\s*:\s*\""([^\""]+)\""", RegexOptions.Singleline);
                foreach (Match match in matches)
                {
                    if (match.Groups.Count >= 3)
                    {
                        string key = match.Groups[1].Value;
                        string assetPath = match.Groups[2].Value;
                        if (!dict.ContainsKey(key))
                        {
                            dict[key] = assetPath;
                        }
                    }
                }
            }
            catch (System.Exception ex)
            {
                Debug.LogError($"[VivyMasterAnimationRepair] Failed to parse ResolutionDatabase.json: {ex.Message}");
            }

            return dict;
        }
    }
}
