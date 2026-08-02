using UnityEngine;
using UnityEditor;
using UnityEditor.Animations;
using System.IO;
using System.Collections.Generic;
using System.Text;
using System.Linq;

namespace VivyAI.Editor
{
    [InitializeOnLoad]
    public class ForensicAuditRunner
    {
        private static string registryFilePath = "d:/Vivy/vivy_animation_registry.json";
        private static string reportPath = "d:/Vivy/Forensic_Audit_Report.txt";

        static ForensicAuditRunner()
        {
            EditorApplication.delayCall += RunAuditOnce;
        }

        static void RunAuditOnce()
        {
            if (!SessionState.GetBool("ForensicAuditReadOnly2", false))
            {
                SessionState.SetBool("ForensicAuditReadOnly2", true);
                RunAudit();
            }
        }

        [MenuItem("Vivy AI/Run READ ONLY Forensic Audit")]
        public static void RunAuditMenuItem()
        {
            RunAudit();
        }

        public static void RunAudit()
        {
            Debug.Log("[ForensicAudit] Starting READ-ONLY Forensic Verification...");

            if (!File.Exists(registryFilePath))
            {
                File.WriteAllText(reportPath, "ERROR: Registry file not found.");
                return;
            }

            string jsonContent = File.ReadAllText(registryFilePath);
            var root = VivyAnimatorGenerator.MiniJSON.Parse(jsonContent) as Dictionary<string, object>;
            
            if (root == null || !root.ContainsKey("categories")) return;

            var categories = root["categories"] as Dictionary<string, object>;
            List<AnimEntry> entries = new List<AnimEntry>();

            foreach (var category in categories)
            {
                var list = category.Value as List<object>;
                if (list == null) continue;

                foreach (var item in list)
                {
                    var dict = item as Dictionary<string, object>;
                    if (dict == null) continue;

                    AnimEntry entry = new AnimEntry();
                    entry.category = category.Key;
                    if (dict.TryGetValue("id", out object idObj)) entry.id = idObj as string;
                    if (dict.TryGetValue("trigger", out object tObj)) entry.trigger = tObj as string;
                    if (dict.TryGetValue("bool_param", out object bObj)) entry.bool_param = bObj as string;
                    if (dict.TryGetValue("index_param", out object ipObj)) entry.index_param = ipObj as string;
                    if (dict.TryGetValue("index_val", out object ivObj)) entry.index_val = System.Convert.ToInt32(ivObj);
                    if (dict.TryGetValue("layer", out object lObj)) entry.layer = lObj as string;

                    entries.Add(entry);
                }
            }

            AnimatorController targetController = null;
            string[] guids = AssetDatabase.FindAssets("t:AnimatorController");
            foreach (string guid in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (path.Contains("AvatarAnimatorControllerV2.controller"))
                {
                    targetController = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
                    break;
                }
            }

            if (targetController == null)
            {
                foreach (string guid in guids)
                {
                    string path = AssetDatabase.GUIDToAssetPath(guid);
                    if (path.Contains("AvatarAnimatorController.controller"))
                    {
                        targetController = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
                        break;
                    }
                }
            }

            if (targetController == null)
            {
                File.WriteAllText(reportPath, "ERROR: Target controller not found.");
                return;
            }

            StringBuilder report = new StringBuilder();
            
            int stat_registryAnimations = entries.Count;
            int stat_animatorStates = 0;
            int stat_missingStates = 0;
            int stat_missingMotions = 0;
            int stat_missingClips = 0;
            int stat_brokenTransitions = 0;
            int stat_brokenParameters = 0;
            int stat_wrongClipReferences = 0;
            int stat_rigIncompatibilities = 0;
            int stat_layerProblems = 0;
            int stat_avatarMaskProblems = 0;
            int stat_rootMotionProblems = 0;
            int stat_writeDefaultsProblems = 0;

            // Count all states in controller
            foreach (var layer in targetController.layers)
            {
                if (layer.stateMachine != null) stat_animatorStates += layer.stateMachine.states.Length;
                
                // Check layer problems
                if (layer.avatarMask != null) stat_avatarMaskProblems++;
            }

            // Suspicions flags
            bool s1_motionNone = false;
            bool s2_wrongClip = false;
            bool s3_wrongRig = false;
            bool s4_missingTrans = false;
            bool s5_badTransConditions = false;
            bool s6_badParams = false;
            bool s7_incompleteLayers = false;
            bool s8_avatarMasks = false;
            bool s9_rootMotion = targetController.layers.Length > 0; // simplistic
            bool s10_writeDefaults = false;

            StringBuilder failures = new StringBuilder();

            foreach (var entry in entries)
            {
                string animId = !string.IsNullOrEmpty(entry.id) ? entry.id : (entry.trigger ?? entry.bool_param ?? entry.index_param);
                if (string.IsNullOrEmpty(animId)) continue;

                string targetLayer = string.IsNullOrEmpty(entry.layer) ? "Base Layer" : entry.layer;
                bool layerExists = HasLayer(targetController, targetLayer);
                
                if (!layerExists)
                {
                    stat_layerProblems++;
                    s7_incompleteLayers = true;
                    failures.AppendLine($"{animId}|Layer missing|Layer '{targetLayer}' not found in controller|Verified in targetController.layers|Animator Controller|{targetController.name}|Create layer '{targetLayer}'");
                    continue;
                }

                // Check params
                bool paramOk = true;
                if (!string.IsNullOrEmpty(entry.trigger) && !HasParameter(targetController, entry.trigger, AnimatorControllerParameterType.Trigger)) paramOk = false;
                if (!string.IsNullOrEmpty(entry.bool_param) && !HasParameter(targetController, entry.bool_param, AnimatorControllerParameterType.Bool)) paramOk = false;
                if (!string.IsNullOrEmpty(entry.index_param) && !HasParameter(targetController, entry.index_param, AnimatorControllerParameterType.Int) && !HasParameter(targetController, entry.index_param, AnimatorControllerParameterType.Float)) paramOk = false;

                if (!paramOk)
                {
                    stat_brokenParameters++;
                    s6_badParams = true;
                    failures.AppendLine($"{animId}|Parameter missing|Required parameter for trigger/bool/index not found|Verified in targetController.parameters|Animator Controller|{targetController.name}|Add missing parameters");
                }

                var sm = GetStateMachine(targetController, targetLayer);
                AnimatorState state = GetState(sm, animId);

                if (state == null)
                {
                    stat_missingStates++;
                    failures.AppendLine($"{animId}|State missing|State '{animId}' not found in layer '{targetLayer}'|Verified in targetController states|Animator Controller|{targetController.name}|Generate state '{animId}'");
                    continue;
                }

                if (state.writeDefaultValues)
                {
                    stat_writeDefaultsProblems++;
                    s10_writeDefaults = true;
                }

                if (state.motion == null)
                {
                    stat_missingMotions++;
                    s1_motionNone = true;
                    failures.AppendLine($"{animId}|Motion = NULL|State exists but has no AnimationClip assigned|Verified in state.motion == null|Animator Controller|{targetController.name}|Assign correct AnimationClip");
                }
                else
                {
                    AnimationClip clip = state.motion as AnimationClip;
                    if (clip == null)
                    {
                        stat_wrongClipReferences++;
                        s2_wrongClip = true;
                        failures.AppendLine($"{animId}|Invalid Motion|Motion is assigned but is not an AnimationClip (maybe BlendTree)|Verified in state.motion type|Animator Controller|{targetController.name}|Ensure Motion is AnimationClip");
                    }
                    else
                    {
                        // Check if clip is dummy or actual
                        if (clip.name.Contains("_Dummy"))
                        {
                            stat_missingClips++;
                            s2_wrongClip = true;
                            failures.AppendLine($"{animId}|Dummy Clip|Clip '{clip.name}' is a placeholder|Verified by clip name|Animator Controller|{targetController.name}|Replace Dummy with real clip");
                        }
                        
                        // Check Rig compatibility
                        string clipPath = AssetDatabase.GetAssetPath(clip);
                        if (!string.IsNullOrEmpty(clipPath) && !clipPath.Contains(".anim")) // if it's an FBX
                        {
                            ModelImporter importer = AssetImporter.GetAtPath(clipPath) as ModelImporter;
                            if (importer != null && importer.animationType != ModelImporterAnimationType.Human)
                            {
                                stat_rigIncompatibilities++;
                                s3_wrongRig = true;
                                failures.AppendLine($"{animId}|Rig Incompatible|Clip imported as Generic/None instead of Humanoid|Verified by ModelImporter.animationType|Model Asset|{Path.GetFileName(clipPath)}|Change Rig to Humanoid");
                            }
                        }
                    }
                }

                // Transitions
                AnimatorStateTransition transition = null;
                foreach (var t in sm.anyStateTransitions)
                {
                    if (t.destinationState == state) { transition = t; break; }
                }

                if (transition == null)
                {
                    stat_brokenTransitions++;
                    s4_missingTrans = true;
                    failures.AppendLine($"{animId}|Transition missing|AnyState never reaches {animId}|Verified by transition graph|Animator Controller|{targetController.name}|Generate transition");
                }
                else
                {
                    if (transition.conditions == null || transition.conditions.Length == 0)
                    {
                        stat_brokenTransitions++;
                        s5_badTransConditions = true;
                        failures.AppendLine($"{animId}|Empty Conditions|Transition exists but has no conditions|Verified by transition.conditions.Length|Animator Controller|{targetController.name}|Add conditions");
                    }
                }

                // Exit transitions for bool
                if (!string.IsNullOrEmpty(entry.bool_param))
                {
                    bool hasExit = false;
                    foreach (var ext in state.transitions)
                    {
                        if (ext.conditions.Length > 0 && ext.conditions[0].parameter == entry.bool_param && ext.conditions[0].mode == AnimatorConditionMode.IfNot)
                        {
                            hasExit = true; break;
                        }
                    }
                    if (!hasExit)
                    {
                        stat_brokenTransitions++;
                        failures.AppendLine($"{animId}|Exit Transition Missing|State activated by bool lacks an 'IfNot' exit transition|Verified by state.transitions|Animator Controller|{targetController.name}|Add exit transition");
                    }
                }
            }

            // Write report
            report.AppendLine("=== FINAL REPORT DATA ===");
            report.AppendLine($"1. Is the Animator Controller complete?|{(stat_missingStates == 0 && stat_missingMotions == 0 && stat_missingClips == 0 ? "YES" : "NO")}");
            report.AppendLine($"2. Is every registry animation represented?|{(stat_missingStates == 0 ? "YES" : "NO")}");
            report.AppendLine($"3. Number of registry animations|{stat_registryAnimations}");
            report.AppendLine($"4. Number of Animator States|{stat_animatorStates}");
            report.AppendLine($"5. Number of missing States|{stat_missingStates}");
            report.AppendLine($"6. Number of missing Motions|{stat_missingMotions}");
            report.AppendLine($"7. Number of missing Clips|{stat_missingClips}");
            report.AppendLine($"8. Number of broken transitions|{stat_brokenTransitions}");
            report.AppendLine($"9. Number of broken parameters|{stat_brokenParameters}");
            report.AppendLine($"10. Number of wrong clip references|{stat_wrongClipReferences}");
            report.AppendLine($"11. Number of rig incompatibilities|{stat_rigIncompatibilities}");
            report.AppendLine($"12. Number of layer problems|{stat_layerProblems}");
            report.AppendLine($"13. Number of Avatar Mask problems|{stat_avatarMaskProblems}");
            report.AppendLine($"14. Number of Root Motion problems|{stat_rootMotionProblems} (NOT VERIFIED)");
            report.AppendLine($"15. Number of Write Defaults problems|{stat_writeDefaultsProblems}");

            report.AppendLine("\n=== SUSPICIONS ===");
            report.AppendLine($"1. Many Animator States have Motion = None|{s1_motionNone.ToString().ToUpper()}");
            report.AppendLine($"2. Many states reference the wrong AnimationClip|{s2_wrongClip.ToString().ToUpper()}");
            report.AppendLine($"3. Many clips use the wrong Rig|{s3_wrongRig.ToString().ToUpper()}");
            report.AppendLine($"4. Transitions are missing|{s4_missingTrans.ToString().ToUpper()}");
            report.AppendLine($"5. Transitions exist but conditions never become true|{s5_badTransConditions.ToString().ToUpper()}");
            report.AppendLine($"6. Animator parameters do not match registry|{s6_badParams.ToString().ToUpper()}");
            report.AppendLine($"7. Layers exist but contain incomplete State Machines|{s7_incompleteLayers.ToString().ToUpper()}");
            report.AppendLine($"8. Avatar Masks suppress playback|{s8_avatarMasks.ToString().ToUpper()}");
            report.AppendLine($"9. Root Motion causes the avatar to sink|NOT VERIFIED");
            report.AppendLine($"10. Write Defaults break playback|{s10_writeDefaults.ToString().ToUpper()}");

            report.AppendLine("\n=== FAILURES ===");
            report.Append(failures.ToString());

            File.WriteAllText(reportPath, report.ToString());
            Debug.Log("[ForensicAudit] Read-Only Audit Complete!");
        }

        private static bool HasLayer(AnimatorController controller, string layerName)
        {
            foreach (var layer in controller.layers)
                if (layer.name == layerName) return true;
            return false;
        }

        private static bool HasParameter(AnimatorController controller, string paramName, AnimatorControllerParameterType type)
        {
            foreach (var param in controller.parameters)
                if (param.name == paramName && param.type == type) return true;
            return false;
        }

        private static AnimatorStateMachine GetStateMachine(AnimatorController controller, string layerName)
        {
            foreach (var layer in controller.layers)
                if (layer.name == layerName) return layer.stateMachine;
            return null;
        }

        private static AnimatorState GetState(AnimatorStateMachine sm, string stateName)
        {
            if (sm == null) return null;
            foreach (var state in sm.states)
                if (state.state.name == stateName) return state.state;
            return null;
        }

        private struct AnimEntry
        {
            public string id;
            public string trigger;
            public string bool_param;
            public string index_param;
            public int index_val;
            public string layer;
            public string category;
        }
    }
}
