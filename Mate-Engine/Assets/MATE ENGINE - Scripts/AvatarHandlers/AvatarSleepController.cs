using UnityEngine;
using System.Collections.Generic;

public class AvatarSleepController : MonoBehaviour
{
    [Header("Enable Sleep Feature")]
    public bool enableSleep = false;

    [Header("Sleep Timer (seconds)")]
    [Range(30f, 360f)]
    public float sleepTimer = 60f;

    [Header("Allowed States (Whitelist)")]
    public string[] allowedStates = new string[] { "Idle", "Sleeping" };

    [Header("Wake Up If Any Of These Animator Bools Is True")]
    public string[] wakeUpBools = new string[] { "isDragging" };

    [Header("Debug Info (Read Only)")]
    [SerializeField] private float idleTime = 0f;
    [SerializeField] private string currentState = "";
    [SerializeField] private bool isSleeping = false;

    [Header("Circadian Energy Rules")]
    [SerializeField] private float currentEnergy = 1.0f;
    [SerializeField] private bool isSleepLocked = false;
    public bool IsSleepLocked => isSleepLocked;

    private Animator animator;
    private int _resolvedSleepParamHash = 0;

    void Start()
    {
        animator = GetComponent<Animator>();
        ResolveSleepParam();
        SetSleeping(false);
        idleTime = 0f;
    }

    private bool IsAnimatorValid() => animator != null && animator.IsValidAndPlaying();

    void ResolveSleepParam()
    {
        if (!IsAnimatorValid()) return;
        _resolvedSleepParamHash = Animator.StringToHash("isSleeping"); // default lowercase
        foreach (var p in animator.parameters)
        {
            if (p.name == "IsSleeping")
            {
                _resolvedSleepParamHash = Animator.StringToHash("IsSleeping");
                break;
            }
        }
    }

    public void UpdateCircadianEnergy(float energy)
    {
        currentEnergy = Mathf.Clamp01(energy);
        if (currentEnergy < 0.20f && !isSleepLocked)
        {
            isSleepLocked = true;
            SetSleepOverride(true);
            Debug.Log($"[AvatarSleepController] Energy dropped to {currentEnergy:P0} (< 20%). Activating locked sleep mode.");
        }
        else if (currentEnergy > 0.40f && isSleepLocked)
        {
            isSleepLocked = false;
            SetSleepOverride(false);
            Debug.Log($"[AvatarSleepController] Energy recharged to {currentEnergy:P0} (> 40%). Releasing sleep lock.");
        }
    }

    void Update()
    {
        if (!enableSleep || !IsAnimatorValid())
        {
            if (!isSleepLocked)
                SetSleeping(false);
            idleTime = 0f;
            return;
        }

        AnimatorStateInfo state = animator.GetCurrentAnimatorStateInfo(0);
        currentState = GetCurrentStateName(state);

        if (IsAnyWakeUpBoolTrue())
        {
            if (!isSleepLocked)
                WakeUp();
            return;
        }

        bool allowed = IsInAllowedState(state);

        if (allowed)
        {
            if (!isSleeping)
                idleTime += Time.deltaTime;
            // Removed automatic idle sleep timer: Sleep is strictly controlled by Circadian Energy (< 0.20) or manual overrides.
        }
        else
        {
            idleTime = 0f;
            if (!isSleepLocked)
                SetSleeping(false);
        }

        if (isSleeping && !allowed && !isSleepLocked)
        {
            SetSleeping(false);
            idleTime = 0f;
        }
        else if (isSleepLocked && !isSleeping)
        {
            SetSleeping(true);
        }
    }

    string GetCurrentStateName(AnimatorStateInfo state)
    {
        foreach (var s in allowedStates)
            if (!string.IsNullOrEmpty(s) && state.IsName(s))
                return s;
            return state.shortNameHash.ToString();
    }

    bool IsInAllowedState(AnimatorStateInfo state)
    {
        if (allowedStates == null || allowedStates.Length == 0)
            return true;
        foreach (var s in allowedStates)
            if (!string.IsNullOrEmpty(s) && state.IsName(s))
                return true;
        return false;
    }

    bool IsAnyWakeUpBoolTrue()
    {
        if (wakeUpBools == null || wakeUpBools.Length == 0 || !IsAnimatorValid())
            return false;
        foreach (var b in wakeUpBools)
        {
            if (!string.IsNullOrEmpty(b) && animator.GetBool(b))
                return true;
        }
        return false;
    }

    public void SetSleepOverride(bool sleepState)
    {
        if (sleepState)
        {
            enableSleep = true;
            idleTime = sleepTimer;
            SetSleeping(true);
        }
        else
        {
            if (isSleepLocked)
            {
                Debug.LogWarning("[AvatarSleepController] Cannot awaken: Sleep mode is locked due to low circadian energy (< 40%).");
                return;
            }
            WakeUp();
        }
    }

    void SetSleeping(bool value)
    {
        if (isSleeping == value)
            return;
        isSleeping = value;
        if (IsAnimatorValid())
        {
            if (_resolvedSleepParamHash != 0)
                animator.SetBool(_resolvedSleepParamHash, value);
            else
                animator.SetBool("isSleeping", value);
        }
    }

    public void WakeUp()
    {
        if (isSleepLocked) return;
        SetSleeping(false);
        idleTime = 0f;
    }
}
