using System;
using System.IO;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class VivyRuntimeAnimationBuilder : MonoBehaviour
{
    private string interchangeDir = "d:/Vivy/shared/interchange";
    private Animator _animator;
    private AnimatorOverrideController _overrideController;
    private VivyWebSocketClient _wsClient;

    void Start()
    {
        _animator = GetComponent<Animator>();
        _wsClient = GetComponent<VivyWebSocketClient>();
        StartCoroutine(PollForPendingAnimations());
    }

    private IEnumerator PollForPendingAnimations()
    {
        while (true)
        {
            string pendingFile = Path.Combine(interchangeDir, "pending_anim.json");
            if (File.Exists(pendingFile))
            {
                Debug.Log($"[VivyRuntimeAnimationBuilder] Found pending animation at {pendingFile}");
                yield return ProcessPendingAnimation(pendingFile);
            }
            yield return new WaitForSeconds(1.0f);
        }
    }

    private IEnumerator ProcessPendingAnimation(string filePath)
    {
        string jsonContent = "";
        try
        {
            jsonContent = File.ReadAllText(filePath);
        }
        catch (Exception e)
        {
            Debug.LogWarning($"[VivyRuntimeAnimationBuilder] Failed to read pending anim: {e.Message}");
            yield break;
        }

        // Clean up the pending file so we don't process it again
        try
        {
            File.Delete(filePath);
        }
        catch { }

        // Parse JSON using JsonUtility
        PendingAnimData animData = null;
        try
        {
            animData = JsonUtility.FromJson<PendingAnimData>(jsonContent);
        }
        catch (Exception ex)
        {
            Debug.LogWarning($"[VivyRuntimeAnimationBuilder] JSON Parse failed: {ex.Message}");
        }

        string animId = (animData != null && !string.IsNullOrEmpty(animData.id)) ? animData.id : "AutoAnim";
        Debug.Log($"[VivyRuntimeAnimationBuilder] Constructing AnimationClip for {animId}...");

        AnimationClip clip = new AnimationClip();
        clip.name = animId;

        // Build true AnimationCurves if data exists
        if (animData != null && animData.frames != null && animData.frames.Length > 0 && _animator != null && _animator.IsValidAndPlaying())
        {
            bool isUpstreamFailure = false;
            
            // Check variance in JSON data first
            if (animData.frames.Length > 1 && animData.frames[0].bones != null && animData.frames[0].bones.Length > 0)
            {
                foreach (var firstFrameBone in animData.frames[0].bones)
                {
                    bool boneHasVariance = false;
                    for (int i = 1; i < animData.frames.Length; i++)
                    {
                        var curBone = Array.Find(animData.frames[i].bones, b => b.name == firstFrameBone.name);
                        if (curBone != null)
                        {
                            if (Mathf.Abs(curBone.x - firstFrameBone.x) > 0.0001f ||
                                Mathf.Abs(curBone.y - firstFrameBone.y) > 0.0001f ||
                                Mathf.Abs(curBone.z - firstFrameBone.z) > 0.0001f ||
                                Mathf.Abs(curBone.w - firstFrameBone.w) > 0.0001f)
                            {
                                boneHasVariance = true;
                                break;
                            }
                        }
                    }

                    if (!boneHasVariance)
                    {
                        if (Mathf.Abs(firstFrameBone.x) < 0.001f && Mathf.Abs(firstFrameBone.y) < 0.001f && 
                            Mathf.Abs(firstFrameBone.z) < 0.001f && Mathf.Abs(Mathf.Abs(firstFrameBone.w) - 1f) < 0.001f)
                        {
                            Debug.LogError($"[VivyRuntimeAnimationBuilder] ABORT: Bone {firstFrameBone.name} contains only default/placeholder transforms. Upstream motion reconstruction failure detected.");
                            isUpstreamFailure = true;
                            break;
                        }
                    }
                }
            }

            if (isUpstreamFailure)
            {
                Debug.LogError("[VivyRuntimeAnimationBuilder] Generating AnimationClip aborted due to upstream motion reconstruction failure.");
                yield break;
            }

            Vector3 origPos = _animator.transform.position;
            Quaternion origRot = _animator.transform.rotation;
            _animator.transform.position = Vector3.zero;
            _animator.transform.rotation = Quaternion.identity;

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

            float fps = animData.fps > 0 ? animData.fps : 30f;
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
                                boneTransform.localRotation = new Quaternion(bone.x, bone.y, bone.z, bone.w);
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
            
            Debug.Log($"[VivyRuntimeAnimationBuilder] Baked {HumanTrait.MuscleCount} muscle curves into AnimationClip!");

            // [RUNTIME VALIDATION] Dump Telemetry
            try {
                var telemetry = new List<string>();
                telemetry.Add("{\"muscles\": [");
                for (int i = 0; i < animData.frames.Length; i++)
                {
                    List<string> frameData = new List<string>();
                    for (int m = 0; m < HumanTrait.MuscleCount; m++)
                    {
                        float val = muscleCurves[m][i].value;
                        string mName = HumanTrait.MuscleName[m];
                        frameData.Add($"\"{mName}\": {val}");
                    }
                    telemetry.Add("{" + string.Join(",", frameData) + "}" + (i < animData.frames.Length - 1 ? "," : ""));
                }
                telemetry.Add("]}");
                File.WriteAllText(Path.Combine(interchangeDir, $"telemetry_{animId}.json"), string.Join("\n", telemetry));
            } catch (Exception ex) {
                Debug.LogWarning("Failed to write telemetry: " + ex.Message);
            }

        }
        else
        {
            Debug.LogError("[VivyRuntimeAnimationBuilder] ABORT: Clip contains empty curves. Upstream motion reconstruction failure detected.");
            yield break;
        }
        
        // To ensure the clip loops for the live preview
        clip.wrapMode = WrapMode.Loop;

        // Inject it into the Animator using an Override Controller
        if (_animator != null && _animator.IsValidAndPlaying())
        {
            if (_overrideController == null)
            {
                _overrideController = new AnimatorOverrideController(_animator.runtimeAnimatorController);
            }
            
            // We will override the "Idle0" state which is a known base layer state
            // Since Unity 2020, we override clips by name or by reference.
            // We will find the clip named "Idle0" (or fallback to the first clip)
            AnimationClip clipToOverride = null;
            foreach (var ac in _animator.runtimeAnimatorController.animationClips)
            {
                if (ac.name == "Idle0" || ac.name == "Neutral")
                {
                    clipToOverride = ac;
                    break;
                }
            }
            
            if (clipToOverride == null && _animator.runtimeAnimatorController.animationClips.Length > 0)
            {
                clipToOverride = _animator.runtimeAnimatorController.animationClips[0];
            }

            if (clipToOverride != null)
            {
                _overrideController[clipToOverride.name] = clip;
                _animator.runtimeAnimatorController = _overrideController;
                _animator.Play("Idle0", 0, 0f);
                Debug.Log($"[VivyRuntimeAnimationBuilder] Successfully injected {animId} into Animator and started playback!");
            }
        }

        // Write the ACK file for Python to pick up
        string ackFile = Path.Combine(interchangeDir, $"ack_{animId}.json");
        try
        {
            File.WriteAllText(ackFile, "{\"status\": \"verification_success\"}");
            Debug.Log($"[VivyRuntimeAnimationBuilder] Wrote ACK file to {ackFile}");
        }
        catch (Exception e)
        {
            Debug.LogError($"[VivyRuntimeAnimationBuilder] Failed to write ACK file: {e.Message}");
        }
    }

    private string GetBonePath(Transform root, Transform target)
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
}

[Serializable]
public class PendingAnimData
{
    public string id;
    public float fps;
    public PendingAnimFrame[] frames;
}

[Serializable]
public class PendingAnimFrame
{
    public PendingAnimBone[] bones;
}

[Serializable]
public class PendingAnimBone
{
    public string name;
    public float x;
    public float y;
    public float z;
    public float w;
}
