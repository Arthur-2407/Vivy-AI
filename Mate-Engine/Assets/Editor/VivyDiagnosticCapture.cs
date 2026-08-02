using UnityEngine;
using UnityEditor;
using System.IO;
using System.Collections;
using System.Collections.Generic;
using System;
using System.Text;

namespace VivyAI.Editor
{
    [Serializable]
    public class DiagnosticTrigger
    {
        public string anim_id;
    }

    [InitializeOnLoad]
    public class VivyDiagnosticCapture
    {
        private static string interchangeDir = "d:/Vivy/shared/interchange";
        private static string triggerFile = "d:/Vivy/shared/interchange/diagnostic_trigger.json";
        private static string outputDump = "d:/Vivy/shared/interchange/diagnostic_unity_dump.json";
        private static string framesDir = "d:/Vivy/shared/interchange/diagnostic_frames";
        private static double lastCheckTime;

        static VivyDiagnosticCapture()
        {
            EditorApplication.update += OnEditorUpdate;
            if (!Directory.Exists(interchangeDir)) Directory.CreateDirectory(interchangeDir);
            if (!Directory.Exists(framesDir)) Directory.CreateDirectory(framesDir);
        }

        private static void OnEditorUpdate()
        {
            if (EditorApplication.timeSinceStartup - lastCheckTime < 1.0) return;
            lastCheckTime = EditorApplication.timeSinceStartup;

            if (File.Exists(triggerFile))
            {
                Debug.Log("[VivyDiagnosticCapture] Trigger found. Starting diagnostic capture...");
                ProcessDiagnostic();
            }
        }

        private static void ProcessDiagnostic()
        {
            try
            {
                string json = File.ReadAllText(triggerFile);
                File.Delete(triggerFile);
                
                DiagnosticTrigger triggerData = JsonUtility.FromJson<DiagnosticTrigger>(json);
                if (triggerData == null || string.IsNullOrEmpty(triggerData.anim_id))
                {
                    Debug.LogError("[VivyDiagnosticCapture] Invalid trigger data");
                    return;
                }

                string animId = triggerData.anim_id;
                string clipPath = $"Assets/MATE ENGINE - Animations/Generated/{animId}.anim";
                AnimationClip clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);

                if (clip == null)
                {
                    Debug.LogError($"[VivyDiagnosticCapture] Could not find animation clip at {clipPath}");
                    return;
                }

                Animator animator = UnityEngine.Object.FindFirstObjectByType<Animator>();
                if (animator == null)
                {
                    Debug.LogError("[VivyDiagnosticCapture] No Animator found in scene.");
                    return;
                }

                if (!Directory.Exists(framesDir)) Directory.CreateDirectory(framesDir);
                foreach (string f in Directory.GetFiles(framesDir)) File.Delete(f);

                float fps = clip.frameRate > 0 ? clip.frameRate : 30f;
                int frameCount = Mathf.FloorToInt(clip.length * fps);
                
                List<string> frameDumps = new List<string>();

                HumanBodyBones[] requiredBones = new HumanBodyBones[] {
                    HumanBodyBones.Hips, HumanBodyBones.Spine, HumanBodyBones.Chest,
                    HumanBodyBones.Neck, HumanBodyBones.Head,
                    HumanBodyBones.LeftUpperArm, HumanBodyBones.LeftLowerArm, HumanBodyBones.LeftHand,
                    HumanBodyBones.RightUpperArm, HumanBodyBones.RightLowerArm, HumanBodyBones.RightHand,
                    HumanBodyBones.LeftUpperLeg, HumanBodyBones.LeftLowerLeg, HumanBodyBones.LeftFoot,
                    HumanBodyBones.RightUpperLeg, HumanBodyBones.RightLowerLeg, HumanBodyBones.RightFoot
                };

                // Store original state
                Vector3 origPos = animator.transform.position;
                Quaternion origRot = animator.transform.rotation;
                
                animator.transform.position = Vector3.zero;
                animator.transform.rotation = Quaternion.identity;

                // Setup headless camera for screenshot capture
                Camera captureCam = new GameObject("DiagnosticCamera").AddComponent<Camera>();
                captureCam.transform.position = new Vector3(0, 1.2f, 2.5f);
                captureCam.transform.LookAt(new Vector3(0, 1.0f, 0)); // Look at torso
                RenderTexture rt = new RenderTexture(512, 512, 24);
                captureCam.targetTexture = rt;
                captureCam.clearFlags = CameraClearFlags.SolidColor;
                captureCam.backgroundColor = Color.gray;
                Texture2D tex = new Texture2D(512, 512, TextureFormat.RGB24, false);

                for (int i = 0; i < frameCount; i++)
                {
                    float time = i / fps;
                    
                    // Sample animation on the avatar
                    clip.SampleAnimation(animator.gameObject, time);
                    
                    List<string> boneJsonList = new List<string>();
                    foreach (var bone in requiredBones)
                    {
                        Transform t = animator.GetBoneTransform(bone);
                        if (t != null)
                        {
                            Vector3 pos = t.position;
                            Quaternion rot = t.rotation;
                            
                            string boneJson = $"\"{bone.ToString()}\": {{" +
                                $"\"position\": {{\"x\": {pos.x}, \"y\": {pos.y}, \"z\": {pos.z}}}, " +
                                $"\"rotation\": {{\"x\": {rot.x}, \"y\": {rot.y}, \"z\": {rot.z}, \"w\": {rot.w}}}" +
                            "}";
                            boneJsonList.Add(boneJson);
                        }
                    }
                    
                    frameDumps.Add("{" + string.Join(",", boneJsonList) + "}");
                    
                    // Render frame silently
                    captureCam.Render();
                    RenderTexture.active = rt;
                    tex.ReadPixels(new Rect(0, 0, 512, 512), 0, 0);
                    tex.Apply();
                    RenderTexture.active = null;
                    
                    byte[] pngBytes = tex.EncodeToPNG();
                    File.WriteAllBytes(Path.Combine(framesDir, $"frame_{i:D3}.png"), pngBytes);
                }

                string dumpJson = "{\"frames\": [" + string.Join(",", frameDumps) + "]}";
                File.WriteAllText(outputDump, dumpJson);
                
                // Cleanup headless capture
                UnityEngine.Object.DestroyImmediate(captureCam.gameObject);
                UnityEngine.Object.DestroyImmediate(rt);
                UnityEngine.Object.DestroyImmediate(tex);
                
                // Restore
                animator.transform.position = origPos;
                animator.transform.rotation = origRot;
                clip.SampleAnimation(animator.gameObject, 0);

                Debug.Log("[VivyDiagnosticCapture] Diagnostic capture complete.");
            }
            catch (Exception ex)
            {
                Debug.LogError($"[VivyDiagnosticCapture] Error: {ex.Message}\n{ex.StackTrace}");
            }
        }
    }
}
