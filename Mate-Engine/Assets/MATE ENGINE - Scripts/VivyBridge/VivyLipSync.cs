using UnityEngine;
using System.Collections;
using System.Collections.Generic;

/// <summary>
/// Vivy Lip Sync — Drives VRM viseme blendshapes (A/I/U/E/O) from text.
///
/// When Vivy sends a "speak" message, this component approximates lip
/// movement by mapping characters to viseme weights and playing them
/// as a timed sequence through UniversalBlendshapes.
///
/// This is a text-driven approach (not audio-driven) which works reliably
/// regardless of whether TTS audio is played locally or remotely.
///
/// Attach this to the root avatar GameObject (same as UniversalBlendshapes).
/// </summary>
[RequireComponent(typeof(UniversalBlendshapes))]
public class VivyLipSync : MonoBehaviour
{
    [Header("Lip Sync Settings")]
    [Range(0.03f, 0.15f)] public float phonemeDuration = 0.07f;
    [Range(0f, 1f)] public float visemeIntensity = 0.75f;
    [Range(1f, 20f)] public float smoothSpeed = 12f;
    [Range(0f, 1f)] public float restClosedWeight = 0f;

    [Header("Debug")]
    public bool isSpeaking = false;

    private UniversalBlendshapes _blendshapes;
    private Coroutine _lipSyncCoroutine;

    // Current and target viseme weights
    private float _targetA, _targetI, _targetU, _targetE, _targetO;

    // Character → Viseme mapping
    // Maps lowercase characters to approximate mouth shapes
    private static readonly Dictionary<char, int> _charToViseme = new Dictionary<char, int>
    {
        // Viseme index: 0=A, 1=I, 2=U, 3=E, 4=O, -1=closed
        { 'a', 0 }, { 'á', 0 }, { 'à', 0 },
        { 'i', 1 }, { 'í', 1 }, { 'y', 1 },
        { 'u', 2 }, { 'ú', 2 }, { 'w', 2 },
        { 'e', 3 }, { 'é', 3 }, { 'è', 3 },
        { 'o', 4 }, { 'ó', 4 }, { 'ò', 4 },
        // Consonants with approximate mouth shapes
        { 'b', 0 }, { 'p', 0 }, { 'm', 0 },      // Bilabial → closed/A
        { 'f', 1 }, { 'v', 1 },                     // Labiodental → I-ish
        { 't', 1 }, { 'd', 1 }, { 'n', 1 },         // Alveolar → I-ish
        { 's', 1 }, { 'z', 1 },                     // Sibilant → I-ish
        { 'k', 3 }, { 'g', 3 },                     // Velar → E-ish
        { 'l', 1 }, { 'r', 3 },                     // Liquid → I/E
        { 'h', 0 },                                   // Glottal → A
        { 'j', 1 },                                   // Palatal → I
        { 'c', 1 }, { 'q', 2 }, { 'x', 1 },
    };

    void Awake()
    {
        _blendshapes = GetComponent<UniversalBlendshapes>();
    }

    void LateUpdate()
    {
        if (_blendshapes == null) return;

        // Smooth interpolation of viseme weights
        float dt = Time.deltaTime * smoothSpeed;
        _blendshapes.A = Mathf.MoveTowards(_blendshapes.A, _targetA, dt);
        _blendshapes.I = Mathf.MoveTowards(_blendshapes.I, _targetI, dt);
        _blendshapes.U = Mathf.MoveTowards(_blendshapes.U, _targetU, dt);
        _blendshapes.E = Mathf.MoveTowards(_blendshapes.E, _targetE, dt);
        _blendshapes.O = Mathf.MoveTowards(_blendshapes.O, _targetO, dt);
    }

    private string _currentText = "";

    /// <summary>
    /// Start lip sync animation from text.
    /// Called by VivyWebSocketClient when a "speak" message arrives.
    /// </summary>
    public void StartLipSync(string text)
    {
        if (string.IsNullOrEmpty(text)) return;
        if (isSpeaking && text == _currentText) return; // Prevent redundant restarting of identical utterance text
        _currentText = text;
        StopLipSync();
        _lipSyncCoroutine = StartCoroutine(LipSyncCoroutine(text));
    }

    /// <summary>
    /// Stop any running lip sync animation.
    /// </summary>
    public void StopLipSync()
    {
        if (_lipSyncCoroutine != null)
        {
            StopCoroutine(_lipSyncCoroutine);
            _lipSyncCoroutine = null;
        }
        ResetVisemes();
        isSpeaking = false;
    }

    private IEnumerator LipSyncCoroutine(string text)
    {
        isSpeaking = true;
        string lower = text.ToLower();

        for (int i = 0; i < lower.Length; i++)
        {
            char c = lower[i];

            // Spaces and punctuation → brief mouth close
            if (c == ' ' || c == ',' || c == '.' || c == '!' || c == '?' || c == '\n')
            {
                ResetVisemeTargets();
                float pauseDuration = (c == ' ') ? phonemeDuration * 0.5f :
                                      (c == ',' || c == '.') ? phonemeDuration * 2f :
                                      phonemeDuration;
                yield return new WaitForSeconds(pauseDuration);
                continue;
            }

            // Map character to viseme
            if (_charToViseme.TryGetValue(c, out int visemeIndex))
            {
                SetVisemeTarget(visemeIndex);
            }
            else
            {
                // Unknown character → slight mouth movement
                SetVisemeTarget(0, 0.3f);
            }

            yield return new WaitForSeconds(phonemeDuration);
        }

        // Close mouth after speaking
        ResetVisemeTargets();
        yield return new WaitForSeconds(0.2f);

        isSpeaking = false;
        _lipSyncCoroutine = null;
    }

    private void SetVisemeTarget(int visemeIndex, float intensityOverride = -1f)
    {
        float intensity = intensityOverride > 0 ? intensityOverride : visemeIntensity;

        _targetA = (visemeIndex == 0) ? intensity : 0f;
        _targetI = (visemeIndex == 1) ? intensity : 0f;
        _targetU = (visemeIndex == 2) ? intensity : 0f;
        _targetE = (visemeIndex == 3) ? intensity : 0f;
        _targetO = (visemeIndex == 4) ? intensity : 0f;
    }

    private void ResetVisemeTargets()
    {
        _targetA = restClosedWeight;
        _targetI = restClosedWeight;
        _targetU = restClosedWeight;
        _targetE = restClosedWeight;
        _targetO = restClosedWeight;
    }

    private void ResetVisemes()
    {
        ResetVisemeTargets();
        if (_blendshapes != null)
        {
            _blendshapes.A = restClosedWeight;
            _blendshapes.I = restClosedWeight;
            _blendshapes.U = restClosedWeight;
            _blendshapes.E = restClosedWeight;
            _blendshapes.O = restClosedWeight;
        }
    }
}
