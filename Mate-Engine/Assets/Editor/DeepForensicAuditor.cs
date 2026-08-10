using UnityEngine;
using UnityEditor;
using UnityEditor.Animations;
using System.IO;
using System.Collections.Generic;
using System.Text;

namespace VivyAI.Editor
{
    [InitializeOnLoad]
    public class DeepForensicAuditor
    {
        private static string reportPath = "d:/Vivy/Deep_Audit_Report.txt";

        static DeepForensicAuditor()
        {
            EditorApplication.delayCall += RunAuditOnce;
        }

        static void RunAuditOnce()
        {
            if (!EditorPrefs.GetBool("Vivy_AutoRunStartupAudits", false)) return;
            if (!SessionState.GetBool("DeepForensicAuditDone1", false))
            {
                SessionState.SetBool("DeepForensicAuditDone1", true);
                RunAudit();
            }
        }

        [MenuItem("Vivy AI/Run DEEP Forensic Audit")]
        public static void RunAuditMenuItem()
        {
            RunAudit();
        }

        public static void RunAudit()
        {
            Debug.Log("[DeepForensic] Starting DEEP Forensic Verification...");

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

            // Find Runtime Animator
            Animator runtimeAnimator = null;
            if (EditorApplication.isPlaying)
            {
                runtimeAnimator = UnityEngine.Object.FindFirstObjectByType<Animator>();
            }

            List<string> targetStates = new List<string> { "Idle0", "Idle1", "IdleHappy", "IdleCheer", "IdleSad", "IdleAngry" };
            
            StringBuilder report = new StringBuilder();
            report.AppendLine("=== DEEP FORENSIC AUDIT ===");
            report.AppendLine($"Controller: {targetController.name}");
            report.AppendLine($"Runtime Animator Found: {(runtimeAnimator != null ? "YES" : "NO")}");
            if (runtimeAnimator != null)
            {
                report.AppendLine($"Avatar isHuman: {(runtimeAnimator.avatar != null ? runtimeAnimator.avatar.isHuman.ToString() : "NULL")}");
                report.AppendLine($"Apply Root Motion: {runtimeAnimator.applyRootMotion}");
            }
            report.AppendLine("--------------------------------------------------");

            foreach (var layer in targetController.layers)
            {
                if (layer.stateMachine == null) continue;

                foreach (var stateNode in layer.stateMachine.states)
                {
                    AnimatorState state = stateNode.state;
                    string sName = state.name;

                    // If we only want to log specific states to avoid massive files:
                    // (Actually we will just log the targeted ones fully, and count the rest)
                    bool isTarget = targetStates.Contains(sName);
                    
                    if (!isTarget) continue;

                    report.AppendLine($"\nSTATE: {sName}");
                    report.AppendLine($"Layer: {layer.name}");
                    report.AppendLine($"1. Does the state exist? YES");

                    bool motionAssigned = state.motion != null;
                    report.AppendLine($"2. Is Motion assigned? {(motionAssigned ? "YES" : "NO")}");
                    report.AppendLine($"3. Is Motion NULL? {(!motionAssigned ? "YES" : "NO")}");

                    if (motionAssigned)
                    {
                        AnimationClip clip = state.motion as AnimationClip;
                        if (clip != null)
                        {
                            string clipPath = AssetDatabase.GetAssetPath(clip);
                            string clipGuid = AssetDatabase.AssetPathToGUID(clipPath);
                            
                            report.AppendLine($"4. Which AnimationClip is assigned? {clip.name}");
                            report.AppendLine($"5. Does the AnimationClip asset actually exist? {(!string.IsNullOrEmpty(clipPath) ? "YES" : "NO")}");
                            report.AppendLine($"   Clip GUID: {clipGuid}");
                            
                            if (!string.IsNullOrEmpty(clipPath))
                            {
                                ModelImporter importer = AssetImporter.GetAtPath(clipPath) as ModelImporter;
                                if (importer != null)
                                {
                                    report.AppendLine($"6. Is the clip imported correctly? YES");
                                    report.AppendLine($"7. Is the clip Humanoid or Generic? {importer.animationType}");
                                }
                                else
                                {
                                    report.AppendLine($"6. Is the clip imported correctly? UNKNOWN (Not a Model, maybe native .anim)");
                                    report.AppendLine($"7. Is the clip Humanoid or Generic? N/A (.anim format)");
                                }
                            }
                        }
                        else
                        {
                            report.AppendLine($"4. Which AnimationClip is assigned? BLENDTREE OR OTHER");
                            BlendTree bt = state.motion as BlendTree;
                            if (bt != null)
                            {
                                report.AppendLine($"20. Is the state using a missing or invalid BlendTree? BlendTree Found, {bt.children.Length} children");
                            }
                        }
                    }
                    else
                    {
                        report.AppendLine($"4. Which AnimationClip is assigned? NONE");
                    }

                    if (runtimeAnimator != null && runtimeAnimator.avatar != null)
                    {
                        report.AppendLine($"8. Is the avatar Humanoid or Generic? {(runtimeAnimator.avatar.isHuman ? "Humanoid" : "Generic")}");
                        if (motionAssigned && state.motion is AnimationClip)
                        {
                            string clipPath = AssetDatabase.GetAssetPath(state.motion);
                            ModelImporter importer = AssetImporter.GetAtPath(clipPath) as ModelImporter;
                            if (importer != null)
                            {
                                bool compat = (runtimeAnimator.avatar.isHuman && importer.animationType == ModelImporterAnimationType.Human) ||
                                              (!runtimeAnimator.avatar.isHuman && importer.animationType == ModelImporterAnimationType.Generic);
                                report.AppendLine($"9. Are they compatible? {(compat ? "YES" : "NO")}");
                            }
                            else
                            {
                                report.AppendLine($"9. Are they compatible? ASSUMED YES (.anim file)");
                            }
                        }
                    }

                    // Runtime checks
                    if (runtimeAnimator != null)
                    {
                        // Check if we are currently transitioning to or in this state
                        int layerIndex = -1;
                        for(int i=0; i<runtimeAnimator.layerCount; i++)
                        {
                            if (runtimeAnimator.GetLayerName(i) == layer.name)
                            {
                                layerIndex = i; break;
                            }
                        }

                        if (layerIndex != -1)
                        {
                            report.AppendLine($"10-13. Runtime state checks require active frame analysis. Current state on layer {layer.name}:");
                            var currState = runtimeAnimator.GetCurrentAnimatorStateInfo(layerIndex);
                            var currTrans = runtimeAnimator.GetAnimatorTransitionInfo(layerIndex);
                            
                            report.AppendLine($"   Current State Hash: {currState.shortNameHash} (Length: {currState.length})");
                            report.AppendLine($"   In Transition: {runtimeAnimator.IsInTransition(layerIndex)}");
                            
                            float layerWeight = runtimeAnimator.GetLayerWeight(layerIndex);
                            report.AppendLine($"14. Is another layer overriding it? (Layer weight: {layerWeight})");
                            
                            bool hasMask = layer.avatarMask != null;
                            report.AppendLine($"15. Is an Avatar Mask suppressing it? {(hasMask ? "YES (" + layer.avatarMask.name + ")" : "NO")}");
                            
                            report.AppendLine($"16. Is Root Motion moving the avatar downward? Runtime applyRootMotion={runtimeAnimator.applyRootMotion}");
                        }
                    }
                    else
                    {
                        report.AppendLine($"10-16. Runtime Checks: NOT IN PLAY MODE");
                        report.AppendLine($"   Layer weight (Default): {layer.defaultWeight}");
                        bool hasMask = layer.avatarMask != null;
                        report.AppendLine($"15. Is an Avatar Mask suppressing it? {(hasMask ? "YES (" + layer.avatarMask.name + ")" : "NO")}");
                    }

                    report.AppendLine($"17. Is Write Defaults causing the pose to freeze? {(state.writeDefaultValues ? "YES (True)" : "NO (False)")}");
                    report.AppendLine($"18. Is the state's Speed set to 0? {(state.speed == 0 ? "YES" : "NO (Speed=" + state.speed + ")")}");
                    report.AppendLine($"19. Is Time Parameter enabled incorrectly? {(state.timeParameterActive ? "YES (Parameter: " + state.timeParameter + ")" : "NO")}");

                }
            }

            File.WriteAllText(reportPath, report.ToString());
            Debug.Log($"[DeepForensic] Deep Audit Complete! Report saved to {reportPath}");
        }
    }
}
