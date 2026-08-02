using UnityEngine;
using VRM;
using UniVRM10;
using System.Collections.Generic;

[DisallowMultipleComponent]
public class UniversalBlendshapes : MonoBehaviour
{
    [Header("Universal Preview")]
    [Range(0f, 1f)] public float Blink, Blink_L, Blink_R, LookUp, LookDown, LookLeft, LookRight, Neutral;
    [Range(0f, 1f)] public float A, I, U, E, O, Joy, Angry, Sorrow, Fun;
    public float fadeSpeed = 5f, safeTimeout = 2f, minHoldTime = 0.1f;

    private VRMBlendShapeProxy proxy0; private Vrm10Instance vrm1; private Vrm10RuntimeExpression expr1;
    private class BlendState { public float value, lastInput, lastUpdateTime, holdUntil; }

    private readonly Dictionary<string, BlendState> states = new();
    private readonly List<KeyValuePair<BlendShapeKey, float>> reusableList = new();

    private static readonly string[] keys = new[]
    {
        "Blink", "Blink_L", "Blink_R",
        "LookUp", "LookDown", "LookLeft", "LookRight",
        "Neutral", "A", "I", "U", "E", "O",
        "Joy", "Angry", "Sorrow", "Fun"
    };

    private static readonly BlendShapePreset[] vrm0Presets = new[]
    {
        BlendShapePreset.Blink, BlendShapePreset.Blink_L, BlendShapePreset.Blink_R,
        BlendShapePreset.LookUp, BlendShapePreset.LookDown, BlendShapePreset.LookLeft, BlendShapePreset.LookRight,
        BlendShapePreset.Neutral,
        BlendShapePreset.A, BlendShapePreset.I, BlendShapePreset.U, BlendShapePreset.E, BlendShapePreset.O,
        BlendShapePreset.Joy, BlendShapePreset.Angry, BlendShapePreset.Sorrow, BlendShapePreset.Fun
    };

    private static readonly Dictionary<string, string> vrm10KeyMap = new()
    {
        { "A", "aa" }, { "I", "ih" }, { "U", "ou" }, { "E", "ee" }, { "O", "oh" },
        { "Joy", "happy" }, { "Angry", "angry" }, { "Sorrow", "sad" }, { "Fun", "relaxed" },
        { "Blink", "blink" }, { "Blink_L", "blinkLeft" }, { "Blink_R", "blinkRight" },
        { "LookUp", "lookUp" }, { "LookDown", "lookDown" }, { "LookLeft", "lookLeft" }, { "LookRight", "lookRight" },
        { "Neutral", "neutral" }
    };

    private readonly Dictionary<string, ExpressionKey> vrm1ExpressionKeyMap = new();
    private readonly float[] valueCache = new float[keys.Length];

    [Header("Autonomous Behavior")]
    public bool autoBlinkEnabled = true;
    [Range(2f, 8f)] public float minBlinkInterval = 2.5f;
    [Range(3f, 10f)] public float maxBlinkInterval = 5.5f;

    private void Awake()
    {
        // Unconditionally initialize states dictionary first to prevent dictionary key missing bugs
        for (int i = 0; i < keys.Length; i++)
            states[keys[i]] = new BlendState();

        try
        {
            proxy0 = GetComponent<VRMBlendShapeProxy>();
            vrm1 = GetComponentInChildren<Vrm10Instance>(true);
            expr1 = vrm1 != null ? vrm1.Runtime?.Expression : null;
        }
        catch (System.Exception ex)
        {
            Debug.LogError($"[UniversalBlendshapes] Error in Awake refs: {ex.Message}");
        }

        if (expr1 != null)
        {
            try
            {
                vrm1ExpressionKeyMap.Clear();
                foreach (var k in expr1.ExpressionKeys)
                {
                    if (!vrm1ExpressionKeyMap.ContainsKey(k.Name))
                        vrm1ExpressionKeyMap[k.Name] = k;
                }
            }
            catch (System.Exception ex)
            {
                Debug.LogError($"[UniversalBlendshapes] Error mapping expression keys: {ex.Message}");
            }
        }
    }

    private void Start()
    {
        StartCoroutine(AutonomousBlinkRoutine());
    }

    private System.Collections.IEnumerator AutonomousBlinkRoutine()
    {
        while (true)
        {
            float delay = UnityEngine.Random.Range(minBlinkInterval, maxBlinkInterval);
            yield return new WaitForSeconds(delay);

            if (!autoBlinkEnabled || IsAvatarSleeping()) continue;

            int blinks = (UnityEngine.Random.value < 0.2f) ? 2 : 1;
            for (int i = 0; i < blinks; i++)
            {
                float elapsed = 0f;
                float closeDuration = 0.07f;
                while (elapsed < closeDuration)
                {
                    elapsed += Time.deltaTime;
                    Blink = Mathf.Lerp(0f, 1f, elapsed / closeDuration);
                    yield return null;
                }
                Blink = 1f;

                elapsed = 0f;
                float openDuration = 0.12f;
                while (elapsed < openDuration)
                {
                    elapsed += Time.deltaTime;
                    Blink = Mathf.Lerp(1f, 0f, elapsed / openDuration);
                    yield return null;
                }
                Blink = 0f;

                if (blinks > 1 && i < blinks - 1)
                    yield return new WaitForSeconds(0.1f);
            }
        }
    }

    private bool HasBoolParam(Animator a, string paramName)
    {
        foreach (var p in a.parameters)
            if (p.name == paramName && p.type == AnimatorControllerParameterType.Bool)
                return true;
        return false;
    }

    private bool IsAvatarSleeping()
    {
        var anim = GetComponent<Animator>();
        if (anim != null && anim.IsValidAndPlaying())
        {
            foreach (var p in anim.parameters)
            {
                if (p.type == AnimatorControllerParameterType.Bool &&
                    (string.Equals(p.name, "isSleeping", System.StringComparison.OrdinalIgnoreCase) ||
                     string.Equals(p.name, "sleeping", System.StringComparison.OrdinalIgnoreCase)))
                {
                    if (anim.GetBool(p.name)) return true;
                }
            }
        }
        return false;
    }

    private void LateUpdate()
    {
        float now = Time.time;
        float dt = Time.deltaTime;

        // Ensure states is initialized (fallback)
        for (int i = 0; i < keys.Length; i++)
        {
            if (!states.ContainsKey(keys[i]))
                states[keys[i]] = new BlendState();
        }

        for (int i = 0; i < keys.Length; i++)
        {
            string key = keys[i];
            float input = valueCache[i] = GetInputValue(i);
            UpdateState(key, input, now, dt);
        }

        if (IsAvatarSleeping())
        {
            if (states.TryGetValue("Blink", out var blinkState))
            {
                blinkState.value = Mathf.MoveTowards(blinkState.value, 1f, fadeSpeed * dt);
                Blink = blinkState.value;
            }
        }

        if (proxy0 != null)
        {
            reusableList.Clear();
            for (int i = 0; i < keys.Length; i++)
            {
                reusableList.Add(new KeyValuePair<BlendShapeKey, float>(
                    BlendShapeKey.CreateFromPreset(vrm0Presets[i]), states[keys[i]].value
                ));
            }
            proxy0.SetValues(reusableList);
            proxy0.Apply();
        }
        else if (expr1 != null)
        {
            for (int i = 0; i < keys.Length; i++)
            {
                string key = keys[i];
                if (!vrm10KeyMap.TryGetValue(key, out var mapped)) mapped = key;
                if (vrm1ExpressionKeyMap.TryGetValue(mapped, out var exprKey))
                {
                    expr1.SetWeight(exprKey, states[key].value);
                }
            }
        }
    }

    private float GetInputValue(int i) => i switch
    {
        0 => Blink,
        1 => Blink_L,
        2 => Blink_R,
        3 => LookUp,
        4 => LookDown,
        5 => LookLeft,
        6 => LookRight,
        7 => Neutral,
        8 => A,
        9 => I,
        10 => U,
        11 => E,
        12 => O,
        13 => Joy,
        14 => Angry,
        15 => Sorrow,
        16 => Fun,
        _ => 0f
    };


    private void UpdateState(string key, float input, float now, float dt)
    {
        if (!states.TryGetValue(key, out var state)) return;

        bool changed = !Mathf.Approximately(input, state.lastInput);
        bool activelyDriven = !Mathf.Approximately(input, 0f);

        if (changed || activelyDriven)
        {
            state.lastInput = input;
            state.lastUpdateTime = now;
            state.value = input;
            state.holdUntil = now + minHoldTime;
        }
        else
        {
            if (now < state.holdUntil)
            {
                state.value = input;
            }
            else
            {
                float idleTime = now - state.lastUpdateTime;
                if (idleTime > safeTimeout)
                {
                    state.value = 0f;
                }
                else
                {
                    state.value = Mathf.MoveTowards(state.value, 0f, fadeSpeed * dt);
                }
            }
        }
    }
}
