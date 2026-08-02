using UnityEngine;
using UnityEditor;
using UnityEditor.Callbacks;
using System.IO;
using System.Text.RegularExpressions;
using System;
using System.Reflection;

namespace VivyAI.Editor
{
    [InitializeOnLoad]
    public class VivyProceduralCompiler
    {
        private static string sourceFile = "d:/Vivy/shared/procedural_anim_code.cs";
        private static string generatedDir = "Assets/MATE ENGINE - Scripts/Generated";
        private static string attachFlagFile = "d:/Vivy/shared/interchange/procedural_pending_attach.txt";

        private static double lastCheckTime;
        private static DateTime lastWriteTime = DateTime.MinValue;

        static VivyProceduralCompiler()
        {
            EditorApplication.update += OnEditorUpdate;
            
            // If we are starting up (e.g. after domain reload), check if we need to attach a script
            EditorApplication.delayCall += CheckPendingAttach;
        }

        private static void OnEditorUpdate()
        {
            if (EditorApplication.timeSinceStartup - lastCheckTime < 1.0) return;
            lastCheckTime = EditorApplication.timeSinceStartup;

            if (File.Exists(sourceFile))
            {
                Debug.Log("[VivyProceduralCompiler] Detected procedural_anim_code.cs update! Initiating auto-compile...");
                ProcessProceduralCode();
            }
        }

        private static void ProcessProceduralCode()
        {
            try
            {
                string code = File.ReadAllText(sourceFile);
                File.Delete(sourceFile); // Ensure we don't process it again in a loop
                
                if (string.IsNullOrWhiteSpace(code)) return;

                // Auto-repair: Convert Update to LateUpdate to prevent Animator from overwriting procedural rotations (Step 8/9 Fix)
                code = Regex.Replace(code, @"\bvoid\s+Update\s*\(", "void LateUpdate(");

                // Extract class name
                Match match = Regex.Match(code, @"class\s+([A-Za-z0-9_]+)\s*:");
                if (!match.Success)
                {
                    Debug.LogError("[VivyProceduralCompiler] Could not find a class inheriting from MonoBehaviour in the procedural code.");
                    return;
                }
                
                string className = match.Groups[1].Value;

                if (!Directory.Exists(generatedDir))
                {
                    Directory.CreateDirectory(generatedDir);
                }

                // Delete all other scripts in the Generated folder to prevent conflicts if class names change
                string[] oldFiles = Directory.GetFiles(generatedDir, "*.cs");
                foreach (var f in oldFiles)
                {
                    File.Delete(f);
                }

                string targetPath = Path.Combine(generatedDir, className + ".cs");
                File.WriteAllText(targetPath, code);

                // Write the flag so we know what to attach after reload
                File.WriteAllText(attachFlagFile, className);

                Debug.Log($"[VivyProceduralCompiler] Wrote {className}.cs to {generatedDir}. Triggering AssetDatabase.Refresh()...");
                
                // Trigger Unity recompile
                AssetDatabase.Refresh();
            }
            catch (Exception ex)
            {
                Debug.LogError($"[VivyProceduralCompiler] Error processing procedural code: {ex.Message}");
            }
        }

        [DidReloadScripts]
        private static void OnScriptsReloaded()
        {
            CheckPendingAttach();
        }

        private static void CheckPendingAttach()
        {
            if (File.Exists(attachFlagFile))
            {
                try
                {
                    string className = File.ReadAllText(attachFlagFile).Trim();
                    File.Delete(attachFlagFile); // Clean up immediately

                    if (!string.IsNullOrEmpty(className))
                    {
                        EditorApplication.delayCall += () => AttachComponentToAvatar(className);
                    }
                }
                catch (Exception e)
                {
                    Debug.LogError($"[VivyProceduralCompiler] Failed to read attach flag: {e.Message}");
                }
            }
        }

        private static void AttachComponentToAvatar(string className)
        {
            if (!Application.isPlaying)
            {
                Debug.LogWarning($"[VivyProceduralCompiler] Unity is not in Play Mode. {className} was compiled but will not be attached.");
                return;
            }

            Animator animator = UnityEngine.Object.FindFirstObjectByType<Animator>();
            if (animator == null)
            {
                Debug.LogError("[VivyProceduralCompiler] No Animator found in scene to attach procedural animation to.");
                return;
            }

            GameObject avatar = animator.gameObject;

            // Search for the type across all assemblies
            Type componentType = null;
            foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                componentType = assembly.GetType(className);
                if (componentType != null)
                {
                    break;
                }
            }

            if (componentType == null)
            {
                Debug.LogError($"[VivyProceduralCompiler] Could not find Type '{className}' after reload.");
                return;
            }

            // Remove previous instances of this component if any exist
            var existing = avatar.GetComponents(componentType);
            foreach (var oldComp in existing)
            {
                UnityEngine.Object.Destroy(oldComp);
            }

            // Attach new component
            var newComp = avatar.AddComponent(componentType);

            // Auto-assign humanoid bones to Transform fields based on loose name matching
            if (animator.isHuman)
            {
                foreach (FieldInfo field in componentType.GetFields(BindingFlags.Public | BindingFlags.Instance))
                {
                    if (field.FieldType == typeof(Transform))
                    {
                        string fn = field.Name.ToLower();
                        HumanBodyBones? targetBone = null;
                        
                        if (fn.Contains("hip")) targetBone = HumanBodyBones.Hips;
                        else if (fn.Contains("spine")) targetBone = HumanBodyBones.Spine;
                        else if (fn.Contains("chest")) targetBone = HumanBodyBones.Chest;
                        else if (fn.Contains("head")) targetBone = HumanBodyBones.Head;
                        else if (fn.Contains("neck")) targetBone = HumanBodyBones.Neck;
                        else if (fn.Contains("leftarm") || fn.Contains("leftupperarm")) targetBone = HumanBodyBones.LeftUpperArm;
                        else if (fn.Contains("rightarm") || fn.Contains("rightupperarm")) targetBone = HumanBodyBones.RightUpperArm;
                        else if (fn.Contains("leftforearm") || fn.Contains("leftlowerarm")) targetBone = HumanBodyBones.LeftLowerArm;
                        else if (fn.Contains("rightforearm") || fn.Contains("rightlowerarm")) targetBone = HumanBodyBones.RightLowerArm;
                        else if (fn.Contains("lefthand")) targetBone = HumanBodyBones.LeftHand;
                        else if (fn.Contains("righthand")) targetBone = HumanBodyBones.RightHand;
                        else if (fn.Contains("leftleg") || fn.Contains("leftupperleg")) targetBone = HumanBodyBones.LeftUpperLeg;
                        else if (fn.Contains("rightleg") || fn.Contains("rightupperleg")) targetBone = HumanBodyBones.RightUpperLeg;
                        else if (fn.Contains("leftfoot")) targetBone = HumanBodyBones.LeftFoot;
                        else if (fn.Contains("rightfoot")) targetBone = HumanBodyBones.RightFoot;

                        if (targetBone.HasValue)
                        {
                            Transform boneTransform = animator.GetBoneTransform(targetBone.Value);
                            if (boneTransform != null)
                            {
                                field.SetValue(newComp, boneTransform);
                                Debug.Log($"[VivyProceduralCompiler] Auto-assigned {field.Name} to {targetBone.Value}");
                            }
                        }
                    }
                }
            }

            Debug.Log($"[VivyProceduralCompiler] Successfully attached {className} to {avatar.name} in Play Mode!");
        }
    }
}
