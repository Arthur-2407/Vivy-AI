using UnityEngine;
using UnityEditor;
using UnityEditor.Animations;
using System.IO;
using System.Collections.Generic;
using System.Text;
using System;

namespace VivyAI.Editor
{
    [InitializeOnLoad]
    public class VivyAutoAssetBuilder
    {
        private static string interchangeDir = "d:/Vivy/shared/interchange";
        private static string pendingFile = "d:/Vivy/shared/interchange/pending_anim.json";
        private static string registryFile = "d:/Vivy/vivy_animation_registry.json";
        private static string generatedAnimDir = "Assets/MATE ENGINE - Animations/Generated";
        private static string controllerPath = "Assets/MATE ENGINE - Animations/AvatarAnimatorController.controller";

        private static double lastCheckTime;

        static VivyAutoAssetBuilder()
        {
            EditorApplication.update += OnEditorUpdate;
            if (!Directory.Exists(interchangeDir)) Directory.CreateDirectory(interchangeDir);
            if (!Directory.Exists(generatedAnimDir)) Directory.CreateDirectory(generatedAnimDir);
        }

        private static void OnEditorUpdate()
        {
            // Throttle check to every 1 second
            if (EditorApplication.timeSinceStartup - lastCheckTime < 1.0) return;
            lastCheckTime = EditorApplication.timeSinceStartup;

            if (File.Exists(pendingFile))
            {
                Debug.Log("[VivyAutoAssetBuilder] Detected pending_anim.json! Building asset...");
                ProcessPendingAnimation();
            }
        }

        private static void ProcessPendingAnimation()
        {
            try
            {
                string json = File.ReadAllText(pendingFile);
                PendingAnimData animData = null;
                try
                {
                    animData = JsonUtility.FromJson<PendingAnimData>(json);
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"[VivyAutoAssetBuilder] JSON Parse failed: {ex.Message}");
                }

                if (animData == null)
                {
                    Debug.LogError("[VivyAutoAssetBuilder] Failed to parse pending_anim.json");
                    File.Delete(pendingFile);
                    return;
                }

                string animId = !string.IsNullOrEmpty(animData.id) ? animData.id : "AutoAnim_Unknown";
                float fps = animData.fps > 0 ? animData.fps : 30f;
                float duration = (animData.frames != null && animData.frames.Length > 0) ? animData.frames.Length / fps : 5.0f;

                // 1. Create Animation Clip
                AnimationClip clip = new AnimationClip();
                clip.name = animId;
                clip.frameRate = fps;

                Animator _animator = UnityEngine.Object.FindFirstObjectByType<Animator>();
                if (_animator == null)
                {
                    Debug.LogError("[VivyAutoAssetBuilder] No Animator found in scene to map bone paths. Aborting.");
                    return;
                }

                if (animData.frames != null && animData.frames.Length > 0)
                {
                    Vector3 origPos = _animator.transform.position;
                    Quaternion origRot = _animator.transform.rotation;
                    _animator.transform.position = Vector3.zero;
                    _animator.transform.rotation = Quaternion.identity;

                    // [PHASE 3 FIX] Cache the avatar's native bind-pose local rotations
                    Dictionary<HumanBodyBones, Quaternion> initialLocalRotations = new Dictionary<HumanBodyBones, Quaternion>();
                    foreach (HumanBodyBones boneType in Enum.GetValues(typeof(HumanBodyBones)))
                    {
                        if (boneType != HumanBodyBones.LastBone)
                        {
                            Transform bTransform = _animator.GetBoneTransform(boneType);
                            if (bTransform != null)
                            {
                                initialLocalRotations[boneType] = bTransform.localRotation;
                            }
                        }
                    }

                    HumanPoseHandler poseHandler = new HumanPoseHandler(_animator.avatar, _animator.transform);
                    HumanPose humanPose = new HumanPose();
                    
                    Dictionary<int, List<Keyframe>> muscleCurves = new Dictionary<int, List<Keyframe>>();
                    for (int m = 0; m < HumanTrait.MuscleCount; m++) muscleCurves[m] = new List<Keyframe>();

                    List<Keyframe> rootPosX = new List<Keyframe>();
                    List<Keyframe> rootPosY = new List<Keyframe>();
                    List<Keyframe> rootPosZ = new List<Keyframe>();
                    List<Keyframe> rootRotX = new List<Keyframe>();
                    List<Keyframe> rootRotY = new List<Keyframe>();
                    List<Keyframe> rootRotZ = new List<Keyframe>();
                    List<Keyframe> rootRotW = new List<Keyframe>();
                    for (int i = 0; i < animData.frames.Length; i++)
                    {
                        float time = i / fps;
                        
                        if (animData.frames[i].bones != null)
                        {
                            foreach (var bone in animData.frames[i].bones)
                            {
                                if (Enum.TryParse<HumanBodyBones>(bone.name, out HumanBodyBones boneType))
                                {
                                    Transform boneTransform = _animator.GetBoneTransform(boneType);
                                    if (boneTransform != null)
                                    {
                                        if (initialLocalRotations.TryGetValue(boneType, out Quaternion initialRot))
                                        {
                                            // Left-Multiply to apply the Python offset in the Parent's coordinate space
                                            boneTransform.localRotation = new Quaternion(bone.x, bone.y, bone.z, bone.w) * initialRot;
                                        }
                                    }
                                }
                            }
                        }

                        poseHandler.GetHumanPose(ref humanPose);

                        for (int m = 0; m < HumanTrait.MuscleCount; m++)
                        {
                            muscleCurves[m].Add(new Keyframe(time, humanPose.muscles[m]));
                        }
                        rootPosX.Add(new Keyframe(time, humanPose.bodyPosition.x));
                        rootPosY.Add(new Keyframe(time, humanPose.bodyPosition.y));
                        rootPosZ.Add(new Keyframe(time, humanPose.bodyPosition.z));
                        rootRotX.Add(new Keyframe(time, humanPose.bodyRotation.x));
                        rootRotY.Add(new Keyframe(time, humanPose.bodyRotation.y));
                        rootRotZ.Add(new Keyframe(time, humanPose.bodyRotation.z));
                        rootRotW.Add(new Keyframe(time, humanPose.bodyRotation.w));
                    }

                    _animator.transform.position = origPos;
                    _animator.transform.rotation = origRot;

                    for (int m = 0; m < HumanTrait.MuscleCount; m++)
                    {
                        string muscleName = HumanTrait.MuscleName[m];
                        clip.SetCurve("", typeof(Animator), muscleName, new AnimationCurve(muscleCurves[m].ToArray()));
                    }
                    
                    clip.SetCurve("", typeof(Animator), "RootT.x", new AnimationCurve(rootPosX.ToArray()));
                    clip.SetCurve("", typeof(Animator), "RootT.y", new AnimationCurve(rootPosY.ToArray()));
                    clip.SetCurve("", typeof(Animator), "RootT.z", new AnimationCurve(rootPosZ.ToArray()));
                    clip.SetCurve("", typeof(Animator), "RootQ.x", new AnimationCurve(rootRotX.ToArray()));
                    clip.SetCurve("", typeof(Animator), "RootQ.y", new AnimationCurve(rootRotY.ToArray()));
                    clip.SetCurve("", typeof(Animator), "RootQ.z", new AnimationCurve(rootRotZ.ToArray()));
                    clip.SetCurve("", typeof(Animator), "RootQ.w", new AnimationCurve(rootRotW.ToArray()));
                }

                string clipPath = $"{generatedAnimDir}/{animId}.anim";
                AssetDatabase.CreateAsset(clip, clipPath);
                AssetDatabase.SaveAssets();

                // Phase 12 Mandatory Acceptance Gate
                bool isApproved = EditorUtility.DisplayDialog(
                    "MANDATORY ACCEPTANCE GATE",
                    $"The AnimationClip '{animId}' has been generated at:\n{clipPath}\n\n" +
                    "INSTRUCTIONS:\n" +
                    "1. Open the Unity Animation Window (Ctrl+6).\n" +
                    "2. Select the generated .anim file.\n" +
                    "3. Verify that each major humanoid bone contains non-empty, time-varying curves derived from the motion reconstruction.\n\n" +
                    "If the clip contains empty curves or placeholder values, click REJECT to classify this as an upstream defect.\n" +
                    "If the curves are valid, click APPROVE to register the animation.",
                    "APPROVE (Valid Curves)", "REJECT (Empty/Placeholder)");

                if (!isApproved)
                {
                    Debug.LogError($"[VivyAutoAssetBuilder] User REJECTED animation {animId} after manual inspection.");
                    File.Delete(pendingFile);
                    AssetDatabase.DeleteAsset(clipPath);
                    string failedAckFile = $"{interchangeDir}/ack_{animId}.json";
                    File.WriteAllText(failedAckFile, $"{{\"status\":\"rejected\",\"id\":\"{animId}\"}}");
                    return;
                }

                // 2. Wire into Animator Controller
                AnimatorController controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath);
                if (controller != null)
                {
                    // Ensure Trigger parameter exists
                    bool hasTrigger = false;
                    foreach (var p in controller.parameters) if (p.name == animId) hasTrigger = true;
                    if (!hasTrigger) controller.AddParameter(animId, AnimatorControllerParameterType.Trigger);

                    // Ensure State exists
                    AnimatorStateMachine rootSM = controller.layers[0].stateMachine;
                    AnimatorState targetState = null;
                    foreach (var s in rootSM.states) if (s.state.name == animId) { targetState = s.state; break; }
                    
                    if (targetState == null)
                    {
                        targetState = rootSM.AddState(animId);
                    }
                    
                    targetState.motion = clip;

                    // Ensure Transition exists
                    bool hasTransition = false;
                    foreach (var t in rootSM.anyStateTransitions)
                    {
                        if (t.destinationState == targetState) hasTransition = true;
                    }

                    if (!hasTransition)
                    {
                        var transition = rootSM.AddAnyStateTransition(targetState);
                        transition.AddCondition(AnimatorConditionMode.If, 0, animId);
                        transition.hasExitTime = false;
                        transition.duration = 0.25f;
                    }

                    EditorUtility.SetDirty(controller);
                    AssetDatabase.SaveAssets();
                    Debug.Log($"[VivyAutoAssetBuilder] Wired {animId} into AnimatorController successfully.");
                }

                // 3. Update Registry
                if (File.Exists(registryFile))
                {
                    string regJson = File.ReadAllText(registryFile);
                    var regRoot = MiniJSON.Parse(regJson) as Dictionary<string, object>;
                    if (regRoot != null && regRoot.ContainsKey("categories"))
                    {
                        var categories = regRoot["categories"] as Dictionary<string, object>;
                        if (!categories.ContainsKey("Generated")) categories["Generated"] = new List<object>();
                        var genList = categories["Generated"] as List<object>;
                        
                        var newEntry = new Dictionary<string, object>
                        {
                            { "id", animId },
                            { "trigger", animId },
                            { "layer", "Base Layer" },
                            { "priority", 2 },
                            { "duration", duration },
                            { "auto_generated", true }
                        };
                        genList.Add(newEntry);
                        
                        string newRegJson = SerializeJSON(regRoot);
                        File.WriteAllText(registryFile, newRegJson);
                        Debug.Log($"[VivyAutoAssetBuilder] Registered {animId} in JSON Registry.");
                    }
                }

                // 4. Send ACK and cleanup
                File.Delete(pendingFile);
                string ackFile = $"{interchangeDir}/ack_{animId}.json";
                File.WriteAllText(ackFile, $"{{\"status\":\"success\",\"id\":\"{animId}\"}}");
                Debug.Log($"[VivyAutoAssetBuilder] Sent ACK to Python pipeline.");
            }
            catch (Exception ex)
            {
                Debug.LogError($"[VivyAutoAssetBuilder] Error building asset: {ex.Message}\n{ex.StackTrace}");
                if (File.Exists(pendingFile)) File.Delete(pendingFile); // prevent loop
            }
        }

        private static string GetBonePath(Transform root, Transform target)
        {
            if (target == root) return "";
            string path = target.name;
            while (target.parent != null && target.parent != root)
            {
                target = target.parent;
                path = target.name + "/" + path;
            }
            return path;
        }

        // Simple JSON Serialization for Registry
        private static string SerializeJSON(Dictionary<string, object> dict)
        {
            StringBuilder sb = new StringBuilder();
            SerializeDict(dict, sb, 0);
            return sb.ToString();
        }
        private static void SerializeDict(Dictionary<string, object> dict, StringBuilder sb, int indent)
        {
            sb.AppendLine("{");
            int count = 0;
            foreach (var kvp in dict)
            {
                sb.Append(new string(' ', (indent + 1) * 2));
                sb.Append($"\"{kvp.Key}\": ");
                SerializeVal(kvp.Value, sb, indent + 1);
                if (++count < dict.Count) sb.AppendLine(","); else sb.AppendLine();
            }
            sb.Append(new string(' ', indent * 2)).Append("}");
        }
        private static void SerializeList(List<object> list, StringBuilder sb, int indent)
        {
            sb.AppendLine("[");
            int count = 0;
            foreach (var val in list)
            {
                sb.Append(new string(' ', (indent + 1) * 2));
                SerializeVal(val, sb, indent + 1);
                if (++count < list.Count) sb.AppendLine(","); else sb.AppendLine();
            }
            sb.Append(new string(' ', indent * 2)).Append("]");
        }
        private static void SerializeVal(object val, StringBuilder sb, int indent)
        {
            if (val == null) sb.Append("null");
            else if (val is string s) sb.Append($"\"{s}\"");
            else if (val is bool b) sb.Append(b ? "true" : "false");
            else if (val is int || val is float || val is double) sb.Append(val.ToString());
            else if (val is Dictionary<string, object> d) SerializeDict(d, sb, indent);
            else if (val is List<object> l) SerializeList(l, sb, indent);
            else sb.Append($"\"{val}\"");
        }

        public static class MiniJSON
        {
            public static object Parse(string json)
            {
                if (string.IsNullOrEmpty(json)) return null; int index = 0; return ParseValue(json, ref index);
            }
            private static object ParseValue(string json, ref int index)
            {
                SkipWhitespace(json, ref index); if (index >= json.Length) return null;
                char c = json[index];
                if (c == '{') return ParseObject(json, ref index);
                if (c == '[') return ParseArray(json, ref index);
                if (c == '"') return ParseString(json, ref index);
                if (c == 't') { index += 4; return true; }
                if (c == 'f') { index += 5; return false; }
                if (c == 'n') { index += 4; return null; }
                return ParseNumber(json, ref index);
            }
            private static Dictionary<string, object> ParseObject(string json, ref int index)
            {
                var obj = new Dictionary<string, object>(); index++;
                while (index < json.Length) { SkipWhitespace(json, ref index); if (json[index] == '}') { index++; break; } string key = ParseString(json, ref index); SkipWhitespace(json, ref index); if (json[index] == ':') index++; object value = ParseValue(json, ref index); obj[key] = value; SkipWhitespace(json, ref index); if (json[index] == ',') index++; }
                return obj;
            }
            private static List<object> ParseArray(string json, ref int index)
            {
                var arr = new List<object>(); index++;
                while (index < json.Length) { SkipWhitespace(json, ref index); if (json[index] == ']') { index++; break; } arr.Add(ParseValue(json, ref index)); SkipWhitespace(json, ref index); if (json[index] == ',') index++; }
                return arr;
            }
            private static string ParseString(string json, ref int index)
            {
                index++; int start = index;
                while (index < json.Length) { if (json[index] == '"') break; if (json[index] == '\\') index++; index++; }
                string str = json.Substring(start, index - start); str = str.Replace("\\\"", "\""); index++; return str;
            }
            private static double ParseNumber(string json, ref int index)
            {
                int start = index; while (index < json.Length && (char.IsDigit(json[index]) || json[index] == '.' || json[index] == '-')) index++;
                double.TryParse(json.Substring(start, index - start), System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out double num);
                return num;
            }
            private static void SkipWhitespace(string json, ref int index) { while (index < json.Length && char.IsWhiteSpace(json[index])) index++; }
        }
    }
}
