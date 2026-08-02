using UnityEngine;
using System.Collections;
using System.Collections.Generic;

/// <summary>
/// Vivy Emotion Mapper — Maps Vivy's 7 emotion labels to MateEngine blendshapes.
///
/// Vivy's emotion engine (distilroberta) outputs:
///   joy, sadness, anger, surprise, fear, disgust, neutral
///
/// MateEngine's UniversalBlendshapes supports:
///   Joy, Angry, Sorrow, Fun, Neutral, Blink, A/I/U/E/O, LookUp/Down/Left/Right
///
/// This component smoothly transitions between emotion states by driving
/// the UniversalBlendshapes component on the same GameObject.
///
/// Attach this to the root avatar GameObject (same as UniversalBlendshapes).
/// </summary>
[RequireComponent(typeof(UniversalBlendshapes))]
public class VivyEmotionMapper : MonoBehaviour
{
    [Header("Transition Settings")]
    [Range(0.5f, 10f)] public float transitionSpeed = 3f;
    [Range(0f, 1f)] public float maxExpressionIntensity = 0.85f;

    [Header("Debug")]
    public string currentEmotion = "neutral";
    public bool logEmotionChanges = true;

    // Target blendshape weights for current emotion
    private Dictionary<string, float> _targetWeights = new Dictionary<string, float>();
    private Dictionary<string, float> _currentWeights = new Dictionary<string, float>();

    // Reference to MateEngine's blendshape system
    private UniversalBlendshapes _blendshapes;

    // All blendshape keys we control
    private static readonly string[] _emotionKeys = { "Joy", "Angry", "Sorrow", "Fun", "Neutral" };

    // Emotion → Blendshape mappings
    private static readonly Dictionary<string, Dictionary<string, float>> _emotionMap = new Dictionary<string, Dictionary<string, float>>
    {
        { "joy", new Dictionary<string, float> { { "Joy", 0.8f }, { "Fun", 0.5f }, { "Angry", 0f }, { "Sorrow", 0f }, { "Neutral", 0f } } },
        { "sadness", new Dictionary<string, float> { { "Joy", 0f }, { "Fun", 0f }, { "Angry", 0f }, { "Sorrow", 0.8f }, { "Neutral", 0f } } },
        { "anger", new Dictionary<string, float> { { "Joy", 0f }, { "Fun", 0f }, { "Angry", 0.8f }, { "Sorrow", 0f }, { "Neutral", 0f } } },
        { "surprise", new Dictionary<string, float> { { "Joy", 0.3f }, { "Fun", 0.2f }, { "Angry", 0f }, { "Sorrow", 0f }, { "Neutral", 0f } } },
        { "fear", new Dictionary<string, float> { { "Joy", 0f }, { "Fun", 0f }, { "Angry", 0.2f }, { "Sorrow", 0.4f }, { "Neutral", 0f } } },
        { "disgust", new Dictionary<string, float> { { "Joy", 0f }, { "Fun", 0f }, { "Angry", 0.5f }, { "Sorrow", 0.2f }, { "Neutral", 0f } } },
        { "neutral", new Dictionary<string, float> { { "Joy", 0f }, { "Fun", 0f }, { "Angry", 0f }, { "Sorrow", 0f }, { "Neutral", 1f } } }
    };

    void Awake()
    {
        _blendshapes = GetComponent<UniversalBlendshapes>();

        // Initialize weights to zero
        foreach (var key in _emotionKeys)
        {
            _currentWeights[key] = 0f;
            _targetWeights[key] = 0f;
        }
    }

    void LateUpdate()
    {
        if (_blendshapes == null) return;

        // Smoothly interpolate current weights toward target weights
        float dt = Time.deltaTime * transitionSpeed;

        foreach (var key in _emotionKeys)
        {
            if (!_currentWeights.ContainsKey(key)) _currentWeights[key] = 0f;
            if (!_targetWeights.ContainsKey(key)) _targetWeights[key] = 0f;

            _currentWeights[key] = Mathf.MoveTowards(_currentWeights[key], _targetWeights[key], dt);

            // Apply to UniversalBlendshapes public fields
            float val = _currentWeights[key] * maxExpressionIntensity;
            switch (key)
            {
                case "Joy": _blendshapes.Joy = val; break;
                case "Angry": _blendshapes.Angry = val; break;
                case "Sorrow": _blendshapes.Sorrow = val; break;
                case "Fun": _blendshapes.Fun = val; break;
                case "Neutral": _blendshapes.Neutral = val; break;
            }
        }
    }

    /// <summary>
    /// Set the avatar's emotion from Vivy's emotion label.
    /// Called by VivyWebSocketClient when an emotion message arrives.
    /// </summary>
    public void SetEmotion(string emotionLabel)
    {
        if (string.IsNullOrEmpty(emotionLabel)) return;

        string emotion = emotionLabel.ToLower().Trim();

        if (emotion == currentEmotion) return;

        if (logEmotionChanges)
            Debug.Log($"[VivyEmotion] Emotion changed: {currentEmotion} → {emotion}");

        currentEmotion = emotion;

        if (_emotionMap.TryGetValue(emotion, out var weights))
        {
            foreach (var kvp in weights)
                _targetWeights[kvp.Key] = kvp.Value;
        }
        else
        {
            // Unknown emotion — default to neutral
            foreach (var key in _emotionKeys)
                _targetWeights[key] = key == "Neutral" ? 1f : 0f;
        }

        // Handle surprise with a quick blink
        if (emotion == "surprise")
            StartCoroutine(SurpriseBlink());
    }

    /// <summary>
    /// Directly set a blendshape weight. Called by VivyWebSocketClient for
    /// individual blendshape control messages.
    /// </summary>
    public void SetBlendshapeDirect(string shapeName, float weight)
    {
        if (_blendshapes == null || string.IsNullOrEmpty(shapeName)) return;

        weight = Mathf.Clamp01(weight);

        switch (shapeName)
        {
            case "Joy": _blendshapes.Joy = weight; break;
            case "Angry": _blendshapes.Angry = weight; break;
            case "Sorrow": _blendshapes.Sorrow = weight; break;
            case "Fun": _blendshapes.Fun = weight; break;
            case "Neutral": _blendshapes.Neutral = weight; break;
            case "Blink": _blendshapes.Blink = weight; break;
            case "Blink_L": _blendshapes.Blink_L = weight; break;
            case "Blink_R": _blendshapes.Blink_R = weight; break;
            case "A": _blendshapes.A = weight; break;
            case "I": _blendshapes.I = weight; break;
            case "U": _blendshapes.U = weight; break;
            case "E": _blendshapes.E = weight; break;
            case "O": _blendshapes.O = weight; break;
        }
    }

    /// <summary>
    /// Quick blink effect for surprise emotion.
    /// </summary>
    private IEnumerator SurpriseBlink()
    {
        if (_blendshapes == null) yield break;

        _blendshapes.Blink = 1f;
        yield return new WaitForSeconds(0.12f);
        _blendshapes.Blink = 0f;
    }
}
