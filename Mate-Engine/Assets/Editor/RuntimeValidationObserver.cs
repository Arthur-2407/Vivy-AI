using UnityEditor;
using UnityEngine;
using System.IO;
using System.Collections.Generic;

[InitializeOnLoad]
public static class RuntimeValidationObserver
{
    private static Animator _targetAnimator;
    private static string _logPath = "d:/Vivy/Reports/Live_Animator_Audit.txt";
    private static string _lastStateName = "";
    private static List<string> _logBuffer = new List<string>();

    static RuntimeValidationObserver()
    {
        EditorApplication.update += OnUpdate;
        EditorApplication.playModeStateChanged += OnPlayModeChanged;
    }

    private static void OnPlayModeChanged(PlayModeStateChange state)
    {
        if (state == PlayModeStateChange.EnteredPlayMode)
        {
            _logBuffer.Clear();
            _logBuffer.Add("--- RUNTIME VALIDATION OBSERVER STARTED ---");
            _lastStateName = "";
        }
        else if (state == PlayModeStateChange.ExitingPlayMode)
        {
            FlushLog();
        }
    }

    private static void OnUpdate()
    {
        if (!Application.isPlaying) return;

        if (_targetAnimator == null)
        {
            // Find the avatar animator
            var animators = Object.FindObjectsByType<Animator>(FindObjectsSortMode.None);
            foreach (var a in animators)
            {
                if (a.gameObject.name.Contains("CustomVRM") || a.gameObject.name.Contains("Avatar") || a.gameObject.GetComponent("VivyWebSocketClient") != null)
                {
                    _targetAnimator = a;
                    _logBuffer.Add($"[Observer] Attached to Animator on: {_targetAnimator.gameObject.name}");
                    break;
                }
            }
        }

        if (_targetAnimator != null && _targetAnimator.gameObject.activeInHierarchy)
        {
            int baseLayer = 0;
            if (_targetAnimator.layerCount > 0)
            {
                var stateInfo = _targetAnimator.GetCurrentAnimatorStateInfo(baseLayer);
                var clipInfo = _targetAnimator.GetCurrentAnimatorClipInfo(baseLayer);
                string currentState = stateInfo.fullPathHash.ToString(); // Or stateInfo.IsName if we had hash mappings

                // Try to get actual state name from clip if possible, or hash
                string stateReadable = $"Hash:{stateInfo.fullPathHash}";
                string clipName = "NULL";
                if (clipInfo != null && clipInfo.Length > 0 && clipInfo[0].clip != null)
                {
                    clipName = clipInfo[0].clip.name;
                    stateReadable = clipName; 
                }

                if (stateReadable != _lastStateName)
                {
                    _lastStateName = stateReadable;
                    string entry = $"[{Time.time:F2}s] Transitioned to State/Clip: {clipName} | NormalizedTime: {stateInfo.normalizedTime:F2}";
                    _logBuffer.Add(entry);

                    // Flush every 10 entries to avoid massive memory buildup
                    if (_logBuffer.Count > 10)
                    {
                        FlushLog();
                    }
                }
            }
        }
    }

    private static void FlushLog()
    {
        if (_logBuffer.Count > 0)
        {
            try
            {
                File.AppendAllLines(_logPath, _logBuffer);
                _logBuffer.Clear();
            }
            catch { }
        }
    }
}
