using System;
using System.Collections.Generic;
using UnityEngine;
using UniVRM10;

[Serializable]
public class TrackingPermission
{
    public string stateOrParameterName;
    public bool isParameter;
    public bool allowHead = true, allowSpine = true, allowEye = true;
}

[RequireComponent(typeof(Animator))]
public class AvatarMouseTracking : MonoBehaviour
{
    [Header("Mouse Tracking Settings")]
    public bool enableMouseTracking = true;
    public List<TrackingPermission> trackingPermissions = new();

    [Range(0f, 90f)] public float headYawLimit = 45f, headPitchLimit = 30f;
    [Range(1f, 20f)] public float headSmoothness = 10f;
    [Range(-90f, 90f)] public float spineMinRotation = -15f, spineMaxRotation = 15f;
    [Range(1f, 50f)] public float spineSmoothness = 25f;
    [Range(1f, 10f)] public float spineFadeSpeed = 5f;
    [Range(0f, 90f)] public float eyeYawLimit = 12f, eyePitchLimit = 12f;
    [Range(1f, 20f)] public float eyeSmoothness = 10f;
    [Range(0f, 1f)] public float headBlend = 1f, spineBlend = 1f, eyeBlend = 1f;

    Animator animator;
    Camera mainCam;

    Transform headBone, spineBone, chestBone, upperChestBone;
    Transform leftEyeBone, rightEyeBone, headDriver, spineDriver;
    Transform leftEyeDriver, rightEyeDriver, eyeCenter, vrmLookAtTarget;

    Quaternion headInitRot, spineInitRot;
    float spineTrackingWeight;

    Vrm10Instance vrm10;
    int currStateHash, nextStateHash;

    // =====================================================
    // VIVY LOOKAT OVERRIDE
    // When active, replaces Input.mousePosition with a Vivy-provided
    // screen position for a configurable duration, then returns to
    // normal mouse tracking automatically.
    // Called by VivyWebSocketClient.HandleLookAt().
    // All fields are private — public surface is SetLookAtOverride only.
    // =====================================================
    private bool    _vivyOverrideActive;
    private Vector2 _vivyOverrideScreen;
    private Vector2 _smoothOverrideScreen;
    private float   _vivyOverrideExpiry;

    // Procedural Micro-Saccade Animation
    private Vector2 _saccadeOffset = Vector2.zero;
    private float   _nextSaccadeTime = 0f;

    private void UpdateMicroSaccades(Camera cam)
    {
        if (Time.time >= _nextSaccadeTime)
        {
            _nextSaccadeTime = Time.time + UnityEngine.Random.Range(1.5f, 4.0f);
            // Subtle saccade shift: +/- 1.5% of screen width/height for lifelike eye movement
            _saccadeOffset = new Vector2(
                UnityEngine.Random.Range(-0.015f, 0.015f) * cam.pixelWidth,
                UnityEngine.Random.Range(-0.01f, 0.01f) * cam.pixelHeight
            );
        }
    }

    /// <summary>
    /// Set a temporary look-at override from Vivy's AI pipeline.
    /// The avatar head and eyes will track <paramref name="screenPos"/> (pixel space)
    /// for <paramref name="durationSeconds"/> seconds, then resume mouse tracking.
    /// Pass durationSeconds = 0 to cancel an active override immediately.
    /// </summary>
    public void SetLookAtOverride(Vector2 screenPos, float durationSeconds)
    {
        if (durationSeconds <= 0f)
        {
            _vivyOverrideActive = false;
            return;
        }
        if (!_vivyOverrideActive)
        {
            _smoothOverrideScreen = (screenPos.x <= 0.01f && screenPos.y <= 0.01f) ? new Vector2(0.5f, 0.5f) : screenPos;
        }
        _vivyOverrideScreen  = screenPos;
        _vivyOverrideExpiry  = Time.time + durationSeconds;
        _vivyOverrideActive  = true;
    }

    private Camera GetActiveCamera()
    {
        if (_vivyOverrideActive)
        {
            var streamer = GetComponent<VivyAvatarStreamer>();
            if (streamer != null && streamer.StreamCamera != null)
            {
                return streamer.StreamCamera;
            }
        }
        return mainCam != null ? mainCam : Camera.main;
    }

    /// <summary>Returns the effective mouse/lookat position for this frame relative to active camera pixels.</summary>
    private Vector3 GetEffectivePixelPosition(Camera cam)
    {
        if (cam == null) return Input.mousePosition;
        UpdateMicroSaccades(cam);
        Vector3 basePos;

        if (_vivyOverrideActive)
        {
            if (Time.time < _vivyOverrideExpiry)
            {
                // If override is (0,0), substitute center (0.5, 0.5) so avatar faces forward instead of looking down at floor
                Vector2 target = (_vivyOverrideScreen.x <= 0.01f && _vivyOverrideScreen.y <= 0.01f)
                    ? new Vector2(0.5f, 0.5f) : _vivyOverrideScreen;

                // Smoothly interpolate the normalized override coordinate to eliminate browser update-interval jitter
                _smoothOverrideScreen = Vector2.Lerp(_smoothOverrideScreen, target, Time.deltaTime * 15f);
                basePos = new Vector3(_smoothOverrideScreen.x * cam.pixelWidth, _smoothOverrideScreen.y * cam.pixelHeight, 0f);
                return basePos + (Vector3)_saccadeOffset;
            }
            // Override expired — return to mouse tracking
            _vivyOverrideActive = false;
        }

        Vector3 mouse = Input.mousePosition;
        // When mouse is off-screen or near zero, default to straight ahead at camera center (0.5, 0.5)
        if (mouse.x <= 5f || mouse.y <= 5f || mouse.x >= Screen.width - 5f || mouse.y >= Screen.height - 5f)
        {
            basePos = new Vector3(0.5f * cam.pixelWidth, 0.5f * cam.pixelHeight, 0f);
        }
        else
        {
            basePos = mouse;
        }
        return basePos + (Vector3)_saccadeOffset;
    }

    void Start()
    {
        animator = GetComponent<Animator>();
        mainCam = Camera.main;
        if (!animator || !animator.isHuman) { enableMouseTracking = false; Debug.LogError("Animator not found or not humanoid!"); return; }
        vrm10 = GetComponentInChildren<Vrm10Instance>();
        InitHead(); InitSpine(); InitEye();
    }

    void InitHead()
    {
        headBone = animator.GetBoneTransform(HumanBodyBones.Head);
        if (!headBone) return;
        headDriver = new GameObject("HeadDriver").transform;
        headDriver.SetParent(headBone.parent, false);
        headDriver.localPosition = headBone.localPosition;
        headDriver.localRotation = headBone.localRotation;
        headInitRot = headBone.localRotation;
    }

    void InitSpine()
    {
        spineBone = animator.GetBoneTransform(HumanBodyBones.Spine);
        chestBone = animator.GetBoneTransform(HumanBodyBones.Chest);
        upperChestBone = animator.GetBoneTransform(HumanBodyBones.UpperChest);
        if (!spineBone) return;
        spineDriver = new GameObject("SpineDriver").transform;
        spineDriver.SetParent(spineBone.parent, false);
        spineDriver.localPosition = spineBone.localPosition;
        spineDriver.localRotation = spineBone.localRotation;
        spineInitRot = spineBone.localRotation;
    }

    void InitEye()
    {
        leftEyeBone = animator.GetBoneTransform(HumanBodyBones.LeftEye);
        rightEyeBone = animator.GetBoneTransform(HumanBodyBones.RightEye);
        if (vrm10)
        {
            vrmLookAtTarget = new GameObject("VRMLookAtTarget").transform;
            vrmLookAtTarget.SetParent(transform, false);
            vrm10.LookAtTarget = vrmLookAtTarget;
            vrm10.LookAtTargetType = VRM10ObjectLookAt.LookAtTargetTypes.SpecifiedTransform;
        }
        if (!leftEyeBone || !rightEyeBone)
        {
            foreach (var t in animator.GetComponentsInChildren<Transform>())
            {
                var n = t.name.ToLower();
                if (!leftEyeBone && (n.Contains("lefteye") || n.Contains("eye.l"))) leftEyeBone = t;
                else if (!rightEyeBone && (n.Contains("righteye") || n.Contains("eye.r"))) rightEyeBone = t;
            }
        }
        if (leftEyeBone && rightEyeBone)
        {
            eyeCenter = new GameObject("EyeCenter").transform;
            eyeCenter.SetParent(leftEyeBone.parent, false);
            eyeCenter.position = (leftEyeBone.position + rightEyeBone.position) * 0.5f;
            leftEyeDriver = new GameObject("LeftEyeDriver").transform;
            leftEyeDriver.SetParent(leftEyeBone.parent, false);
            leftEyeDriver.localPosition = leftEyeBone.localPosition;
            leftEyeDriver.localRotation = leftEyeBone.localRotation;
            rightEyeDriver = new GameObject("RightEyeDriver").transform;
            rightEyeDriver.SetParent(rightEyeBone.parent, false);
            rightEyeDriver.localPosition = rightEyeBone.localPosition;
            rightEyeDriver.localRotation = rightEyeBone.localRotation;
        }
    }

    void LateUpdate()
    {
        if (!mainCam) mainCam = Camera.main;
        if (!enableMouseTracking || !mainCam || !animator || !animator.IsValidAndPlaying()) return;
        var info = animator.GetCurrentAnimatorStateInfo(0);
        var next = animator.GetNextAnimatorStateInfo(0);
        bool trans = animator.IsInTransition(0);
        if (trans) nextStateHash = next.shortNameHash;
        else { currStateHash = info.shortNameHash; nextStateHash = 0; }

        if (IsAllowed("Head")) DoHead();
        DoSpine();
        if (IsAllowed("Eye")) DoEye();
    }

    bool IsAllowed(string f)
    {
        bool? a = null, b = null;
        foreach (var t in trackingPermissions)
        {
            if (t.isParameter && animator.GetBool(t.stateOrParameterName)) return Get(t, f);
            int hash = Animator.StringToHash(t.stateOrParameterName);
            if (currStateHash == hash) a = Get(t, f);
            if (animator.IsInTransition(0) && nextStateHash == hash) b = Get(t, f);
        }
        if (animator.IsInTransition(0) && b.HasValue) return b.Value;
        return a ?? false;
    }
    bool Get(TrackingPermission e, string f) => f == "Head" ? e.allowHead : f == "Spine" ? e.allowSpine : e.allowEye;

    void DoHead()
    {
        if (!headBone || !headDriver) return;
        var activeCam = GetActiveCamera();
        if (activeCam == null) return;
        var mouse = GetEffectivePixelPosition(activeCam);
        float depth = Vector3.Distance(activeCam.transform.position, headDriver.position);
        var world = activeCam.ScreenToWorldPoint(new Vector3(mouse.x, mouse.y, depth));
        var dir = (world - headDriver.position).normalized;
        var localDir = headDriver.parent.InverseTransformDirection(dir);
        float yaw = Mathf.Clamp(Mathf.Atan2(localDir.x, localDir.z) * Mathf.Rad2Deg, -headYawLimit, headYawLimit);
        float pitch = Mathf.Clamp(Mathf.Asin(localDir.y) * Mathf.Rad2Deg, -headPitchLimit, headPitchLimit);
        headDriver.localRotation = Quaternion.Slerp(headDriver.localRotation, Quaternion.Euler(-pitch, yaw, 0), Time.deltaTime * headSmoothness);
        var baseRot = headBone.localRotation;
        var delta = headDriver.localRotation * Quaternion.Inverse(headInitRot);
        headBone.localRotation = Quaternion.Slerp(baseRot, delta * baseRot, headBlend);
    }

    void DoSpine()
    {
        if (!spineBone || !spineDriver) return;
        float targetW = IsAllowed("Spine") ? 1f : 0f;
        spineTrackingWeight = Mathf.MoveTowards(spineTrackingWeight, targetW, Time.deltaTime * spineFadeSpeed);
        var activeCam = GetActiveCamera();
        if (activeCam == null) return;
        var mouse = GetEffectivePixelPosition(activeCam);
        float normX = Mathf.Clamp01(mouse.x / activeCam.pixelWidth);
        float targetY = Mathf.Lerp(spineMinRotation, spineMaxRotation, normX);
        spineDriver.localRotation = Quaternion.Slerp(spineDriver.localRotation, Quaternion.Euler(0f, -targetY, 0f), Time.deltaTime * spineSmoothness);
        var baseRot = spineBone.localRotation;
        var delta = spineDriver.localRotation * Quaternion.Inverse(spineInitRot);
        float applied = spineTrackingWeight * spineBlend;
        var offset = Quaternion.Slerp(Quaternion.identity, delta, applied);
        spineBone.localRotation = offset * baseRot;
        if (chestBone)
            chestBone.localRotation = Quaternion.Slerp(Quaternion.identity, delta, 0.8f * applied) * chestBone.localRotation;
        if (upperChestBone)
            upperChestBone.localRotation = Quaternion.Slerp(Quaternion.identity, delta, 0.6f * applied) * upperChestBone.localRotation;
    }

    void DoEye()
    {
        var activeCam = GetActiveCamera();
        if (activeCam == null) return;
        var mouse = GetEffectivePixelPosition(activeCam);
        float depth = Vector3.Distance(activeCam.transform.position, eyeCenter != null ? eyeCenter.position : transform.position);
        var world = activeCam.ScreenToWorldPoint(new Vector3(mouse.x, mouse.y, depth));
        if (vrm10 && vrmLookAtTarget)
        {
            vrmLookAtTarget.position = Vector3.Lerp(vrmLookAtTarget.position, world, Time.deltaTime * eyeSmoothness);
            if (vrm10.Runtime != null && vrm10.Runtime.LookAt != null)
            {
                var par = vrmLookAtTarget.parent ?? transform;
                Matrix4x4 mtx = Matrix4x4.TRS(par.position, par.rotation, Vector3.one);
                var (rawYaw, rawPitch) = mtx.CalcYawPitch(vrmLookAtTarget.position);
                float yaw = Mathf.Clamp(-rawYaw, -eyeYawLimit, eyeYawLimit);
                float pitch = Mathf.Clamp(rawPitch, -eyePitchLimit, eyePitchLimit);
                vrm10.Runtime.LookAt.SetYawPitchManually(yaw, pitch);
            }
            return;
        }
        if (!leftEyeBone || !rightEyeBone || !eyeCenter) return;
        eyeCenter.position = (leftEyeBone.position + rightEyeBone.position) * 0.5f;
        var dir = (world - eyeCenter.position).normalized;
        var localDir = eyeCenter.parent.InverseTransformDirection(dir);
        float eyeYaw = Mathf.Clamp(Mathf.Atan2(localDir.x, localDir.z) * Mathf.Rad2Deg, -eyeYawLimit, eyeYawLimit);
        float eyePitch = Mathf.Clamp(Mathf.Asin(localDir.y) * Mathf.Rad2Deg, -eyePitchLimit, eyePitchLimit);
        var eyeRot = Quaternion.Euler(-eyePitch, eyeYaw, 0f);
        leftEyeDriver.localRotation = Quaternion.Slerp(leftEyeDriver.localRotation, eyeRot, Time.deltaTime * eyeSmoothness);
        rightEyeDriver.localRotation = Quaternion.Slerp(rightEyeDriver.localRotation, eyeRot, Time.deltaTime * eyeSmoothness);
        leftEyeBone.localRotation = Quaternion.Slerp(leftEyeBone.localRotation, leftEyeDriver.localRotation, eyeBlend);
        rightEyeBone.localRotation = Quaternion.Slerp(rightEyeBone.localRotation, rightEyeDriver.localRotation, eyeBlend);
    }

    void OnDestroy()
    {
        if (headDriver != null) Destroy(headDriver.gameObject);
        if (spineDriver != null) Destroy(spineDriver.gameObject);
        if (leftEyeDriver != null) Destroy(leftEyeDriver.gameObject);
        if (rightEyeDriver != null) Destroy(rightEyeDriver.gameObject);
        if (eyeCenter != null) Destroy(eyeCenter.gameObject);
        if (vrmLookAtTarget != null) Destroy(vrmLookAtTarget.gameObject);
    }
}
