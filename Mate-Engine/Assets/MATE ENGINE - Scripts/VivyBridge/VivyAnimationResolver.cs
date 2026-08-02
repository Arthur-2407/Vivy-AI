using System.Collections.Generic;
using UnityEngine;
using Vivy.AnimationFramework;

public class VivyAnimationResolver : MonoBehaviour
{
    private Animator _animator;
    private List<string> _knownBools = new List<string>();

    private void Start()
    {
        _animator = GetComponent<Animator>();
        if (_animator != null)
        {
            // Cache all known bool parameters from the Animator to avoid checking every frame
            foreach (var param in _animator.parameters)
            {
                if (param.type == AnimatorControllerParameterType.Bool)
                {
                    _knownBools.Add(param.name);
                }
            }
            DumpAnimatorDiagnostics();
        }
    }

    private void DumpAnimatorDiagnostics()
    {
        try
        {
            string log = $"Animator Diagnostics:\nApplyRootMotion: {_animator.applyRootMotion}\n";
            log += $"Has Transform: {transform.position}\n";
            for (int i = 0; i < _animator.layerCount; i++)
            {
                log += $"Layer {i}: {_animator.GetLayerName(i)} | Weight: {_animator.GetLayerWeight(i)}\n";
                var clipInfo = _animator.GetCurrentAnimatorClipInfo(i);
                foreach (var info in clipInfo)
                {
                    log += $"  - Playing Clip: {(info.clip != null ? info.clip.name : "NULL")}\n";
                }
            }

            // Dump all parameters and their types
            log += "\nParameters:\n";
            foreach (var param in _animator.parameters)
            {
                log += $"  {param.name} ({param.type})\n";
            }

            System.IO.File.WriteAllText("d:/Vivy/runtime_animator_diag.txt", log);
        }
        catch (System.Exception e)
        {
            Debug.LogError("Diag failed: " + e.Message);
        }
    }

    public void PlayAnimation(string animId)
    {
        if (_animator == null)
        {
            _animator = GetComponent<Animator>();
            if (_animator == null) return;
        }
        if (!_animator.IsValidAndPlaying()) return;

        // Ensure Registry exists
        if (AnimationRegistry.Instance == null)
        {
            var go = new GameObject("AnimationRegistry_Auto");
            go.AddComponent<AnimationRegistry>();
            Debug.Log("[VivyAnimationResolver] Auto-instantiated missing AnimationRegistry.");
        }

        var registry = AnimationRegistry.Instance;
        if (registry != null)
        {
            var clipMeta = registry.GetClipById(animId);
            if (clipMeta != null)
            {
                Debug.Log($"[VivyAnimationResolver] Found registry entry for '{animId}': trigger='{clipMeta.trigger}', bool='{clipMeta.bool_param}', index='{clipMeta.index_param}', index_val={clipMeta.index_val}");

                // Reset all known bool parameters to false first (stop current animation)
                foreach (var boolParam in _knownBools)
                {
                    _animator.SetBool(boolParam, false);
                }

                // Apply Bool parameter
                if (!string.IsNullOrEmpty(clipMeta.bool_param))
                {
                    if (AnimatorHasParameter(clipMeta.bool_param, AnimatorControllerParameterType.Bool))
                    {
                        _animator.SetBool(clipMeta.bool_param, true);
                        Debug.Log($"[VivyAnimationResolver] SetBool '{clipMeta.bool_param}' = true");
                    }
                    else
                    {
                        Debug.LogWarning($"[VivyAnimationResolver] Bool parameter '{clipMeta.bool_param}' not found on Animator.");
                    }
                }

                // Apply index parameter — detect whether it's Int or Float on the actual Animator
                if (!string.IsNullOrEmpty(clipMeta.index_param))
                {
                    var paramType = GetParameterType(clipMeta.index_param);
                    if (paramType == AnimatorControllerParameterType.Int)
                    {
                        _animator.SetInteger(clipMeta.index_param, clipMeta.index_val);
                        Debug.Log($"[VivyAnimationResolver] SetInteger '{clipMeta.index_param}' = {clipMeta.index_val}");
                    }
                    else if (paramType == AnimatorControllerParameterType.Float)
                    {
                        _animator.SetFloat(clipMeta.index_param, (float)clipMeta.index_val);
                        Debug.Log($"[VivyAnimationResolver] SetFloat '{clipMeta.index_param}' = {clipMeta.index_val}");
                    }
                    else
                    {
                        Debug.LogWarning($"[VivyAnimationResolver] Index parameter '{clipMeta.index_param}' not found as Int or Float on Animator.");
                    }
                }

                // Apply Trigger parameter
                if (!string.IsNullOrEmpty(clipMeta.trigger))
                {
                    if (AnimatorHasParameter(clipMeta.trigger, AnimatorControllerParameterType.Trigger))
                    {
                        _animator.SetTrigger(clipMeta.trigger);
                        Debug.Log($"[VivyAnimationResolver] SetTrigger '{clipMeta.trigger}'");
                    }
                    else
                    {
                        Debug.LogWarning($"[VivyAnimationResolver] Trigger parameter '{clipMeta.trigger}' not found on Animator.");
                    }
                }

                return;
            }
            else
            {
                Debug.LogWarning($"[VivyAnimationResolver] Animation ID '{animId}' not found in registry. Trying direct trigger fallback.");
            }
        }

        // Fallback for backward compatibility
        if (AnimatorHasParameter(animId, AnimatorControllerParameterType.Trigger))
        {
            _animator.SetTrigger(animId);
        }
        else
        {
            Debug.LogWarning($"[VivyAnimationResolver] Animator has no Trigger parameter '{animId}' and it was not found in registry. Skipping.");
        }
    }

    /// <summary>
    /// Get the actual parameter type from the Animator, regardless of what the registry says.
    /// This handles the case where DanceIndex is defined as Float in the controller
    /// but the registry treats it as an integer index.
    /// </summary>
    private AnimatorControllerParameterType GetParameterType(string paramName)
    {
        if (_animator == null || !_animator.IsValidAndPlaying()) return (AnimatorControllerParameterType)(-1);
        foreach (var p in _animator.parameters)
        {
            if (p.name == paramName)
                return p.type;
        }
        return (AnimatorControllerParameterType)(-1);
    }

    private bool AnimatorHasParameter(string paramName, AnimatorControllerParameterType paramType)
    {
        if (_animator == null || !_animator.IsValidAndPlaying()) return false;
        foreach (var p in _animator.parameters)
        {
            if (p.name == paramName && p.type == paramType)
                return true;
        }
        return false;
    }
}
